from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maestro_flow.ci_ops import load_run_state

ALLOWED_DECISIONS = {"apply", "keep_local"}


def build_sync_plan_from_execution(execution_report: dict[str, Any]) -> dict[str, str]:
    latest_actions: dict[str, str] = {}
    for round_report in execution_report.get("reports", []):
        file_apply = round_report.get("file_apply", {})
        for item in file_apply.get("results", []):
            if str(item.get("status", "")).strip().lower() != "applied":
                continue
            path = str(item.get("path", "")).strip()
            action = str(item.get("action", "")).strip().lower()
            if path and action in {"create", "update", "delete"}:
                latest_actions[path] = action
    return latest_actions


def build_sync_decision_template(*, repo_root: Path, run_dir: Path) -> dict[str, Any]:
    state = load_run_state(run_dir)
    execution = state.get("execution", {})
    workspace = execution.get("workspace", {})
    workspace_mode = str(workspace.get("mode", ""))
    if workspace_mode != "copy":
        raise RuntimeError("当前运行不是 copy 隔离执行，不支持生成回写决策清单。")

    workspace_repo_root = Path(str(workspace.get("repo_root", "")))
    if not workspace_repo_root.exists():
        raise RuntimeError(f"隔离执行目录不存在: {workspace_repo_root}")

    baseline_snapshot = str(workspace.get("baseline_snapshot", "")).strip()
    if baseline_snapshot:
        baseline_path = Path(baseline_snapshot)
    else:
        baseline_path = run_dir / "sync_back_baseline.json"

    baseline_files, baseline_loaded = load_sync_back_baseline(baseline_path)
    plan = build_sync_plan_from_execution(execution)

    items: list[dict[str, Any]] = []
    for rel_path, action in sorted(plan.items()):
        target = (repo_root / rel_path).resolve()
        source = (workspace_repo_root / rel_path).resolve()
        _assert_within_root(repo_root=repo_root, target=target, rel_path=rel_path)
        _assert_within_root(repo_root=workspace_repo_root, target=source, rel_path=rel_path)

        conflict = detect_sync_conflict(
            rel_path=rel_path,
            target=target,
            baseline_files=baseline_files,
            baseline_loaded=baseline_loaded,
        )
        if conflict:
            recommended = "keep_local"
            reason = str(conflict.get("reason", "检测到冲突"))
        else:
            recommended = "apply"
            reason = "无冲突，建议回写。"

        if action in {"create", "update"} and (not source.exists() or not source.is_file()):
            recommended = "keep_local"
            reason = "隔离执行目录缺少源文件，无法回写。"

        items.append(
            {
                "path": rel_path,
                "action": action,
                "conflict": bool(conflict),
                "conflict_detail": conflict or {},
                "recommended": recommended,
                "decision": recommended,
                "reason": reason,
            }
        )

    return {
        "schema_version": "1.0",
        "run_id": run_dir.name,
        "generated_at": _now_iso(),
        "workspace_repo_root": str(workspace_repo_root),
        "baseline_snapshot": str(baseline_path),
        "baseline_loaded": baseline_loaded,
        "items": items,
    }


def apply_sync_decisions(
    *,
    repo_root: Path,
    run_dir: Path,
    decision_payload: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    state = load_run_state(run_dir)
    execution = state.get("execution", {})
    workspace = execution.get("workspace", {})
    workspace_repo_root = Path(str(workspace.get("repo_root", "")))
    if not workspace_repo_root.exists():
        raise RuntimeError(f"隔离执行目录不存在: {workspace_repo_root}")

    decision_by_path: dict[str, str] = {}
    for item in decision_payload.get("items", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        decision = str(item.get("decision", "")).strip().lower()
        if not path:
            continue
        if decision and decision not in ALLOWED_DECISIONS:
            raise RuntimeError(f"非法决策: path={path}, decision={decision}")
        decision_by_path[path] = decision or "keep_local"

    plan = build_sync_plan_from_execution(execution)
    applied: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    repo_root_resolved = repo_root.resolve()
    workspace_root_resolved = workspace_repo_root.resolve()
    for rel_path, action in sorted(plan.items()):
        decision = decision_by_path.get(rel_path, "keep_local")
        target = (repo_root / rel_path).resolve()
        source = (workspace_repo_root / rel_path).resolve()
        try:
            target.relative_to(repo_root_resolved)
            source.relative_to(workspace_root_resolved)
        except ValueError:
            failed.append({"path": rel_path, "action": action, "decision": decision, "message": "路径越界，拒绝执行。"})
            continue

        if decision != "apply":
            skipped.append({"path": rel_path, "action": action, "decision": decision, "message": "按决策保留主工作区版本。"})
            continue

        if action == "delete":
            if not target.exists():
                skipped.append({"path": rel_path, "action": action, "decision": decision, "message": "目标文件不存在，跳过删除。"})
                continue
            if not target.is_file():
                failed.append({"path": rel_path, "action": action, "decision": decision, "message": "目标路径不是文件，删除失败。"})
                continue
            if not dry_run:
                target.unlink()
            applied.append({"path": rel_path, "action": action, "decision": decision, "message": "已删除主工作区文件。"})
            continue

        if not source.exists() or not source.is_file():
            failed.append({"path": rel_path, "action": action, "decision": decision, "message": "隔离执行目录缺少源文件。"})
            continue

        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        applied.append({"path": rel_path, "action": action, "decision": decision, "message": "已按决策回写主工作区。"})

    status = "failed" if failed else "succeeded"
    return {
        "status": status,
        "dry_run": dry_run,
        "run_id": run_dir.name,
        "generated_at": _now_iso(),
        "applied": applied,
        "failed": failed,
        "skipped": skipped,
    }


def write_manual_sync_report(*, run_dir: Path, report: dict[str, Any]) -> Path:
    path = run_dir / "sync_back_manual_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_sync_decisions(*, output_file: Path, payload: dict[str, Any]) -> Path:
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_file


def load_sync_decisions(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"决策文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_sync_back_baseline(path: Path) -> tuple[dict[str, str], bool]:
    if not path.exists():
        return {}, False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, False
    files = payload.get("files", {}) if isinstance(payload, dict) else {}
    if not isinstance(files, dict):
        return {}, False
    result: dict[str, str] = {}
    for rel_path, file_hash in files.items():
        if isinstance(rel_path, str) and isinstance(file_hash, str):
            result[rel_path] = file_hash
    return result, True


def detect_sync_conflict(
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
    current_hash = sha256_file(target) if current_exists else ""

    conflict = False
    reason = ""
    if baseline_exists:
        if not current_exists:
            conflict = True
            reason = "主工作区文件在执行期间被删除。"
        elif baseline_hash != current_hash:
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


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _assert_within_root(*, repo_root: Path, target: Path, rel_path: str) -> None:
    try:
        target.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"路径越界: {rel_path}") from exc


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
