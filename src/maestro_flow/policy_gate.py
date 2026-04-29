from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from maestro_flow.config import PolicyConfig, PolicyRuleOverride


@dataclass(frozen=True)
class PolicyResult:
    policy_id: str
    status: str
    blocking: bool
    message: str


def evaluate_policies(
    stage_outputs: dict[str, Any],
    config: PolicyConfig,
    repo_root: Path | None = None,
) -> list[PolicyResult]:
    if not config.enabled:
        return [
            PolicyResult(
                policy_id="POLICY_DISABLED",
                status="skipped",
                blocking=False,
                message="策略门禁已关闭。",
            )
        ]

    results: list[PolicyResult] = []
    results.extend(_evaluate_builtin_policies(stage_outputs, config))
    results.extend(_evaluate_plugin_policies(stage_outputs, config, repo_root))

    if not results:
        return [
            PolicyResult(
                policy_id="POLICY_EMPTY",
                status="skipped",
                blocking=False,
                message="未配置可执行的策略规则。",
            )
        ]

    return results


def _evaluate_builtin_policies(stage_outputs: dict[str, Any], config: PolicyConfig) -> list[PolicyResult]:
    results: list[PolicyResult] = []
    has_override = config.rules

    if _is_rule_enabled("TESTER_CASES_REQUIRED", has_override) and (
        config.require_tester_cases or "TESTER_CASES_REQUIRED" in has_override
    ):
        tester_cases = stage_outputs.get("tester", {}).get("test_cases", [])
        ok = len(tester_cases) > 0
        results.append(
            PolicyResult(
                policy_id="TESTER_CASES_REQUIRED",
                status="pass" if ok else "fail",
                blocking=True,
                message="测试阶段必须提供至少一个测试用例。",
            )
        )

    if _is_rule_enabled("DEV_VERIFY_COMMAND_REQUIRED", has_override) and (
        config.require_dev_verification_commands or "DEV_VERIFY_COMMAND_REQUIRED" in has_override
    ):
        dev_cmds = stage_outputs.get("dev", {}).get("verification_commands", [])
        ok = len(dev_cmds) > 0
        results.append(
            PolicyResult(
                policy_id="DEV_VERIFY_COMMAND_REQUIRED",
                status="pass" if ok else "fail",
                blocking=True,
                message="开发阶段必须提供本地验证命令。",
            )
        )

    if _is_rule_enabled("DEV_FILE_CHANGES_LIMIT", has_override):
        file_changes = stage_outputs.get("dev", {}).get("file_changes", [])
        ok = len(file_changes) <= config.max_dev_file_changes
        results.append(
            PolicyResult(
                policy_id="DEV_FILE_CHANGES_LIMIT",
                status="pass" if ok else "fail",
                blocking=True,
                message=f"开发阶段变更文件数必须小于等于 {config.max_dev_file_changes}。",
            )
        )

    if _is_rule_enabled("REVIEWER_NO_CRITICAL", has_override) and (
        config.block_on_critical_review or "REVIEWER_NO_CRITICAL" in has_override
    ):
        findings = stage_outputs.get("reviewer", {}).get("findings", [])
        has_critical = any(str(f.get("severity", "")).lower() == "critical" for f in findings)
        results.append(
            PolicyResult(
                policy_id="REVIEWER_NO_CRITICAL",
                status="fail" if has_critical else "pass",
                blocking=True,
                message="评审结果中不得包含 critical 级别问题。",
            )
        )

    if _is_rule_enabled("SECURITY_SECRET_PATTERN_SCAN", has_override):
        flattened = json.dumps(stage_outputs, ensure_ascii=False)
        secret_hit = any(re.search(pattern, flattened) for pattern in config.secret_patterns)
        results.append(
            PolicyResult(
                policy_id="SECURITY_SECRET_PATTERN_SCAN",
                status="fail" if secret_hit else "pass",
                blocking=True,
                message="输出中不得出现疑似密钥或口令信息。",
            )
        )

    return [_apply_rule_override(result, config.rules) for result in results]


def _evaluate_plugin_policies(
    stage_outputs: dict[str, Any],
    config: PolicyConfig,
    repo_root: Path | None,
) -> list[PolicyResult]:
    results: list[PolicyResult] = []
    for entry in config.plugin_entrypoints:
        try:
            plugin_callable = _load_plugin_callable(entry, repo_root)
        except Exception as exc:
            results.append(
                PolicyResult(
                    policy_id=f"PLUGIN_LOAD::{entry}",
                    status="fail",
                    blocking=True,
                    message=f"插件加载失败：{exc}",
                )
            )
            continue

        try:
            raw = _run_plugin(plugin_callable, stage_outputs, config, repo_root)
            normalized = _normalize_plugin_output(entry, raw)
            results.extend([_apply_rule_override(item, config.rules) for item in normalized])
        except Exception as exc:
            results.append(
                PolicyResult(
                    policy_id=f"PLUGIN_EXEC::{entry}",
                    status="fail",
                    blocking=True,
                    message=f"插件执行失败：{exc}",
                )
            )
    return results


def _is_rule_enabled(policy_id: str, overrides: dict[str, PolicyRuleOverride]) -> bool:
    override = overrides.get(policy_id)
    if override is None:
        return True
    return override.enabled


def _apply_rule_override(result: PolicyResult, overrides: dict[str, PolicyRuleOverride]) -> PolicyResult:
    override = overrides.get(result.policy_id)
    if override is None:
        return result
    blocking = result.blocking if override.blocking is None else override.blocking
    message = override.message.strip() or result.message
    return PolicyResult(
        policy_id=result.policy_id,
        status=result.status,
        blocking=blocking,
        message=message,
    )


def _load_plugin_callable(
    entrypoint: str,
    repo_root: Path | None,
) -> Callable[..., Any]:
    if ":" not in entrypoint:
        raise ValueError("入口格式必须为 `module:function` 或 `path.py:function`。")

    target, symbol = entrypoint.rsplit(":", 1)
    symbol = symbol.strip()
    target = target.strip()
    if not symbol:
        raise ValueError("入口函数名不能为空。")

    module: Any
    if target.endswith(".py") or "/" in target or "\\" in target:
        file_path = Path(target)
        if not file_path.is_absolute():
            if repo_root is None:
                raise ValueError("路径型插件需要提供 repo_root。")
            file_path = (repo_root / file_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"插件文件不存在：{file_path}")

        module_name = f"maestro_policy_plugin_{abs(hash(str(file_path)))}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载插件模块：{file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(target)

    plugin_callable = getattr(module, symbol, None)
    if not callable(plugin_callable):
        raise TypeError(f"插件入口不是可调用对象：{entrypoint}")
    return plugin_callable


def _run_plugin(
    plugin_callable: Callable[..., Any],
    stage_outputs: dict[str, Any],
    config: PolicyConfig,
    repo_root: Path | None,
) -> Any:
    sig = inspect.signature(plugin_callable)
    params = sig.parameters
    if "stage_outputs" in params and "config" in params:
        if "repo_root" in params:
            return plugin_callable(stage_outputs=stage_outputs, config=config, repo_root=repo_root)
        return plugin_callable(stage_outputs=stage_outputs, config=config)
    return plugin_callable(stage_outputs, config)


def _normalize_plugin_output(entrypoint: str, raw: Any) -> list[PolicyResult]:
    if isinstance(raw, PolicyResult):
        return [raw]
    if isinstance(raw, dict):
        return [_dict_to_policy_result(entrypoint, raw)]
    if isinstance(raw, list):
        results: list[PolicyResult] = []
        for item in raw:
            if isinstance(item, PolicyResult):
                results.append(item)
            elif isinstance(item, dict):
                results.append(_dict_to_policy_result(entrypoint, item))
            else:
                raise TypeError("插件返回列表仅支持 PolicyResult 或 dict 元素。")
        return results
    raise TypeError("插件返回值必须是 PolicyResult、dict 或它们的列表。")


def _dict_to_policy_result(entrypoint: str, data: dict[str, Any]) -> PolicyResult:
    policy_id = str(data.get("policy_id", "")).strip()
    status = str(data.get("status", "")).strip()
    if not policy_id or not status:
        raise ValueError(f"插件 {entrypoint} 缺少 policy_id 或 status 字段。")

    blocking_raw = data.get("blocking", True)
    blocking = bool(blocking_raw)
    message = str(data.get("message", "")).strip() or "插件未提供说明。"
    return PolicyResult(policy_id=policy_id, status=status, blocking=blocking, message=message)


def persist_policy_report(run_dir: Path, results: list[PolicyResult]) -> Path:
    data = [
        {
            "policy_id": r.policy_id,
            "status": r.status,
            "blocking": r.blocking,
            "message": r.message,
        }
        for r in results
    ]
    report_file = run_dir / "policy_report.json"
    report_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_file


def evaluate_execution_policies(
    execution_report: dict[str, Any],
    overrides: dict[str, PolicyRuleOverride] | None = None,
) -> list[PolicyResult]:
    if not execution_report:
        return []

    overrides = overrides or {}
    command_items: list[dict[str, Any]] = []
    for round_report in execution_report.get("reports", []):
        for key in ("fix_commands", "verify_commands"):
            for item in round_report.get(key, []):
                if isinstance(item, dict):
                    command_items.append(item)

    if not command_items:
        return []

    blocked = [item for item in command_items if item.get("allowed") is False]
    timed_out = [item for item in command_items if bool(item.get("timed_out", False))]
    warnings: list[str] = []
    for item in command_items:
        for warning in item.get("warnings", []) or []:
            warnings.append(str(warning))

    results = [
        PolicyResult(
            policy_id="EXECUTION_COMMAND_ALLOWED",
            status="fail" if blocked else "pass",
            blocking=True,
            message="存在未被命令策略放行的执行命令。"
            if blocked
            else "执行命令均通过策略放行。",
        ),
        PolicyResult(
            policy_id="EXECUTION_COMMAND_TIMEOUT",
            status="fail" if timed_out else "pass",
            blocking=True,
            message=f"检测到 {len(timed_out)} 条命令执行超时。"
            if timed_out
            else "执行命令未发生超时。",
        ),
        PolicyResult(
            policy_id="EXECUTION_COMMAND_WARNINGS",
            status="fail" if warnings else "pass",
            blocking=False,
            message=f"检测到 {len(warnings)} 条命令策略告警。"
            if warnings
            else "未检测到命令策略告警。",
        ),
    ]
    return [_apply_rule_override(result, overrides) for result in results]


def has_blocking_failure(results: list[PolicyResult]) -> bool:
    return any(r.blocking and r.status == "fail" for r in results)
