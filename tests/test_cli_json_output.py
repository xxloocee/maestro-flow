from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from maestro_flow.cli import app


runner = CliRunner()


def _parse_json_output(result) -> dict:
    assert result.stdout.strip(), result.stdout
    return json.loads(result.stdout)


def test_run_json_output_mock_success():
    result = runner.invoke(
        app,
        ["run", "--requirement", "json smoke", "--mock", "--skip-gates", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    payload = _parse_json_output(result)
    assert payload["ok"] is True
    assert payload["command"] == "run"
    assert payload["verdict"]
    assert Path(payload["run_dir"]).exists()
    assert Path(payload["summary_file"]).exists()


def test_spec_run_json_output_mock_success(tmp_path: Path):
    spec_file = tmp_path / "sample-spec.md"
    spec_file.write_text("# Sample Spec\n\n- one\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "spec",
            "run",
            "--file",
            str(spec_file),
            "--mock",
            "--skip-gates",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = _parse_json_output(result)
    assert payload["ok"] is True
    assert payload["command"] == "spec.run"
    assert payload["spec_file"] == spec_file.resolve().as_posix()
    assert Path(payload["run_dir"]).exists()
    assert Path(payload["summary_file"]).exists()


def test_install_json_output_dry_run():
    result = runner.invoke(
        app,
        ["install", "--target", "codex", "--scope", "project", "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    payload = _parse_json_output(result)
    assert payload["ok"] is True
    assert payload["command"] == "install"
    assert payload["target"] == "codex"
    assert payload["scope"] == "project"
    assert payload["dry_run"] is True
    assert payload["files"]


def test_ci_evaluate_json_output_after_mock_run():
    run_result = runner.invoke(
        app,
        ["run", "--requirement", "ci json smoke", "--mock", "--skip-gates", "--json"],
    )
    assert run_result.exit_code == 0, run_result.stdout
    run_payload = _parse_json_output(run_result)

    result = runner.invoke(
        app,
        ["ci", "evaluate", "--run-id", run_payload["run_id"], "--json"],
    )

    assert result.exit_code == 0, result.stdout
    payload = _parse_json_output(result)
    assert payload["command"] == "ci.evaluate"
    assert payload["ok"] is True
    assert payload["passed"] is True


def test_spec_run_json_output_missing_file():
    result = runner.invoke(
        app,
        ["spec", "run", "--file", "missing-spec.md", "--json"],
    )

    assert result.exit_code == 2
    payload = _parse_json_output(result)
    assert payload["ok"] is False
    assert payload["command"] == "spec.run"
    assert payload["error"]["type"] == "bad_parameter"


def test_sync_back_plan_json_output_non_copy_run_fails():
    run_result = runner.invoke(
        app,
        ["run", "--requirement", "sync-back json smoke", "--mock", "--skip-gates", "--json"],
    )
    assert run_result.exit_code == 0, run_result.stdout
    run_payload = _parse_json_output(run_result)

    result = runner.invoke(
        app,
        ["sync-back", "plan", "--run-id", run_payload["run_id"], "--json"],
    )

    assert result.exit_code == 1
    payload = _parse_json_output(result)
    assert payload["ok"] is False
    assert payload["command"] == "sync-back.plan"
    assert "copy" in payload["error"]["message"]
