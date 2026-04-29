from __future__ import annotations

import hashlib
import inspect
import json
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from maestro_flow.config import AppConfig
from maestro_flow.contracts import STAGE_TO_MODEL
from maestro_flow.executor import apply_file_changes, run_commands
from maestro_flow.knowledge_base import KnowledgeItem, collect_knowledge
from maestro_flow.llm import LLMClient
from maestro_flow.policy_gate import (
    evaluate_execution_policies,
    evaluate_policies,
    has_blocking_failure,
    persist_policy_report,
)
from maestro_flow.prompting import PromptSpec, load_prompt_spec

ERROR_DAG_DEADLOCK = "DAG_DEADLOCK"
ERROR_STAGE_FAILED = "STAGE_EXECUTION_FAILED"
ERROR_MODEL_OUTPUT = "MODEL_OUTPUT_INVALID"
ERROR_QUALITY_GATE = "QUALITY_GATE_FAILED"
ERROR_ROLLBACK_FAILED = "ROLLBACK_FAILED"
ERROR_POLICY_GATE = "POLICY_GATE_FAILED"
ERROR_EXECUTION_LOOP = "EXECUTION_LOOP_FAILED"
ERROR_SYNC_BACK = "SYNC_BACK_FAILED"


@dataclass(frozen=True)
class StageNode:
    name: str
    dependencies: list[str]


WORKFLOW_DAG = [
    StageNode("pm", []),
    StageNode("architect", ["pm"]),
    StageNode("dev", ["architect"]),
    StageNode("tester", ["dev"]),
    StageNode("debugger", ["dev"]),
    StageNode("reviewer", ["architect", "dev", "tester", "debugger"]),
]

STAGE_ORDER = [node.name for node in WORKFLOW_DAG]
STAGE_MAP = {node.name: node for node in WORKFLOW_DAG}


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    verdict: str
    summary_file: Path


@dataclass
class StageExecResult:
    stage: str
    success: bool
    data: dict[str, Any] | None = None
    error_code: str = ""
    error_message: str = ""


@dataclass
class RollbackExecResult:
    status: str
    steps: list[dict[str, Any]]
    started_at: str
    ended_at: str
    mode: str
    message: str = ""


class DevFlowOrchestrator:
    def __init__(
        self,
        *,
        repo_root: Path,
        config: AppConfig,
        model: str,
        mock: bool,
        llm_client: LLMClient | None = None,
    ):
        self.repo_root = repo_root
        self.config = config
        self.llm = llm_client or LLMClient(repo_root=repo_root, model=model, mock=mock)
        self._llm_supports_prompt_text = self._detect_prompt_text_support()

    def run(
        self,
        *,
        requirement: str,
        execute_quality_gates: bool = True,
        execute_rollback: bool = True,
    ) -> RunResult:
        run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}-{uuid4().hex[:6]}"
        run_dir = self.repo_root / ".maestro" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        manifest = self._new_manifest(run_id=run_id)
        manifest_lock = threading.Lock()

        knowledge_items = collect_knowledge(self.repo_root, self.config.knowledge)
        prompt_registry = self._build_prompt_registry()
        manifest["knowledge"] = [self._knowledge_to_dict(item) for item in knowledge_items]
        manifest["prompts"] = {
            stage: {"path": spec.path, "version": spec.version, "sha256": spec.sha256}
            for stage, spec in prompt_registry.items()
        }
        self._save_manifest(run_dir, manifest, manifest_lock)
        self._write_knowledge_snapshot(run_dir, knowledge_items)
        self._write_prompt_registry(run_dir, prompt_registry)

        stage_outputs = self._run_dag_workflow(
            requirement=requirement,
            run_dir=run_dir,
            manifest=manifest,
            manifest_lock=manifest_lock,
            prompt_registry=prompt_registry,
            knowledge_items=knowledge_items,
        )

        execution_report: dict[str, Any] = {}
        workspace = {
            "mode": "inplace",
            "repo_root": str(self.repo_root),
            "cleanup": False,
        }
        if manifest["status"] != "failed" and self.config.workflow.execution_enabled:
            workspace = self._prepare_execution_workspace(run_dir)
            execution_repo_root = Path(workspace["repo_root"])
            execution_report = self._run_execution_loop(
                requirement=requirement,
                run_dir=run_dir,
                stage_outputs=stage_outputs,
                prompt_registry=prompt_registry,
                knowledge_items=knowledge_items,
                execution_repo_root=execution_repo_root,
            )

            execution_report["workspace"] = {
                "mode": workspace.get("mode", "inplace"),
                "repo_root": workspace.get("repo_root", str(self.repo_root)),
                "cleanup": bool(workspace.get("cleanup", False)),
                "baseline_snapshot": workspace.get("baseline_snapshot", ""),
            }
            manifest["execution"] = execution_report
            if execution_report.get("status") == "failed":
                manifest["status"] = "failed"
                manifest["error_code"] = ERROR_EXECUTION_LOOP
                manifest["error_message"] = execution_report.get("message", "执行闭环未通过。")
            else:
                refresh_result = self._refresh_reviewer_after_execution(
                    requirement=requirement,
                    run_dir=run_dir,
                    stage_outputs=stage_outputs,
                    prompt_registry=prompt_registry,
                    knowledge_items=knowledge_items,
                    execution_report=execution_report,
                )
                execution_report["reviewer_refresh"] = refresh_result
                refreshed_reviewer = refresh_result.get("reviewer")
                if isinstance(refreshed_reviewer, dict):
                    stage_outputs["reviewer"] = refreshed_reviewer

        raw_policy_results = []
        if manifest["status"] != "failed":
            raw_policy_results.extend(evaluate_policies(stage_outputs, self.config.policy, self.repo_root))
        raw_policy_results.extend(
            evaluate_execution_policies(
                execution_report=execution_report,
                overrides=self.config.policy.rules,
            )
        )
        persist_policy_report(run_dir, raw_policy_results)
        policy_results: list[dict[str, Any]] = [
            {
                "policy_id": r.policy_id,
                "status": r.status,
                "blocking": r.blocking,
                "message": r.message,
            }
            for r in raw_policy_results
        ]
        manifest["policies"] = policy_results
        if manifest["status"] != "failed" and has_blocking_failure(raw_policy_results):
            manifest["status"] = "failed"
            manifest["error_code"] = ERROR_POLICY_GATE
            manifest["error_message"] = "策略门禁未通过，存在阻断型失败规则。"

        gate_results: list[dict[str, Any]] = []
        if execute_quality_gates and manifest["status"] != "failed":
            gate_results = self._run_quality_gates(run_dir)
            manifest["quality_gates"] = gate_results
            required_failed = any(g["required"] and g["exit_code"] != 0 for g in gate_results)
            if required_failed:
                manifest["status"] = "failed"
                manifest["error_code"] = ERROR_QUALITY_GATE
                manifest["error_message"] = "存在必过质量门禁失败。"

        if self._should_sync_back_changes(execution_report, manifest_status=manifest["status"]):
            sync_report = self._sync_execution_changes_from_workspace(
                run_dir=run_dir,
                execution_report=execution_report,
                workspace_repo_root=Path(workspace.get("repo_root", str(self.repo_root))),
                baseline_snapshot_path=Path(workspace["baseline_snapshot"]) if workspace.get("baseline_snapshot") else None,
            )
            execution_report["sync_back"] = sync_report
            if manifest["status"] != "failed" and sync_report.get("status") == "failed":
                manifest["status"] = "failed"
                manifest["error_code"] = ERROR_SYNC_BACK
                manifest["error_message"] = sync_report.get("message", "执行改动回写主工作区失败。")

        rollback_result = self._run_rollback_on_failure(
            run_dir=run_dir,
            manifest=manifest,
            execute_rollback=execute_rollback,
        )
        manifest["rollback"] = {
            "status": rollback_result.status,
            "mode": rollback_result.mode,
            "message": rollback_result.message,
            "started_at": rollback_result.started_at,
            "ended_at": rollback_result.ended_at,
            "steps": rollback_result.steps,
        }

        if manifest["status"] == "failed":
            if rollback_result.status == "rolled_back":
                manifest["status"] = "rolled_back"
            elif rollback_result.status == "rollback_failed":
                manifest["status"] = "rollback_failed"
                manifest["error_code"] = ERROR_ROLLBACK_FAILED
                if not manifest["error_message"]:
                    manifest["error_message"] = rollback_result.message or "回滚执行失败。"
        else:
            manifest["status"] = "succeeded"
        manifest["ended_at"] = self._now_iso()
        self._save_manifest(run_dir, manifest, manifest_lock)

        review = stage_outputs.get("reviewer")
        verdict = review["verdict"] if review else manifest["status"]

        summary_file = run_dir / "summary.md"
        summary_file.write_text(
            self._build_summary(requirement, stage_outputs, gate_results, manifest),
            encoding="utf-8",
        )

        if workspace.get("mode") == "copy" and bool(workspace.get("cleanup", False)):
            self._cleanup_execution_workspace(Path(workspace["repo_root"]))

        return RunResult(
            run_id=run_id,
            run_dir=run_dir,
            verdict=verdict,
            summary_file=summary_file,
        )

    def _run_rollback_on_failure(
        self,
        *,
        run_dir: Path,
        manifest: dict[str, Any],
        execute_rollback: bool,
    ) -> RollbackExecResult:
        now = self._now_iso()
        mode = self.config.rollback.mode
        if manifest["status"] != "failed":
            return RollbackExecResult(
                status="skipped",
                steps=[],
                started_at=now,
                ended_at=now,
                mode=mode,
                message="本次运行成功，跳过回滚。",
            )

        if not execute_rollback:
            return RollbackExecResult(
                status="skipped",
                steps=[],
                started_at=now,
                ended_at=now,
                mode=mode,
                message="运行参数禁用了回滚执行。",
            )

        if not self.config.rollback.enabled:
            return RollbackExecResult(
                status="skipped",
                steps=[],
                started_at=now,
                ended_at=now,
                mode=mode,
                message="配置中已禁用回滚。",
            )

        if mode != "command":
            return RollbackExecResult(
                status="rollback_failed",
                steps=[],
                started_at=now,
                ended_at=self._now_iso(),
                mode=mode,
                message=f"不支持的回滚模式：{mode}",
            )

        if not self.config.rollback.commands:
            return RollbackExecResult(
                status="skipped",
                steps=[],
                started_at=now,
                ended_at=self._now_iso(),
                mode=mode,
                message="未配置回滚命令，跳过回滚。",
            )

        steps: list[dict[str, Any]] = []
        rollback_status = "rolled_back"
        for idx, command in enumerate(self.config.rollback.commands, start=1):
            proc = subprocess.run(
                command,
                cwd=self.repo_root,
                shell=True,
                capture_output=True,
                text=True,
            )
            step = {
                "index": idx,
                "command": command,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "status": "succeeded" if proc.returncode == 0 else "failed",
            }
            steps.append(step)
            (run_dir / f"rollback_step_{idx}.log").write_text(
                f"$ {command}\n\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n",
                encoding="utf-8",
            )
            if proc.returncode != 0 and self.config.rollback.stop_on_error:
                rollback_status = "rollback_failed"
                break

        report = RollbackExecResult(
            status=rollback_status,
            steps=steps,
            started_at=now,
            ended_at=self._now_iso(),
            mode=mode,
            message="" if rollback_status == "rolled_back" else "至少一个回滚命令执行失败。",
        )
        self._write_rollback_report(run_dir=run_dir, report=report)
        return report

    @staticmethod
    def _write_rollback_report(*, run_dir: Path, report: RollbackExecResult) -> None:
        data = {
            "status": report.status,
            "mode": report.mode,
            "message": report.message,
            "started_at": report.started_at,
            "ended_at": report.ended_at,
            "steps": report.steps,
        }
        (run_dir / "rollback_report.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _run_dag_workflow(
        self,
        *,
        requirement: str,
        run_dir: Path,
        manifest: dict[str, Any],
        manifest_lock: threading.Lock,
        prompt_registry: dict[str, PromptSpec],
        knowledge_items: list[KnowledgeItem],
    ) -> dict[str, Any]:
        stage_outputs: dict[str, Any] = {}
        pending = set(STAGE_ORDER)
        completed: set[str] = set()
        failed = False

        while pending and not failed:
            ready = [
                stage for stage in pending if all(dep in completed for dep in STAGE_MAP[stage].dependencies)
            ]
            if not ready:
                manifest["status"] = "failed"
                manifest["error_code"] = ERROR_DAG_DEADLOCK
                manifest["error_message"] = "没有可执行阶段，请检查 DAG 依赖关系。"
                for stg in sorted(pending):
                    if manifest["stages"][stg]["status"] == "pending":
                        manifest["stages"][stg]["status"] = "skipped"
                self._save_manifest(run_dir, manifest, manifest_lock)
                break

            with ThreadPoolExecutor(max_workers=self.config.workflow.parallel_workers) as pool:
                future_map = {
                    pool.submit(
                        self._execute_stage_with_retry,
                        stage=stage,
                        requirement=requirement,
                        stage_outputs=stage_outputs,
                        run_dir=run_dir,
                        manifest=manifest,
                        manifest_lock=manifest_lock,
                        prompt_registry=prompt_registry,
                        knowledge_items=knowledge_items,
                    ): stage
                    for stage in ready
                }

                for future in as_completed(future_map):
                    result = future.result()
                    stage = result.stage
                    pending.discard(stage)
                    if result.success and result.data is not None:
                        stage_outputs[stage] = result.data
                        completed.add(stage)
                    else:
                        failed = True
                        manifest["status"] = "failed"
                        manifest["error_code"] = result.error_code or ERROR_STAGE_FAILED
                        manifest["error_message"] = result.error_message or f"阶段执行失败: {stage}"

            if failed:
                for stg in sorted(pending):
                    if manifest["stages"][stg]["status"] == "pending":
                        manifest["stages"][stg]["status"] = "skipped"
                self._save_manifest(run_dir, manifest, manifest_lock)

        return stage_outputs

    def _execute_stage_with_retry(
        self,
        *,
        stage: str,
        requirement: str,
        stage_outputs: dict[str, Any],
        run_dir: Path,
        manifest: dict[str, Any],
        manifest_lock: threading.Lock,
        prompt_registry: dict[str, PromptSpec],
        knowledge_items: list[KnowledgeItem],
    ) -> StageExecResult:
        agent = self.config.agents[stage]
        schema = STAGE_TO_MODEL[stage]
        max_attempts = max(1, self.config.workflow.max_retries + 1)
        prompt_spec = prompt_registry[stage]

        for attempt in range(1, max_attempts + 1):
            self._update_stage_state(
                run_dir=run_dir,
                manifest=manifest,
                manifest_lock=manifest_lock,
                stage=stage,
                status="running",
                attempts=attempt,
            )

            try:
                context: dict[str, Any] = {"repo_root": str(self.repo_root)}
                for dep in STAGE_MAP[stage].dependencies:
                    context[dep] = stage_outputs.get(dep, {})
                context["knowledge"] = [self._knowledge_to_context(item) for item in knowledge_items]
                context["prompt_meta"] = {
                    "path": prompt_spec.path,
                    "version": prompt_spec.version,
                    "sha256": prompt_spec.sha256,
                }

                result = self.llm.complete_json(
                    **self._build_llm_kwargs(
                        stage=stage,
                        agent=agent,
                        schema=schema,
                        requirement=requirement,
                        context=context,
                        prompt_text=prompt_spec.content,
                    )
                )
                data = result.model_dump(mode="json")
                (run_dir / f"stage_{stage}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                self._update_stage_state(
                    run_dir=run_dir,
                    manifest=manifest,
                    manifest_lock=manifest_lock,
                    stage=stage,
                    status="succeeded",
                    error_code="",
                    error_message="",
                )
                return StageExecResult(stage=stage, success=True, data=data)
            except Exception as exc:
                error_message = str(exc)
                error_code = self._classify_stage_error(exc)
                if attempt < max_attempts:
                    self._update_stage_state(
                        run_dir=run_dir,
                        manifest=manifest,
                        manifest_lock=manifest_lock,
                        stage=stage,
                        status="retrying",
                        error_code=error_code,
                        error_message=error_message,
                    )
                    continue

                self._update_stage_state(
                    run_dir=run_dir,
                    manifest=manifest,
                    manifest_lock=manifest_lock,
                    stage=stage,
                    status="failed",
                    error_code=error_code,
                    error_message=error_message,
                )
                return StageExecResult(
                    stage=stage,
                    success=False,
                    error_code=error_code,
                    error_message=error_message,
                )

        return StageExecResult(stage=stage, success=False, error_code=ERROR_STAGE_FAILED)

    @staticmethod
    def _classify_stage_error(exc: Exception) -> str:
        msg = str(exc).lower()
        if "json" in msg:
            return ERROR_MODEL_OUTPUT
        return ERROR_STAGE_FAILED

    def _run_quality_gates(self, run_dir: Path) -> list[dict[str, Any]]:
        results = []
        for gate in self.config.quality_gates:
            proc = subprocess.run(
                gate.command,
                cwd=self.repo_root,
                shell=True,
                capture_output=True,
                text=True,
            )
            result = {
                "name": gate.name,
                "command": gate.command,
                "required": gate.required,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
            results.append(result)
            (run_dir / f"gate_{gate.name}.log").write_text(
                f"$ {gate.command}\n\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n",
                encoding="utf-8",
            )
        return results

    def _new_manifest(self, *, run_id: str) -> dict[str, Any]:
        now = self._now_iso()
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "status": "running",
            "error_code": "",
            "error_message": "",
            "started_at": now,
            "ended_at": "",
            "updated_at": now,
            "stages": {
                stage: {
                    "status": "pending",
                    "dependencies": STAGE_MAP[stage].dependencies,
                    "attempts": 0,
                    "max_attempts": max(1, self.config.workflow.max_retries + 1),
                    "error_code": "",
                    "error_message": "",
                    "started_at": "",
                    "ended_at": "",
                }
                for stage in STAGE_ORDER
            },
            "quality_gates": [],
            "knowledge": [],
            "prompts": {},
            "policies": [],
            "execution": {},
        }

    def _update_stage_state(
        self,
        *,
        run_dir: Path,
        manifest: dict[str, Any],
        manifest_lock: threading.Lock,
        stage: str,
        status: str,
        attempts: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with manifest_lock:
            st = manifest["stages"][stage]
            st["status"] = status
            if attempts is not None:
                st["attempts"] = attempts
            if error_code is not None:
                st["error_code"] = error_code
            if error_message is not None:
                st["error_message"] = error_message
            now = self._now_iso()
            if status == "running" and not st["started_at"]:
                st["started_at"] = now
            if status in {"succeeded", "failed", "skipped"}:
                st["ended_at"] = now
            self._save_manifest(run_dir, manifest, manifest_lock=None)

    def _save_manifest(
        self,
        run_dir: Path,
        manifest: dict[str, Any],
        manifest_lock: threading.Lock | None,
    ) -> None:
        # 这里不加锁，由调用方决定锁的粒度和生命周期。
        manifest["updated_at"] = self._now_iso()
        (run_dir / "run_state.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _build_summary(
        requirement: str,
        stage_outputs: dict[str, Any],
        gate_results: list[dict[str, Any]],
        manifest: dict[str, Any],
    ) -> str:
        reviewer = stage_outputs.get("reviewer", {})
        verdict = reviewer.get("verdict", manifest.get("status", "unknown"))
        lines = [
            "# Maestro Flow 运行总结",
            "",
            "## 需求",
            requirement,
            "",
            "## 运行状态",
            manifest.get("status", "unknown"),
            "",
            "## 评审结论",
            verdict,
            "",
            "## 阶段状态",
        ]

        for stage in STAGE_ORDER:
            st = manifest["stages"][stage]
            lines.append(
                f"- {stage}: {st['status']} (尝试={st['attempts']}/{st['max_attempts']}, 错误={st['error_code'] or '无'})"
            )

        lines.extend(["", "## 评审发现"])
        findings = reviewer.get("findings", [])
        if not findings:
            lines.append("- 无")
        else:
            for f in findings:
                lines.append(
                    f"- [{f['severity']}] {f['finding']} | 文件: {f.get('file_ref', '')} | 建议: {f['recommendation']}"
                )

        lines.extend(["", "## 质量门禁"])
        if not gate_results:
            lines.append("- 已跳过")
        else:
            for g in gate_results:
                state = "通过" if g["exit_code"] == 0 else "失败"
                lines.append(f"- {g['name']}: {state} (exit={g['exit_code']})")

        lines.extend(["", "## 合并条件"])
        for c in reviewer.get("merge_conditions", []):
            lines.append(f"- {c}")

        lines.extend(["", "## 策略门禁"])
        policies = manifest.get("policies", [])
        if not policies:
            lines.append("- 已跳过")
        else:
            for p in policies:
                lines.append(
                    f"- {p.get('policy_id')}: {p.get('status')} (blocking={p.get('blocking')}) | {p.get('message')}"
                )

        execution = manifest.get("execution", {})
        lines.extend(["", "## 执行闭环"])
        if not execution:
            lines.append("- 已跳过")
        else:
            lines.append(f"- 状态: {execution.get('status', 'unknown')}")
            lines.append(f"- 轮次: {execution.get('rounds', 0)}")
            if execution.get("message"):
                lines.append(f"- 信息: {execution.get('message')}")
            workspace = execution.get("workspace", {})
            if workspace:
                lines.append(f"- 执行空间: {workspace.get('mode')} ({workspace.get('repo_root')})")
            reviewer_refresh = execution.get("reviewer_refresh", {})
            if reviewer_refresh:
                lines.append(f"- reviewer 刷新: {reviewer_refresh.get('status', 'unknown')}")
            sync_back = execution.get("sync_back", {})
            if sync_back:
                lines.append(f"- 回写主工作区: {sync_back.get('status', 'unknown')}")

        rollback = manifest.get("rollback", {})
        lines.extend(["", "## 回滚"])
        lines.append(f"- 状态: {rollback.get('status', 'n/a')}")
        lines.append(f"- 模式: {rollback.get('mode', 'n/a')}")
        if rollback.get("message"):
            lines.append(f"- 信息: {rollback.get('message')}")
        steps = rollback.get("steps", [])
        if steps:
            lines.append("- 步骤:")
            for step in steps:
                lines.append(
                    f"  - #{step.get('index')}: {step.get('status')} (exit={step.get('exit_code')})"
                )
        return "\n".join(lines) + "\n"

    def _detect_prompt_text_support(self) -> bool:
        try:
            sig = inspect.signature(self.llm.complete_json)
        except (TypeError, ValueError):
            return True
        return "prompt_text" in sig.parameters

    def _build_llm_kwargs(
        self,
        *,
        stage: str,
        agent: Any,
        schema: Any,
        requirement: str,
        context: dict[str, Any],
        prompt_text: str,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "stage": stage,
            "agent": agent,
            "schema": schema,
            "requirement": requirement,
            "context": context,
        }
        if self._llm_supports_prompt_text:
            kwargs["prompt_text"] = prompt_text
        return kwargs

    def _run_execution_loop(
        self,
        *,
        requirement: str,
        run_dir: Path,
        stage_outputs: dict[str, Any],
        prompt_registry: dict[str, PromptSpec],
        knowledge_items: list[KnowledgeItem],
        execution_repo_root: Path,
    ) -> dict[str, Any]:
        commands = self._collect_execution_commands(stage_outputs)
        if not commands:
            return {
                "status": "skipped",
                "rounds": 0,
                "message": "未提供可执行验证命令，跳过执行闭环。",
            }

        max_loops = max(1, self.config.workflow.max_fix_loops)
        allowed_prefixes = self.config.workflow.allowed_execution_commands
        command_policies = self.config.workflow.command_policies
        unmatched_action = self.config.workflow.unmatched_command_action
        blocked_fragments = self.config.workflow.blocked_command_fragments
        timeout_seconds = self.config.workflow.command_timeout_seconds
        pending_file_changes = list(stage_outputs.get("dev", {}).get("file_changes", []))
        pending_fix_commands: list[str] = []
        round_reports: list[dict[str, Any]] = []

        for round_index in range(1, max_loops + 1):
            apply_report = apply_file_changes(
                repo_root=execution_repo_root,
                file_changes=pending_file_changes,
                run_dir=run_dir,
                round_index=round_index,
            )
            fix_command_results = run_commands(
                repo_root=execution_repo_root,
                commands=pending_fix_commands,
                allowed_prefixes=allowed_prefixes,
                command_policies=command_policies,
                unmatched_action=unmatched_action,
                blocked_fragments=blocked_fragments,
                timeout_seconds=timeout_seconds,
            )
            verify_command_results = run_commands(
                repo_root=execution_repo_root,
                commands=commands,
                allowed_prefixes=allowed_prefixes,
                command_policies=command_policies,
                unmatched_action=unmatched_action,
                blocked_fragments=blocked_fragments,
                timeout_seconds=timeout_seconds,
            )
            all_results = [*fix_command_results, *verify_command_results]
            round_passed = bool(all_results) and all(item.exit_code == 0 for item in all_results)

            report = {
                "round": round_index,
                "status": "succeeded" if round_passed else "failed",
                "file_apply": apply_report,
                "fix_commands": [
                    {
                        "command": item.command,
                        "allowed": item.allowed,
                        "exit_code": item.exit_code,
                        "stdout": item.stdout,
                        "stderr": item.stderr,
                        "timed_out": item.timed_out,
                        "warnings": item.warnings,
                    }
                    for item in fix_command_results
                ],
                "verify_commands": [
                    {
                        "command": item.command,
                        "allowed": item.allowed,
                        "exit_code": item.exit_code,
                        "stdout": item.stdout,
                        "stderr": item.stderr,
                        "timed_out": item.timed_out,
                        "warnings": item.warnings,
                    }
                    for item in verify_command_results
                ],
            }
            round_reports.append(report)
            self._write_execution_round_report(run_dir=run_dir, report=report)

            if round_passed:
                return {
                    "status": "succeeded",
                    "rounds": round_index,
                    "message": "执行闭环通过。",
                    "reports": round_reports,
                }

            if round_index >= max_loops:
                break

            debugger_output = self._execute_debugger_followup(
                requirement=requirement,
                run_dir=run_dir,
                stage_outputs=stage_outputs,
                prompt_registry=prompt_registry,
                knowledge_items=knowledge_items,
                round_index=round_index,
                latest_report=report,
                execution_repo_root=execution_repo_root,
            )
            stage_outputs["debugger"] = debugger_output
            pending_file_changes = list(debugger_output.get("file_changes", []))
            pending_fix_commands = list(debugger_output.get("fix_commands", []))

        return {
            "status": "failed",
            "rounds": len(round_reports),
            "message": "执行闭环达到最大修复轮次仍未通过。",
            "reports": round_reports,
        }

    def _refresh_reviewer_after_execution(
        self,
        *,
        requirement: str,
        run_dir: Path,
        stage_outputs: dict[str, Any],
        prompt_registry: dict[str, PromptSpec],
        knowledge_items: list[KnowledgeItem],
        execution_report: dict[str, Any],
    ) -> dict[str, Any]:
        stage = "reviewer"
        agent = self.config.agents[stage]
        schema = STAGE_TO_MODEL[stage]
        prompt_spec = prompt_registry[stage]
        context: dict[str, Any] = {"repo_root": str(self.repo_root)}
        for dep in STAGE_MAP[stage].dependencies:
            context[dep] = stage_outputs.get(dep, {})
        context["previous_reviewer"] = stage_outputs.get("reviewer", {})
        context["execution"] = execution_report
        context["knowledge"] = [self._knowledge_to_context(item) for item in knowledge_items]
        context["prompt_meta"] = {
            "path": prompt_spec.path,
            "version": prompt_spec.version,
            "sha256": prompt_spec.sha256,
        }

        try:
            result = self.llm.complete_json(
                **self._build_llm_kwargs(
                    stage=stage,
                    agent=agent,
                    schema=schema,
                    requirement=requirement,
                    context=context,
                    prompt_text=prompt_spec.content,
                )
            )
            data = result.model_dump(mode="json")
            (run_dir / "stage_reviewer_post_execution.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # 保持与现有 CI 读取逻辑兼容，覆盖最新 reviewer 结果。
            (run_dir / "stage_reviewer.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "status": "succeeded",
                "message": "已完成执行闭环后的 reviewer 刷新。",
                "reviewer": data,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "message": f"reviewer 刷新失败：{exc}",
            }

    def _execute_debugger_followup(
        self,
        *,
        requirement: str,
        run_dir: Path,
        stage_outputs: dict[str, Any],
        prompt_registry: dict[str, PromptSpec],
        knowledge_items: list[KnowledgeItem],
        round_index: int,
        latest_report: dict[str, Any],
        execution_repo_root: Path,
    ) -> dict[str, Any]:
        stage = "debugger"
        agent = self.config.agents[stage]
        schema = STAGE_TO_MODEL[stage]
        prompt_spec = prompt_registry[stage]
        context: dict[str, Any] = {"repo_root": str(self.repo_root)}
        context["execution_repo_root"] = str(execution_repo_root)
        context["dev"] = stage_outputs.get("dev", {})
        context["tester"] = stage_outputs.get("tester", {})
        context["debugger_previous"] = stage_outputs.get("debugger", {})
        context["execution_round"] = latest_report
        context["knowledge"] = [self._knowledge_to_context(item) for item in knowledge_items]
        context["prompt_meta"] = {
            "path": prompt_spec.path,
            "version": prompt_spec.version,
            "sha256": prompt_spec.sha256,
        }

        result = self.llm.complete_json(
            **self._build_llm_kwargs(
                stage=stage,
                agent=agent,
                schema=schema,
                requirement=requirement,
                context=context,
                prompt_text=prompt_spec.content,
            )
        )
        data = result.model_dump(mode="json")
        (run_dir / f"stage_debugger_loop_{round_index}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return data

    @staticmethod
    def _collect_execution_commands(stage_outputs: dict[str, Any]) -> list[str]:
        commands: list[str] = []
        for source in ("dev", "tester"):
            for cmd in stage_outputs.get(source, {}).get(
                "verification_commands" if source == "dev" else "run_commands",
                [],
            ):
                normalized = str(cmd).strip()
                if normalized and normalized not in commands:
                    commands.append(normalized)
        return commands

    @staticmethod
    def _write_execution_round_report(*, run_dir: Path, report: dict[str, Any]) -> None:
        round_index = report.get("round", 0)
        (run_dir / f"test_report_round_{round_index}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        lines = [
            f"# 修复轮次 {round_index}",
            "",
            f"- 状态: {report.get('status')}",
            f"- 文件变更应用数: {report.get('file_apply', {}).get('applied_count', 0)}",
            f"- 文件变更跳过数: {report.get('file_apply', {}).get('skipped_count', 0)}",
            "",
            "## 验证命令结果",
        ]
        verify_commands = report.get("verify_commands", [])
        if not verify_commands:
            lines.append("- 无")
        else:
            for item in verify_commands:
                warn_count = len(item.get("warnings", []))
                lines.append(f"- {item.get('command')}: exit={item.get('exit_code')} allowed={item.get('allowed')} warnings={warn_count}")
        (run_dir / f"fix_round_{round_index}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _should_sync_back_changes(self, execution_report: dict[str, Any], manifest_status: str) -> bool:
        if not execution_report:
            return False
        if not self.config.workflow.sync_back_on_success:
            return False
        if execution_report.get("status") != "succeeded":
            return False
        workspace_mode = execution_report.get("workspace", {}).get("mode")
        if workspace_mode != "copy":
            return False
        if self.config.workflow.sync_back_only_if_policies_pass and manifest_status == "failed":
            return False
        return True

    def _sync_execution_changes_from_workspace(
        self,
        *,
        run_dir: Path,
        execution_report: dict[str, Any],
        workspace_repo_root: Path,
        baseline_snapshot_path: Path | None = None,
    ) -> dict[str, Any]:
        plan = self._build_sync_plan(execution_report)
        if not plan:
            report = {
                "status": "skipped",
                "message": "执行闭环没有可回写的文件改动。",
                "applied": [],
                "failed": [],
                "skipped": [],
                "conflicts": [],
                "conflicts_ignored": [],
            }
            (run_dir / "sync_back_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return report

        applied: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        conflicts_ignored: list[dict[str, Any]] = []
        warnings: list[str] = []
        repo_root_resolved = self.repo_root.resolve()
        workspace_root_resolved = workspace_repo_root.resolve()
        baseline_files, baseline_loaded = self._load_sync_back_baseline(baseline_snapshot_path)
        conflict_action = self.config.workflow.sync_back_conflict_action

        for rel_path, action in plan.items():
            target = (self.repo_root / rel_path).resolve()
            source = (workspace_repo_root / rel_path).resolve()
            try:
                target.relative_to(repo_root_resolved)
                source.relative_to(workspace_root_resolved)
            except ValueError:
                failed.append(
                    {"path": rel_path, "action": action, "message": "路径越界，拒绝回写。"}
                )
                continue

            conflict_detail = self._detect_sync_conflict(
                rel_path=rel_path,
                target=target,
                baseline_files=baseline_files,
                baseline_loaded=baseline_loaded,
            )
            if conflict_detail is not None:
                if conflict_action == "overwrite":
                    conflicts_ignored.append(conflict_detail)
                else:
                    conflicts.append(conflict_detail)
                    failed.append(
                        {
                            "path": rel_path,
                            "action": action,
                            "message": "检测到主工作区文件在执行期间已变化，按 block 策略阻断回写。",
                        }
                    )
                    continue

            if action == "delete":
                if target.exists():
                    if target.is_file():
                        try:
                            target.unlink()
                        except OSError as exc:
                            failed.append({"path": rel_path, "action": action, "message": f"删除目标文件失败: {exc}"})
                            continue
                        applied.append({"path": rel_path, "action": action, "message": "已删除目标文件。"})
                    else:
                        failed.append({"path": rel_path, "action": action, "message": "目标路径不是文件，删除失败。"})
                else:
                    skipped.append({"path": rel_path, "action": action, "message": "目标文件不存在，跳过删除。"})
                continue

            if not source.exists() or not source.is_file():
                failed.append({"path": rel_path, "action": action, "message": "隔离空间源文件不存在。"})
                continue

            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            except OSError as exc:
                failed.append({"path": rel_path, "action": action, "message": f"复制回主工作区失败: {exc}"})
                continue
            applied.append({"path": rel_path, "action": action, "message": "已回写到主工作区。"})

        if baseline_snapshot_path and not baseline_loaded:
            warnings.append("未加载回写基线快照，跳过冲突检测。")

        status = "failed" if failed else "succeeded"
        message = "执行改动已回写主工作区。" if status == "succeeded" else "部分执行改动回写失败。"
        report = {
            "status": status,
            "message": message,
            "applied": applied,
            "failed": failed,
            "skipped": skipped,
            "conflict_action": conflict_action,
            "conflicts": conflicts,
            "conflicts_ignored": conflicts_ignored,
            "warnings": warnings,
        }
        (run_dir / "sync_back_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report

    @staticmethod
    def _build_sync_plan(execution_report: dict[str, Any]) -> dict[str, str]:
        latest_actions: dict[str, str] = {}
        for round_report in execution_report.get("reports", []):
            file_apply = round_report.get("file_apply", {})
            for item in file_apply.get("results", []):
                if str(item.get("status", "")) != "applied":
                    continue
                path = str(item.get("path", "")).strip()
                action = str(item.get("action", "")).strip().lower()
                if path and action in {"create", "update", "delete"}:
                    latest_actions[path] = action
        return latest_actions

    def _prepare_execution_workspace(self, run_dir: Path) -> dict[str, Any]:
        mode = self.config.workflow.execution_workspace_mode
        if mode == "copy":
            baseline_snapshot = run_dir / "sync_back_baseline.json"
            baseline_snapshot.write_text(
                json.dumps(
                    {
                        "created_at": self._now_iso(),
                        "root": str(self.repo_root),
                        "files": self._build_repo_snapshot(self.repo_root),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            workspace_root = run_dir / "exec_workspace"
            self._copy_repo_to_workspace(self.repo_root, workspace_root)
            return {
                "mode": "copy",
                "repo_root": str(workspace_root),
                "cleanup": self.config.workflow.cleanup_execution_workspace,
                "baseline_snapshot": str(baseline_snapshot),
            }
        return {
            "mode": "inplace",
            "repo_root": str(self.repo_root),
            "cleanup": False,
        }

    @staticmethod
    def _copy_repo_to_workspace(src_root: Path, dst_root: Path) -> None:
        def _ignore(directory: str, names: list[str]) -> set[str]:
            ignored = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
            if Path(directory).resolve() == src_root.resolve():
                ignored.add(".maestro")
            return {name for name in names if name in ignored}

        if dst_root.exists():
            shutil.rmtree(dst_root)
        shutil.copytree(src_root, dst_root, ignore=_ignore)

    @staticmethod
    def _cleanup_execution_workspace(workspace_root: Path) -> None:
        if workspace_root.exists():
            shutil.rmtree(workspace_root, ignore_errors=True)

    @staticmethod
    def _build_repo_snapshot(repo_root: Path) -> dict[str, str]:
        ignored_roots = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".maestro"}
        snapshot: dict[str, str] = {}
        for file_path in repo_root.rglob("*"):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(repo_root)
            if any(part in ignored_roots for part in rel_path.parts):
                continue
            snapshot[rel_path.as_posix()] = DevFlowOrchestrator._sha256_file(file_path)
        return snapshot

    @staticmethod
    def _sha256_file(file_path: Path) -> str:
        hasher = hashlib.sha256()
        with file_path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _load_sync_back_baseline(baseline_snapshot_path: Path | None) -> tuple[dict[str, str], bool]:
        if baseline_snapshot_path is None or not baseline_snapshot_path.exists():
            return {}, False
        try:
            payload = json.loads(baseline_snapshot_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}, False
        files = payload.get("files", {}) if isinstance(payload, dict) else {}
        if not isinstance(files, dict):
            return {}, False
        normalized: dict[str, str] = {}
        for path, file_hash in files.items():
            if isinstance(path, str) and isinstance(file_hash, str):
                normalized[path] = file_hash
        return normalized, True

    @classmethod
    def _detect_sync_conflict(
        cls,
        *,
        rel_path: str,
        target: Path,
        baseline_files: dict[str, str],
        baseline_loaded: bool,
    ) -> dict[str, Any] | None:
        if not baseline_loaded:
            return None

        baseline_exists = rel_path in baseline_files
        baseline_hash = baseline_files.get(rel_path, "")
        current_exists = target.exists() and target.is_file()
        current_hash = cls._sha256_file(target) if current_exists else ""

        conflict = False
        reason = ""
        if baseline_exists:
            if not current_exists:
                conflict = True
                reason = "主工作区文件在执行期间被删除。"
            elif current_hash != baseline_hash:
                conflict = True
                reason = "主工作区文件在执行期间已被修改。"
        elif current_exists:
            conflict = True
            reason = "主工作区文件在执行期间被新增。"

        if not conflict:
            return None

        return {
            "path": rel_path,
            "reason": reason,
            "baseline_exists": baseline_exists,
            "baseline_hash": baseline_hash,
            "current_exists": current_exists,
            "current_hash": current_hash,
        }

    def _build_prompt_registry(self) -> dict[str, PromptSpec]:
        registry: dict[str, PromptSpec] = {}
        for stage in STAGE_ORDER:
            prompt_file = self.config.agents[stage].prompt_file
            registry[stage] = load_prompt_spec(self.repo_root, prompt_file)
        return registry

    @staticmethod
    def _knowledge_to_dict(item: KnowledgeItem) -> dict[str, Any]:
        return {
            "path": item.path,
            "sha256": item.sha256,
            "chars": item.chars,
        }

    @staticmethod
    def _knowledge_to_context(item: KnowledgeItem) -> dict[str, Any]:
        return {
            "path": item.path,
            "sha256": item.sha256,
            "snippet": item.snippet,
        }

    @staticmethod
    def _write_knowledge_snapshot(run_dir: Path, knowledge_items: list[KnowledgeItem]) -> None:
        data = [
            {
                "path": item.path,
                "sha256": item.sha256,
                "chars": item.chars,
                "snippet": item.snippet,
            }
            for item in knowledge_items
        ]
        (run_dir / "knowledge_snapshot.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _write_prompt_registry(run_dir: Path, registry: dict[str, PromptSpec]) -> None:
        data = {
            stage: {
                "path": spec.path,
                "version": spec.version,
                "sha256": spec.sha256,
            }
            for stage, spec in registry.items()
        }
        (run_dir / "prompt_registry.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")






