from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PromptSpec:
    path: str
    version: str
    sha256: str
    content: str


def load_prompt_spec(repo_root: Path, prompt_path: str) -> PromptSpec:
    full_path = repo_root / prompt_path
    raw = full_path.read_text(encoding="utf-8")
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")
    version = "unversioned"
    body = raw

    front_matter = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", raw, flags=re.DOTALL)
    if front_matter:
        header_text = front_matter.group(1)
        body = front_matter.group(2)
        header = yaml.safe_load(header_text) or {}
        version = str(header.get("version", "unversioned"))

    body = body.strip()
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    rel = full_path.relative_to(repo_root).as_posix()
    return PromptSpec(path=rel, version=version, sha256=digest, content=body)
