from __future__ import annotations

import difflib
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CommandExecutionResult:
    command: str
    allowed: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    warnings: list[str]


@dataclass(frozen=True)
class CommandAccessDecision:
    allowed: bool
    warnings: list[str]
    block_reasons: list[str]


@dataclass(frozen=True)
class FileChangeApplyResult:
    path: str
    action: str
    status: str
    message: str


def run_commands(
    *,
    repo_root: Path,
    commands: list[str],
    allowed_prefixes: list[str],
    command_policies: list[Any] | None = None,
    unmatched_action: str = "block",
    blocked_fragments: list[str] | None = None,
    timeout_seconds: int,
) -> list[CommandExecutionResult]:
    results: list[CommandExecutionResult] = []
    for command in commands:
        decision = evaluate_command_access(
            command=command,
            allowed_prefixes=allowed_prefixes,
            command_policies=command_policies,
            unmatched_action=unmatched_action,
            blocked_fragments=blocked_fragments,
        )
        if not decision.allowed:
            results.append(
                CommandExecutionResult(
                    command=command,
                    allowed=False,
                    exit_code=126,
                    stdout="",
                    stderr="\n".join(decision.block_reasons) or "命令不在允许列表中。",
                    timed_out=False,
                    warnings=decision.warnings,
                )
            )
            continue

        try:
            proc = subprocess.run(
                command,
                cwd=repo_root,
                shell=True,
                capture_output=True,
                text=True,
                timeout=max(1, timeout_seconds),
            )
            results.append(
                CommandExecutionResult(
                    command=command,
                    allowed=True,
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    timed_out=False,
                    warnings=decision.warnings,
                )
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                CommandExecutionResult(
                    command=command,
                    allowed=True,
                    exit_code=124,
                    stdout=exc.stdout or "",
                    stderr=(exc.stderr or "") + "\n命令执行超时。",
                    timed_out=True,
                    warnings=decision.warnings,
                )
            )

    return results


def evaluate_command_access(
    *,
    command: str,
    allowed_prefixes: list[str],
    command_policies: list[Any] | None,
    unmatched_action: str,
    blocked_fragments: list[str] | None = None,
) -> CommandAccessDecision:
    normalized = command.strip().lower()
    if not normalized:
        return CommandAccessDecision(
            allowed=False,
            warnings=[],
            block_reasons=["命令为空，拒绝执行。"],
        )

    for fragment in blocked_fragments or []:
        frag = str(fragment).strip().lower()
        if frag and frag in normalized:
            return CommandAccessDecision(
                allowed=False,
                warnings=[],
                block_reasons=[f"命中危险命令片段，拒绝执行: {fragment}"],
            )

    policies = command_policies or []
    if policies:
        return _evaluate_policy_based_access(command=command, normalized=normalized, policies=policies, unmatched_action=unmatched_action)

    for prefix in allowed_prefixes:
        if normalized.startswith(prefix.strip().lower()):
            return CommandAccessDecision(allowed=True, warnings=[], block_reasons=[])

    return CommandAccessDecision(
        allowed=False,
        warnings=[],
        block_reasons=["命令不在允许前缀列表中。"],
    )


def is_command_allowed(
    command: str,
    allowed_prefixes: list[str],
    command_policies: list[Any] | None = None,
    unmatched_action: str = "block",
    blocked_fragments: list[str] | None = None,
) -> bool:
    decision = evaluate_command_access(
        command=command,
        allowed_prefixes=allowed_prefixes,
        command_policies=command_policies,
        unmatched_action=unmatched_action,
        blocked_fragments=blocked_fragments,
    )
    return decision.allowed


def _evaluate_policy_based_access(
    *,
    command: str,
    normalized: str,
    policies: list[Any],
    unmatched_action: str,
) -> CommandAccessDecision:
    tokens = _tokenize_command(command)
    matched_any = False
    warnings: list[str] = []
    block_reasons: list[str] = []

    for policy in policies:
        if not bool(_policy_get(policy, "enabled", True)):
            continue

        mode = str(_policy_get(policy, "mode", "prefix")).strip().lower()
        pattern = str(_policy_get(policy, "pattern", "")).strip()
        if not pattern:
            continue

        if not _matches_policy_pattern(mode=mode, pattern=pattern, command=command, normalized=normalized):
            continue

        matched_any = True
        description = str(_policy_get(policy, "description", "")).strip()
        desc_prefix = f"[{description}] " if description else ""

        required_args = _policy_get(policy, "required_args", []) or []
        forbidden_args = _policy_get(policy, "forbidden_args", []) or []

        for arg in required_args:
            arg_text = str(arg).strip()
            if arg_text and not _has_arg(tokens=tokens, expected=arg_text):
                message = f"{desc_prefix}缺少必需参数: {arg_text}"
                if str(_policy_get(policy, "missing_required_action", "block")) == "warn":
                    warnings.append(message)
                else:
                    block_reasons.append(message)

        for arg in forbidden_args:
            arg_text = str(arg).strip()
            if arg_text and _has_arg(tokens=tokens, expected=arg_text):
                message = f"{desc_prefix}命中禁止参数: {arg_text}"
                if str(_policy_get(policy, "forbidden_arg_action", "block")) == "warn":
                    warnings.append(message)
                else:
                    block_reasons.append(message)

    if not matched_any:
        if str(unmatched_action).strip().lower() == "warn":
            return CommandAccessDecision(
                allowed=True,
                warnings=["未命中任何命令策略，按 warn 放行。"],
                block_reasons=[],
            )
        return CommandAccessDecision(
            allowed=False,
            warnings=[],
            block_reasons=["未命中任何命令策略，按 block 拒绝执行。"],
        )

    return CommandAccessDecision(
        allowed=len(block_reasons) == 0,
        warnings=warnings,
        block_reasons=block_reasons,
    )


def _matches_policy_pattern(*, mode: str, pattern: str, command: str, normalized: str) -> bool:
    if mode == "prefix":
        return normalized.startswith(pattern.lower())
    if mode == "regex":
        try:
            return re.search(pattern, command) is not None
        except re.error:
            return False
    return False


def _tokenize_command(command: str) -> list[str]:
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    return [token.strip() for token in tokens if token.strip()]


def _has_arg(*, tokens: list[str], expected: str) -> bool:
    expected_norm = expected.lower()
    for token in tokens:
        token_norm = token.lower()
        if token_norm == expected_norm:
            return True
        if expected_norm.startswith("--") and token_norm.startswith(f"{expected_norm}="):
            return True
    return False


def _policy_get(policy: Any, key: str, default: Any) -> Any:
    if isinstance(policy, dict):
        return policy.get(key, default)
    return getattr(policy, key, default)


def apply_file_changes(
    *,
    repo_root: Path,
    file_changes: list[dict[str, Any]],
    run_dir: Path,
    round_index: int,
) -> dict[str, Any]:
    repo_root_resolved = repo_root.resolve()
    patch_chunks: list[str] = []
    results: list[FileChangeApplyResult] = []

    for item in file_changes:
        rel_path = str(item.get("path", "")).strip()
        action = str(item.get("action", "")).strip().lower()
        content = str(item.get("content", ""))
        if not rel_path or action not in {"create", "update", "delete"}:
            results.append(
                FileChangeApplyResult(
                    path=rel_path or "<empty>",
                    action=action or "<empty>",
                    status="skipped",
                    message="缺少 path/action 或 action 非法。",
                )
            )
            continue

        target = (repo_root / rel_path).resolve()
        try:
            target.relative_to(repo_root_resolved)
        except ValueError:
            results.append(
                FileChangeApplyResult(
                    path=rel_path,
                    action=action,
                    status="skipped",
                    message="路径越界，已拒绝写入。",
                )
            )
            continue

        before = ""
        if target.exists() and target.is_file():
            before = target.read_text(encoding="utf-8")

        if action in {"create", "update"}:
            if not content:
                results.append(
                    FileChangeApplyResult(
                        path=rel_path,
                        action=action,
                        status="skipped",
                        message="create/update 缺少 content，未应用。",
                    )
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            after = content
            status = "applied"
            message = "已写入文件内容。"
        else:
            if target.exists():
                target.unlink()
                after = ""
                status = "applied"
                message = "已删除文件。"
            else:
                after = ""
                status = "skipped"
                message = "文件不存在，跳过删除。"

        if status == "applied":
            diff = "".join(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                )
            )
            if diff:
                patch_chunks.append(diff)

        results.append(
            FileChangeApplyResult(
                path=rel_path,
                action=action,
                status=status,
                message=message,
            )
        )

    patch_file = run_dir / f"fix_round_{round_index}.patch"
    if patch_chunks:
        patch_file.write_text("\n".join(patch_chunks), encoding="utf-8")

    payload = {
        "round": round_index,
        "applied_count": sum(1 for r in results if r.status == "applied"),
        "skipped_count": sum(1 for r in results if r.status == "skipped"),
        "patch_file": str(patch_file) if patch_chunks else "",
        "results": [
            {
                "path": r.path,
                "action": r.action,
                "status": r.status,
                "message": r.message,
            }
            for r in results
        ],
    }
    (run_dir / f"file_apply_round_{round_index}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload
