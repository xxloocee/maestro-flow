from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from maestro_flow.config import KnowledgeConfig


@dataclass(frozen=True)
class KnowledgeItem:
    path: str
    sha256: str
    chars: int
    snippet: str


def collect_knowledge(repo_root: Path, config: KnowledgeConfig) -> list[KnowledgeItem]:
    if not config.enabled:
        return []

    files: list[Path] = []
    for pattern in config.include_patterns:
        files.extend([p for p in repo_root.glob(pattern) if p.is_file()])

    # 去重并按路径稳定排序，保证同一仓库多次执行结果可复现。
    unique_files = sorted({p.resolve() for p in files})
    selected = unique_files[: config.max_files]

    items: list[KnowledgeItem] = []
    total_chars = 0
    for file_path in selected:
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not text.strip():
            continue

        raw_chars = len(text)
        snippet = text[: config.max_chars_per_file]
        if total_chars + len(snippet) > config.max_total_chars:
            remaining = config.max_total_chars - total_chars
            if remaining <= 0:
                break
            snippet = snippet[:remaining]

        total_chars += len(snippet)
        rel = file_path.relative_to(repo_root).as_posix()
        items.append(
            KnowledgeItem(
                path=rel,
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                chars=raw_chars,
                snippet=snippet,
            )
        )
        if total_chars >= config.max_total_chars:
            break

    return items
