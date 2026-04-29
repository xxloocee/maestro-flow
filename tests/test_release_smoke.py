from __future__ import annotations

from pathlib import Path

from maestro_flow.ci_ops import evaluate_run
from maestro_flow.config import load_config
from maestro_flow.integrations import init_spec_file, install_integration
from maestro_flow.orchestrator import DevFlowOrchestrator


def test_release_smoke_mock_requirement_run_creates_expected_artifacts():
    repo = Path.cwd()
    config = load_config(repo / "agents/agents.yaml")

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
    )

    result = orch.run(
        requirement="release smoke test requirement",
        execute_quality_gates=False,
    )

    assert result.run_dir.exists()
    assert (result.run_dir / "summary.md").exists()
    assert (result.run_dir / "run_state.json").exists()
    assert (result.run_dir / "policy_report.json").exists()


def test_release_smoke_mock_spec_init_creates_markdown_file():
    repo = Path.cwd()
    spec_file = init_spec_file(repo, "Release Smoke Spec")

    assert spec_file.exists()
    assert spec_file.suffix == ".md"


def test_release_smoke_mock_spec_run_creates_summary():
    repo = Path.cwd()
    config = load_config(repo / "agents/agents.yaml")
    spec_file = init_spec_file(repo, "Release Smoke Spec Run")
    content = spec_file.read_text(encoding="utf-8").strip()
    requirement = (
        "Implement and deliver the following software spec.\n\n"
        f"Spec file: {spec_file}\n\n"
        f"{content}"
    )

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
    )

    result = orch.run(
        requirement=requirement,
        execute_quality_gates=False,
    )

    assert result.run_dir.exists()
    assert (result.run_dir / "summary.md").exists()


def test_release_smoke_ci_evaluate_passes_for_mock_run():
    repo = Path.cwd()
    config = load_config(repo / "agents/agents.yaml")

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
    )

    result = orch.run(
        requirement="release smoke ci evaluate",
        execute_quality_gates=False,
    )

    import json

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    reviewer = json.loads((result.run_dir / "stage_reviewer.json").read_text(encoding="utf-8"))
    policy_results = json.loads((result.run_dir / "policy_report.json").read_text(encoding="utf-8"))

    evaluation = evaluate_run(
        state=state,
        reviewer=reviewer,
        policy_results=policy_results,
    )

    assert evaluation.passed is True
    assert evaluation.run_status == "succeeded"


def test_release_smoke_codex_install_dry_run_contains_default_skills():
    repo = Path.cwd()
    dst, files = install_integration(
        repo_root=repo,
        target="codex",
        scope="project",
        dry_run=True,
    )

    assert str(dst).endswith(".agents\\skills") or str(dst).endswith(".agents/skills")
    assert any("maestro-spec" in str(f) for f in files)
    assert any("maestro-run" in str(f) for f in files)
