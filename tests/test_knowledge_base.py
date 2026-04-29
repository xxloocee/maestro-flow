from __future__ import annotations

from pathlib import Path

from maestro_flow.config import KnowledgeConfig
from maestro_flow.knowledge_base import collect_knowledge


def test_collect_knowledge_respects_limits_and_dedup(tmp_path: Path):
    repo_root = tmp_path
    (repo_root / "README.md").write_text("R" * 20, encoding="utf-8")
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs" / "a.md").write_text("A" * 30, encoding="utf-8")
    (repo_root / "docs" / "b.md").write_text("B" * 30, encoding="utf-8")

    cfg = KnowledgeConfig(
        enabled=True,
        include_patterns=["README.md", "docs/*.md", "docs/a.md"],
        max_files=2,
        max_chars_per_file=12,
        max_total_chars=20,
    )

    items = collect_knowledge(repo_root, cfg)

    assert len(items) == 2
    assert len({item.path for item in items}) == 2
    assert sum(len(item.snippet) for item in items) <= 20
    assert all(len(item.snippet) <= 12 for item in items)


def test_collect_knowledge_disabled_returns_empty(tmp_path: Path):
    repo_root = tmp_path
    (repo_root / "README.md").write_text("abc", encoding="utf-8")

    items = collect_knowledge(repo_root, KnowledgeConfig(enabled=False))

    assert items == []
