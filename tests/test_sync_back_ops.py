from __future__ import annotations

import json
from pathlib import Path

from maestro_flow.sync_back_ops import apply_sync_decisions, build_sync_decision_template, sha256_file


def _write_run_state(
    *,
    run_dir: Path,
    workspace_repo_root: Path,
    baseline_snapshot: Path,
    file_path: str,
    action: str,
) -> None:
    state = {
        "status": "failed",
        "execution": {
            "workspace": {
                "mode": "copy",
                "repo_root": str(workspace_repo_root),
                "baseline_snapshot": str(baseline_snapshot),
            },
            "reports": [
                {
                    "round": 1,
                    "file_apply": {
                        "results": [
                            {
                                "path": file_path,
                                "action": action,
                                "status": "applied",
                            }
                        ]
                    },
                }
            ],
        },
    }
    (run_dir / "run_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_sync_decision_template_detects_conflict(tmp_path: Path):
    repo = tmp_path
    run_dir = repo / ".maestro" / "runs" / "r1"
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace_repo_root = run_dir / "exec_workspace"
    (workspace_repo_root / "workspace").mkdir(parents=True, exist_ok=True)
    (repo / "workspace").mkdir(parents=True, exist_ok=True)

    rel_path = "workspace/conflict.txt"
    target = repo / rel_path
    target.write_text("baseline\n", encoding="utf-8")
    baseline_snapshot = run_dir / "sync_back_baseline.json"
    baseline_snapshot.write_text(
        json.dumps(
            {"files": {rel_path: sha256_file(target)}},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    target.write_text("changed_in_repo\n", encoding="utf-8")
    (workspace_repo_root / rel_path).write_text("from_workspace\n", encoding="utf-8")
    _write_run_state(
        run_dir=run_dir,
        workspace_repo_root=workspace_repo_root,
        baseline_snapshot=baseline_snapshot,
        file_path=rel_path,
        action="update",
    )

    payload = build_sync_decision_template(repo_root=repo, run_dir=run_dir)
    assert payload["run_id"] == "r1"
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["path"] == rel_path
    assert item["conflict"] is True
    assert item["decision"] == "keep_local"


def test_apply_sync_decisions_keep_local_preserves_repo_file(tmp_path: Path):
    repo = tmp_path
    run_dir = repo / ".maestro" / "runs" / "r2"
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace_repo_root = run_dir / "exec_workspace"
    (workspace_repo_root / "workspace").mkdir(parents=True, exist_ok=True)
    (repo / "workspace").mkdir(parents=True, exist_ok=True)

    rel_path = "workspace/conflict.txt"
    target = repo / rel_path
    target.write_text("baseline\n", encoding="utf-8")
    baseline_snapshot = run_dir / "sync_back_baseline.json"
    baseline_snapshot.write_text(
        json.dumps({"files": {rel_path: sha256_file(target)}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    target.write_text("changed_in_repo\n", encoding="utf-8")
    (workspace_repo_root / rel_path).write_text("from_workspace\n", encoding="utf-8")
    _write_run_state(
        run_dir=run_dir,
        workspace_repo_root=workspace_repo_root,
        baseline_snapshot=baseline_snapshot,
        file_path=rel_path,
        action="update",
    )

    payload = build_sync_decision_template(repo_root=repo, run_dir=run_dir)
    payload["items"][0]["decision"] = "keep_local"
    report = apply_sync_decisions(repo_root=repo, run_dir=run_dir, decision_payload=payload)

    assert report["status"] == "succeeded"
    assert len(report["applied"]) == 0
    assert len(report["skipped"]) == 1
    assert target.read_text(encoding="utf-8").strip() == "changed_in_repo"


def test_apply_sync_decisions_apply_overwrites_repo_file(tmp_path: Path):
    repo = tmp_path
    run_dir = repo / ".maestro" / "runs" / "r3"
    run_dir.mkdir(parents=True, exist_ok=True)
    workspace_repo_root = run_dir / "exec_workspace"
    (workspace_repo_root / "workspace").mkdir(parents=True, exist_ok=True)
    (repo / "workspace").mkdir(parents=True, exist_ok=True)

    rel_path = "workspace/conflict.txt"
    target = repo / rel_path
    target.write_text("baseline\n", encoding="utf-8")
    baseline_snapshot = run_dir / "sync_back_baseline.json"
    baseline_snapshot.write_text(
        json.dumps({"files": {rel_path: sha256_file(target)}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    target.write_text("changed_in_repo\n", encoding="utf-8")
    (workspace_repo_root / rel_path).write_text("from_workspace\n", encoding="utf-8")
    _write_run_state(
        run_dir=run_dir,
        workspace_repo_root=workspace_repo_root,
        baseline_snapshot=baseline_snapshot,
        file_path=rel_path,
        action="update",
    )

    payload = build_sync_decision_template(repo_root=repo, run_dir=run_dir)
    payload["items"][0]["decision"] = "apply"
    report = apply_sync_decisions(repo_root=repo, run_dir=run_dir, decision_payload=payload)

    assert report["status"] == "succeeded"
    assert len(report["applied"]) == 1
    assert target.read_text(encoding="utf-8").strip() == "from_workspace"
