from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def ensure_git_repo(repo_root: Path) -> None:
    proc = _run(["git", "rev-parse", "--is-inside-work-tree"], repo_root)
    if proc.returncode != 0:
        raise RuntimeError("Current directory is not a git repository. Run: git init")


def finalize_commit(
    *,
    repo_root: Path,
    branch: str,
    commit_message: str,
) -> str:
    ensure_git_repo(repo_root)

    checkout = _run(["git", "checkout", "-B", branch], repo_root)
    if checkout.returncode != 0:
        raise RuntimeError(checkout.stderr.strip())

    add = _run(["git", "add", "."], repo_root)
    if add.returncode != 0:
        raise RuntimeError(add.stderr.strip())

    commit = _run(["git", "commit", "-m", commit_message], repo_root)
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr.strip() or commit.stdout.strip())

    head = _run(["git", "rev-parse", "HEAD"], repo_root)
    return head.stdout.strip()


def write_pr_body(*, run_dir: Path, output_file: Path) -> Path:
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    body = [
        "## What",
        "Automated multi-agent workflow output.",
        "",
        "## Run Artifacts",
        f"- Run directory: `{run_dir}`",
        "",
        "## Summary",
        summary,
    ]
    output_file.write_text("\n".join(body), encoding="utf-8")
    return output_file


def create_pr(*, repo_root: Path, title: str, body_file: Path, base: str = "main") -> str:
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI `gh` not found. Install it or create PR manually.")

    proc = _run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body-file",
            str(body_file),
            "--base",
            base,
        ],
        repo_root,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout.strip()

