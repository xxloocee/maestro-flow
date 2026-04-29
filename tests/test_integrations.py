from pathlib import Path

from maestro_flow.integrations import init_spec_file, install_integration


def test_install_integration_dry_run():
    repo_root = Path.cwd()
    dst, files = install_integration(
        repo_root=repo_root,
        target="opencode",
        scope="project",
        dry_run=True,
    )
    assert str(dst).endswith(".opencode\\commands") or str(dst).endswith(".opencode/commands")
    assert any("maestro-spec.md" in str(f) for f in files)


def test_install_claude_dry_run():
    repo_root = Path.cwd()
    dst, files = install_integration(
        repo_root=repo_root,
        target="claude",
        scope="project",
        dry_run=True,
    )
    assert str(dst).endswith(".claude\\commands") or str(dst).endswith(".claude/commands")
    assert any("maestro-spec.md" in str(f) for f in files)
    assert any("maestro-run.md" in str(f) for f in files)


def test_install_cursor_dry_run():
    repo_root = Path.cwd()
    dst, files = install_integration(
        repo_root=repo_root,
        target="cursor",
        scope="project",
        dry_run=True,
    )
    assert str(dst).endswith(".cursor\\commands") or str(dst).endswith(".cursor/commands")
    assert any("maestro-spec.md" in str(f) for f in files)
    assert any("maestro-run.md" in str(f) for f in files)


def test_install_antigravity_dry_run():
    repo_root = Path.cwd()
    dst, files = install_integration(
        repo_root=repo_root,
        target="antigravity",
        scope="user",
        dry_run=True,
    )
    assert str(dst).endswith(".antigravity\\commands") or str(dst).endswith(".antigravity/commands")
    assert any("maestro-run.md" in str(f) for f in files)


def test_install_codex_dry_run_contains_default_skills():
    repo_root = Path.cwd()
    dst, files = install_integration(
        repo_root=repo_root,
        target="codex",
        scope="project",
        dry_run=True,
    )
    assert str(dst).endswith(".agents\\skills") or str(dst).endswith(".agents/skills")
    assert any("maestro-spec" in str(f) for f in files)
    assert any("maestro-run" in str(f) for f in files)


def test_init_spec_file_creates_markdown():
    repo_root = Path.cwd()
    spec_file = init_spec_file(repo_root, "Spec Smoke Test")
    assert spec_file.exists()
    assert spec_file.suffix == ".md"
    content = spec_file.read_text(encoding="utf-8")
    assert "Acceptance Criteria" in content
