from __future__ import annotations

import json
from pathlib import Path

from maestro_flow.config import AgentConfig, AppConfig, KnowledgeConfig, PolicyConfig, QualityGate, RollbackConfig, WorkflowConfig
from maestro_flow.contracts import FileChange
from maestro_flow.mock_data import mock_stage_output
from maestro_flow.orchestrator import DevFlowOrchestrator


def _write_prompts(repo: Path) -> None:
    base = repo / "agents" / "prompts"
    base.mkdir(parents=True, exist_ok=True)
    for stage in ["pm", "architect", "dev", "tester", "debugger", "reviewer"]:
        (base / f"{stage}.md").write_text("---\nversion: v1\n---\n测试提示词\n", encoding="utf-8")


def _build_config(repo: Path, *, max_fix_loops: int) -> AppConfig:
    _write_prompts(repo)
    agents = {
        stage: AgentConfig(name=f"{stage}-agent", prompt_file=f"agents/prompts/{stage}.md", temperature=0)
        for stage in ["pm", "architect", "dev", "tester", "debugger", "reviewer"]
    }
    return AppConfig(
        default_model="gpt-5.4-mini",
        agents=agents,
        quality_gates=[],
        workflow=WorkflowConfig(
            max_retries=0,
            parallel_workers=2,
            execution_enabled=True,
            max_fix_loops=max_fix_loops,
            command_timeout_seconds=30,
            allowed_execution_commands=["python -c"],
        ),
        rollback=RollbackConfig(enabled=False),
        knowledge=KnowledgeConfig(enabled=False),
        policy=PolicyConfig(enabled=False),
    )


class PassInOneRoundLLM:
    def complete_json(self, *, stage, agent, schema, requirement, context, prompt_text=""):
        output = mock_stage_output(stage, requirement)
        if stage == "dev":
            output.file_changes = [
                FileChange(
                    path="workspace/p6_loop.txt",
                    action="create",
                    purpose="创建测试文件",
                    content="good\n",
                )
            ]
            output.verification_commands = [
                "python -c \"import pathlib,sys; p=pathlib.Path('workspace/p6_loop.txt'); sys.exit(0 if p.exists() and p.read_text(encoding='utf-8').strip()=='good' else 1)\""
            ]
        if stage == "tester":
            output.run_commands = []
        return output


class NeedDebuggerFixLLM:
    def __init__(self):
        self.debugger_calls = 0

    def complete_json(self, *, stage, agent, schema, requirement, context, prompt_text=""):
        output = mock_stage_output(stage, requirement)
        if stage == "dev":
            output.file_changes = [
                FileChange(
                    path="workspace/p6_loop_fix.txt",
                    action="create",
                    purpose="首次写入错误内容",
                    content="bad\n",
                )
            ]
            output.verification_commands = [
                "python -c \"import pathlib,sys; p=pathlib.Path('workspace/p6_loop_fix.txt'); sys.exit(0 if p.exists() and p.read_text(encoding='utf-8').strip()=='good' else 1)\""
            ]
        if stage == "tester":
            output.run_commands = []
        if stage == "debugger":
            self.debugger_calls += 1
            output.file_changes = [
                FileChange(
                    path="workspace/p6_loop_fix.txt",
                    action="update",
                    purpose="修复内容",
                    content="good\n",
                )
            ]
            output.fix_commands = []
        return output


class ReviewerRefreshLLM:
    def __init__(self):
        self.reviewer_calls = 0

    def complete_json(self, *, stage, agent, schema, requirement, context, prompt_text=""):
        output = mock_stage_output(stage, requirement)
        if stage == "dev":
            output.file_changes = [
                FileChange(
                    path="workspace/p6_refresh.txt",
                    action="create",
                    purpose="创建测试文件",
                    content="ok\n",
                )
            ]
            output.verification_commands = [
                "python -c \"import pathlib,sys; p=pathlib.Path('workspace/p6_refresh.txt'); sys.exit(0 if p.exists() else 1)\""
            ]
        if stage == "tester":
            output.run_commands = []
        if stage == "reviewer":
            self.reviewer_calls += 1
            if self.reviewer_calls >= 2:
                output.verdict = "request_changes"
        return output


class DisallowedCommandLLM:
    def complete_json(self, *, stage, agent, schema, requirement, context, prompt_text=""):
        output = mock_stage_output(stage, requirement)
        if stage == "dev":
            output.file_changes = [
                FileChange(
                    path="workspace/p6_disallowed.txt",
                    action="create",
                    purpose="创建测试文件",
                    content="ok\n",
                )
            ]
            output.verification_commands = [
                "python -m maestro_flow.cli run --mock --requirement \"demo\""
            ]
        if stage == "tester":
            output.run_commands = []
        return output


class IsolatedWriteLLM:
    def complete_json(self, *, stage, agent, schema, requirement, context, prompt_text=""):
        output = mock_stage_output(stage, requirement)
        if stage == "dev":
            output.file_changes = [
                FileChange(
                    path="workspace/isolated_only.txt",
                    action="create",
                    purpose="验证隔离空间写入",
                    content="isolated\n",
                )
            ]
            output.verification_commands = [
                "python -c \"import pathlib,sys; p=pathlib.Path('workspace/isolated_only.txt'); sys.exit(0 if p.exists() else 1)\""
            ]
        if stage == "tester":
            output.run_commands = []
        return output


class IsolatedUpdateLLM:
    def complete_json(self, *, stage, agent, schema, requirement, context, prompt_text=""):
        output = mock_stage_output(stage, requirement)
        if stage == "dev":
            output.file_changes = [
                FileChange(
                    path="workspace/conflict_sync.txt",
                    action="update",
                    purpose="隔离执行中更新文件",
                    content="from_workspace\n",
                )
            ]
            output.verification_commands = [
                "python -c \"import pathlib,sys; p=pathlib.Path('workspace/conflict_sync.txt'); sys.exit(0 if p.exists() and p.read_text(encoding='utf-8').strip()=='from_workspace' else 1)\""
            ]
        if stage == "tester":
            output.run_commands = []
        return output


def test_execution_loop_succeeds_in_first_round(tmp_path: Path):
    repo = tmp_path
    config = _build_config(repo, max_fix_loops=2)

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=PassInOneRoundLLM(),
    )

    result = orch.run(
        requirement="验证执行闭环第一轮通过",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "succeeded"
    assert state["execution"]["status"] == "succeeded"
    assert state["execution"]["rounds"] == 1
    assert (repo / "workspace" / "p6_loop.txt").exists()
    assert (result.run_dir / "test_report_round_1.json").exists()


def test_execution_loop_uses_debugger_fix_and_succeeds(tmp_path: Path):
    repo = tmp_path
    config = _build_config(repo, max_fix_loops=2)
    llm = NeedDebuggerFixLLM()

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=llm,
    )

    result = orch.run(
        requirement="验证执行闭环通过 debugger 修复",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "succeeded"
    assert state["execution"]["status"] == "succeeded"
    assert state["execution"]["rounds"] == 2
    assert llm.debugger_calls >= 1
    assert (result.run_dir / "stage_debugger_loop_1.json").exists()


def test_execution_loop_refreshes_reviewer_after_success(tmp_path: Path):
    repo = tmp_path
    config = _build_config(repo, max_fix_loops=1)
    llm = ReviewerRefreshLLM()

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=llm,
    )

    result = orch.run(
        requirement="验证执行闭环后二次评审",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "succeeded"
    assert state["execution"]["reviewer_refresh"]["status"] == "succeeded"
    assert llm.reviewer_calls >= 2
    assert result.verdict == "request_changes"
    assert (result.run_dir / "stage_reviewer_post_execution.json").exists()


def test_execution_failure_still_writes_execution_policies(tmp_path: Path):
    repo = tmp_path
    config = _build_config(repo, max_fix_loops=1)
    config.workflow.allowed_execution_commands = ["python -m pytest"]
    config.policy.enabled = True
    llm = DisallowedCommandLLM()

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=llm,
    )

    result = orch.run(
        requirement="验证执行失败时策略报告仍可见",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    report = json.loads((result.run_dir / "policy_report.json").read_text(encoding="utf-8"))
    by_id = {item["policy_id"]: item for item in report}

    assert state["status"] == "failed"
    assert state["error_code"] == "EXECUTION_LOOP_FAILED"
    assert by_id["EXECUTION_COMMAND_ALLOWED"]["status"] == "fail"


def test_execution_loop_copy_workspace_does_not_modify_repo_root(tmp_path: Path):
    repo = tmp_path
    config = _build_config(repo, max_fix_loops=1)
    config.workflow.execution_workspace_mode = "copy"
    llm = IsolatedWriteLLM()

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=llm,
    )

    result = orch.run(
        requirement="验证 copy 隔离执行空间",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    workspace_info = state["execution"]["workspace"]
    isolated_file = Path(workspace_info["repo_root"]) / "workspace" / "isolated_only.txt"
    repo_file = repo / "workspace" / "isolated_only.txt"

    assert state["status"] == "succeeded"
    assert workspace_info["mode"] == "copy"
    assert isolated_file.exists()
    assert not repo_file.exists()


def test_execution_loop_copy_workspace_can_sync_back_on_success(tmp_path: Path):
    repo = tmp_path
    config = _build_config(repo, max_fix_loops=1)
    config.workflow.execution_workspace_mode = "copy"
    config.workflow.sync_back_on_success = True
    llm = IsolatedWriteLLM()

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=llm,
    )

    result = orch.run(
        requirement="验证 copy 隔离执行后回写主工作区",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    workspace_info = state["execution"]["workspace"]
    sync_back = state["execution"]["sync_back"]
    repo_file = repo / "workspace" / "isolated_only.txt"

    assert state["status"] == "succeeded"
    assert workspace_info["mode"] == "copy"
    assert sync_back["status"] == "succeeded"
    assert repo_file.exists()
    assert repo_file.read_text(encoding="utf-8").strip() == "isolated"
    assert (result.run_dir / "sync_back_report.json").exists()


def test_execution_loop_copy_workspace_sync_back_conflict_blocks_by_default(tmp_path: Path):
    repo = tmp_path
    (repo / "workspace").mkdir(parents=True, exist_ok=True)
    target_file = repo / "workspace" / "conflict_sync.txt"
    target_file.write_text("baseline\n", encoding="utf-8")

    config = _build_config(repo, max_fix_loops=1)
    config.workflow.execution_workspace_mode = "copy"
    config.workflow.sync_back_on_success = True
    config.quality_gates = [
        QualityGate(
            name="mutate-repo-after-execution",
            command="python -c \"import pathlib; p=pathlib.Path('workspace/conflict_sync.txt'); p.write_text('changed_in_repo\\n', encoding='utf-8')\"",
            required=False,
        )
    ]
    llm = IsolatedUpdateLLM()

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=llm,
    )

    result = orch.run(
        requirement="验证 copy 隔离执行回写冲突默认阻断",
        execute_quality_gates=True,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    sync_back = state["execution"]["sync_back"]

    assert state["status"] == "failed"
    assert state["error_code"] == "SYNC_BACK_FAILED"
    assert sync_back["status"] == "failed"
    assert sync_back["conflict_action"] == "block"
    assert sync_back["conflicts"]
    assert target_file.read_text(encoding="utf-8").strip() == "changed_in_repo"
    assert (result.run_dir / "sync_back_baseline.json").exists()


def test_execution_loop_copy_workspace_sync_back_conflict_can_overwrite(tmp_path: Path):
    repo = tmp_path
    (repo / "workspace").mkdir(parents=True, exist_ok=True)
    target_file = repo / "workspace" / "conflict_sync.txt"
    target_file.write_text("baseline\n", encoding="utf-8")

    config = _build_config(repo, max_fix_loops=1)
    config.workflow.execution_workspace_mode = "copy"
    config.workflow.sync_back_on_success = True
    config.workflow.sync_back_conflict_action = "overwrite"
    config.quality_gates = [
        QualityGate(
            name="mutate-repo-after-execution",
            command="python -c \"import pathlib; p=pathlib.Path('workspace/conflict_sync.txt'); p.write_text('changed_in_repo\\n', encoding='utf-8')\"",
            required=False,
        )
    ]
    llm = IsolatedUpdateLLM()

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=llm,
    )

    result = orch.run(
        requirement="验证 copy 隔离执行回写冲突可覆盖",
        execute_quality_gates=True,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    sync_back = state["execution"]["sync_back"]

    assert state["status"] == "succeeded"
    assert sync_back["status"] == "succeeded"
    assert sync_back["conflict_action"] == "overwrite"
    assert sync_back["conflicts_ignored"]
    assert target_file.read_text(encoding="utf-8").strip() == "from_workspace"
