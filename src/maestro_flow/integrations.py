from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class IntegrationTarget:
    name: str
    source_rel: str
    project_dest_rel: str
    user_dest_abs: str


INTEGRATION_TARGETS: dict[str, IntegrationTarget] = {
    "claude": IntegrationTarget(
        name="claude",
        source_rel="integrations/claude/.claude/commands",
        project_dest_rel=".claude/commands",
        user_dest_abs="~/.claude/commands",
    ),
    "cursor": IntegrationTarget(
        name="cursor",
        source_rel="integrations/cursor/.cursor/commands",
        project_dest_rel=".cursor/commands",
        user_dest_abs="~/.cursor/commands",
    ),
    "opencode": IntegrationTarget(
        name="opencode",
        source_rel="integrations/opencode/.opencode/commands",
        project_dest_rel=".opencode/commands",
        user_dest_abs="~/.config/opencode/commands",
    ),
    "codex": IntegrationTarget(
        name="codex",
        source_rel="integrations/codex/skills",
        project_dest_rel=".agents/skills",
        user_dest_abs="~/.agents/skills",
    ),
    "antigravity": IntegrationTarget(
        name="antigravity",
        source_rel="integrations/antigravity/.antigravity/commands",
        project_dest_rel=".antigravity/commands",
        user_dest_abs="~/.antigravity/commands",
    ),
}


def _expand_user_path(value: str) -> Path:
    if value.startswith("${CODEX_HOME:") and "}" in value:
        end = value.index("}")
        fallback = value[len("${CODEX_HOME:") : end]
        suffix = value[end + 1 :].lstrip("/\\")
        codex_home = os.getenv("CODEX_HOME", fallback)
        base = Path(os.path.expanduser(codex_home))
        return base / suffix if suffix else base
    return Path(os.path.expanduser(value))


def _copy_tree(src: Path, dst: Path) -> list[Path]:
    copied: list[Path] = []
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied.append(target)
    return copied


def install_integration(
    *,
    repo_root: Path,
    target: str,
    scope: str,
    destination_override: str | None = None,
    dry_run: bool = False,
) -> tuple[Path, list[Path]]:
    if target not in INTEGRATION_TARGETS:
        options = ", ".join(sorted(INTEGRATION_TARGETS.keys()))
        raise RuntimeError(f"Unknown integration target '{target}'. Supported: {options}")

    cfg = INTEGRATION_TARGETS[target]
    src = repo_root / cfg.source_rel
    if not src.exists():
        raise RuntimeError(f"Integration source not found: {src}")

    if destination_override:
        dst = Path(destination_override).expanduser()
        if not dst.is_absolute():
            dst = (repo_root / dst).resolve()
    elif scope == "project":
        dst = repo_root / cfg.project_dest_rel
    elif scope == "user":
        dst = _expand_user_path(cfg.user_dest_abs)
    else:
        raise RuntimeError("scope must be 'project' or 'user'")

    if dry_run:
        planned = [dst / p.relative_to(src) for p in src.rglob("*") if p.is_file()]
        return dst, planned

    copied = _copy_tree(src, dst)
    return dst, copied


def init_spec_file(repo_root: Path, name: str) -> Path:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    slug = "-".join(x for x in slug.split("-") if x) or "spec"
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    path = repo_root / ".maestro" / "specs" / f"{ts}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"# Spec: {name}\n\n"
        "## Problem\n"
        "- What user problem is being solved?\n\n"
        "## Scope\n"
        "- In scope:\n"
        "- Out of scope:\n\n"
        "## Acceptance Criteria\n"
        "- [ ] Criterion 1\n"
        "- [ ] Criterion 2\n\n"
        "## Technical Constraints\n"
        "- Architecture constraints:\n"
        "- Performance/Security constraints:\n\n"
        "## Plan\n"
        "1. Task breakdown\n"
        "2. Implementation sequence\n"
        "3. Test strategy\n\n"
        "## Review Checklist\n"
        "- [ ] Tests pass\n"
        "- [ ] No critical findings\n"
        "- [ ] Ready to merge\n"
    )
    path.write_text(content, encoding="utf-8")
    return path
