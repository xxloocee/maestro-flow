from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COMMENT_MARKER = "<!-- maestro-flow:report -->"


@dataclass(frozen=True)
class GateEvaluation:
    passed: bool
    run_status: str
    reviewer_verdict: str
    reasons: list[str]
    reason_codes: list[str]
    blocking_policy_failures: list[dict[str, Any]]


def resolve_run_dir(repo_root: Path, run_id: str = "") -> Path:
    runs_dir = repo_root / ".maestro" / "runs"
    if run_id:
        run_dir = runs_dir / run_id
        if not run_dir.exists():
            raise RuntimeError(f"run directory not found: {run_dir}")
        return run_dir

    if not runs_dir.exists():
        raise RuntimeError(f"runs directory not found: {runs_dir}")

    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        raise RuntimeError(f"no run directories found in: {runs_dir}")
    return max(candidates, key=lambda x: x.stat().st_mtime)


def load_run_state(run_dir: Path) -> dict[str, Any]:
    state_file = run_dir / "run_state.json"
    if not state_file.exists():
        raise RuntimeError(f"run_state.json not found: {state_file}")
    return json.loads(state_file.read_text(encoding="utf-8"))


def load_reviewer_output(run_dir: Path) -> dict[str, Any]:
    preferred = run_dir / "stage_reviewer.json"
    fallback = run_dir / "06_reviewer.json"
    if preferred.exists():
        return json.loads(preferred.read_text(encoding="utf-8"))
    if fallback.exists():
        return json.loads(fallback.read_text(encoding="utf-8"))
    return {}


def load_policy_report(run_dir: Path) -> list[dict[str, Any]]:
    report_file = run_dir / "policy_report.json"
    if not report_file.exists():
        return []

    data = json.loads(report_file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError(f"invalid policy report format: {report_file}")

    normalized: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def evaluate_run(
    *,
    state: dict[str, Any],
    reviewer: dict[str, Any],
    policy_results: list[dict[str, Any]] | None = None,
    fail_on_conditions: bool = False,
    fail_on_blocking_policies: bool = True,
) -> GateEvaluation:
    reasons: list[str] = []
    reason_codes: list[str] = []
    run_status = str(state.get("status", "unknown"))
    verdict = str(reviewer.get("verdict", "unknown"))
    policy_results = policy_results or []
    blocking_policy_failures = [
        item
        for item in policy_results
        if str(item.get("status", "")).lower() == "fail" and bool(item.get("blocking", False))
    ]

    if run_status != "succeeded":
        reason_codes.append("RUN_STATUS_NOT_SUCCEEDED")
        reasons.append(f"run_status={run_status}")
    if verdict == "request_changes":
        reason_codes.append("REVIEWER_REQUEST_CHANGES")
        reasons.append("reviewer_verdict=request_changes")
    if fail_on_conditions and reviewer.get("merge_conditions"):
        reason_codes.append("REVIEWER_MERGE_CONDITIONS_PRESENT")
        reasons.append("reviewer_merge_conditions_present")
    if fail_on_blocking_policies and blocking_policy_failures:
        reason_codes.append("POLICY_BLOCKING_FAILURE")
        policy_ids = ",".join(str(item.get("policy_id", "unknown")) for item in blocking_policy_failures)
        reasons.append(f"policy_blocking_failure={policy_ids}")

    return GateEvaluation(
        passed=len(reasons) == 0,
        run_status=run_status,
        reviewer_verdict=verdict,
        reasons=reasons,
        reason_codes=reason_codes,
        blocking_policy_failures=blocking_policy_failures,
    )


def build_pr_comment(
    *,
    run_id: str,
    run_dir: Path,
    state: dict[str, Any],
    reviewer: dict[str, Any],
    evaluation: GateEvaluation,
    policy_results: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        COMMENT_MARKER,
        "## Maestro Flow 报告",
        "",
        f"- 运行 ID: `{run_id}`",
        f"- 运行状态: `{evaluation.run_status}`",
        f"- 评审结论: `{evaluation.reviewer_verdict}`",
        f"- 门禁结果: `{'PASS' if evaluation.passed else 'FAIL'}`",
        f"- 产物目录: `{run_dir}`",
        "",
        "### 阻断摘要",
    ]
    if evaluation.blocking_policy_failures:
        lines.append(f"- 阻断策略失败数: `{len(evaluation.blocking_policy_failures)}`")
        for item in evaluation.blocking_policy_failures:
            lines.append(f"- `{item.get('policy_id', 'unknown')}`: {item.get('message', '')}")
    else:
        lines.append("- 阻断策略失败数: `0`")

    lines.extend(
        [
            "",
            "### 阶段状态",
        ]
    )

    stages = state.get("stages", {})
    for stage in sorted(stages.keys()):
        st = stages[stage]
        lines.append(
            f"- `{stage}`: `{st.get('status', 'unknown')}` (attempts={st.get('attempts', 0)}/{st.get('max_attempts', 0)})"
        )

    findings = reviewer.get("findings", [])
    lines.extend(["", "### 评审发现"])
    if not findings:
        lines.append("- 无")
    else:
        for f in findings:
            sev = f.get("severity", "unknown")
            finding = f.get("finding", "")
            file_ref = f.get("file_ref", "")
            lines.append(f"- [{sev}] {finding} ({file_ref})")

    conditions = reviewer.get("merge_conditions", [])
    lines.extend(["", "### 合并条件"])
    if not conditions:
        lines.append("- 无")
    else:
        for c in conditions:
            lines.append(f"- {c}")

    lines.extend(["", "### 策略门禁"])
    policies = policy_results or []
    if not policies:
        lines.append("- 无 policy_report.json 或策略结果为空")
    else:
        for item in policies:
            policy_id = item.get("policy_id", "unknown")
            status = item.get("status", "unknown")
            blocking = item.get("blocking", False)
            message = item.get("message", "")
            lines.append(f"- `{policy_id}`: `{status}` (blocking={blocking}) | {message}")

    if evaluation.reason_codes:
        lines.extend(["", "### 门禁失败原因码"])
        for code in evaluation.reason_codes:
            lines.append(f"- `{code}`")

    if evaluation.reasons:
        lines.extend(["", "### 门禁失败原因"])
        for r in evaluation.reasons:
            lines.append(f"- {r}")

    return "\n".join(lines) + "\n"


def write_pr_comment_file(*, output_file: Path, body: str) -> Path:
    output_file.write_text(body, encoding="utf-8")
    return output_file


def post_or_update_pr_comment(
    *,
    repo_root: Path,
    pr_number: int,
    body_file: Path,
) -> str:
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI `gh` not found.")

    proc = subprocess.run(
        [
            "gh",
            "pr",
            "comment",
            str(pr_number),
            "--body-file",
            str(body_file),
            "--edit-last",
            "--create-if-none",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout.strip()
