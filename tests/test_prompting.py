from __future__ import annotations

import hashlib
from pathlib import Path

from maestro_flow.prompting import load_prompt_spec


def test_load_prompt_spec_with_front_matter(tmp_path: Path):
    repo_root = tmp_path
    prompt_file = repo_root / "agents" / "prompts" / "pm.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(
        "---\nversion: v2.1.0\nupdated_at: 2026-03-24\n---\n这是提示词正文。\n",
        encoding="utf-8",
    )

    spec = load_prompt_spec(repo_root, "agents/prompts/pm.md")

    assert spec.path == "agents/prompts/pm.md"
    assert spec.version == "v2.1.0"
    assert spec.content == "这是提示词正文。"
    assert spec.sha256 == hashlib.sha256("这是提示词正文。".encode("utf-8")).hexdigest()


def test_load_prompt_spec_without_front_matter(tmp_path: Path):
    repo_root = tmp_path
    prompt_file = repo_root / "agents" / "prompts" / "dev.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text("直接正文", encoding="utf-8")

    spec = load_prompt_spec(repo_root, "agents/prompts/dev.md")

    assert spec.version == "unversioned"
    assert spec.content == "直接正文"


def test_load_prompt_spec_supports_crlf_front_matter(tmp_path: Path):
    repo_root = tmp_path
    prompt_file = repo_root / "agents" / "prompts" / "reviewer.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(
        "---\r\nversion: v3.0.0\r\nupdated_at: 2026-03-24\r\n---\r\nWindows line endings\r\n",
        encoding="utf-8",
    )

    spec = load_prompt_spec(repo_root, "agents/prompts/reviewer.md")

    assert spec.version == "v3.0.0"
    assert spec.content == "Windows line endings"


def test_load_prompt_spec_supports_utf8_bom(tmp_path: Path):
    repo_root = tmp_path
    prompt_file = repo_root / "agents" / "prompts" / "pm.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_bytes(
        "---\r\nversion: v9.9.9\r\n---\r\nBOM content\r\n".encode("utf-8-sig")
    )

    spec = load_prompt_spec(repo_root, "agents/prompts/pm.md")

    assert spec.version == "v9.9.9"
    assert spec.content == "BOM content"
