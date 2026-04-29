from __future__ import annotations

import json
from pathlib import Path

from maestro_flow.config import PolicyConfig
from maestro_flow.policy_gate import (
    evaluate_execution_policies,
    evaluate_policies,
    has_blocking_failure,
    persist_policy_report,
)


def _base_stage_outputs() -> dict:
    return {
        "dev": {
            "file_changes": [{"path": "src/a.py"}],
            "verification_commands": ["pytest -q"],
        },
        "tester": {"test_cases": [{"name": "smoke"}]},
        "reviewer": {"findings": [{"severity": "low"}]},
    }


def test_evaluate_policies_passes_on_valid_outputs():
    outputs = _base_stage_outputs()
    results = evaluate_policies(outputs, PolicyConfig())

    assert results
    assert all(r.status == "pass" for r in results)
    assert has_blocking_failure(results) is False


def test_evaluate_policies_blocks_on_missing_verification_commands():
    outputs = _base_stage_outputs()
    outputs["dev"]["verification_commands"] = []

    results = evaluate_policies(outputs, PolicyConfig())

    by_id = {r.policy_id: r for r in results}
    assert by_id["DEV_VERIFY_COMMAND_REQUIRED"].status == "fail"
    assert has_blocking_failure(results) is True


def test_persist_policy_report(tmp_path: Path):
    outputs = _base_stage_outputs()
    results = evaluate_policies(outputs, PolicyConfig())

    report_file = persist_policy_report(tmp_path, results)

    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert report_file.name == "policy_report.json"
    assert payload[0]["policy_id"]


def test_policy_disabled():
    outputs = _base_stage_outputs()
    results = evaluate_policies(outputs, PolicyConfig(enabled=False))

    assert len(results) == 1
    assert results[0].policy_id == "POLICY_DISABLED"
    assert results[0].status == "skipped"


def test_policy_rule_override_can_disable_builtin_rule():
    outputs = _base_stage_outputs()
    outputs["dev"]["verification_commands"] = []
    config = PolicyConfig(
        rules={
            "DEV_VERIFY_COMMAND_REQUIRED": {
                "enabled": False,
            }
        }
    )

    results = evaluate_policies(outputs, config)
    by_id = {r.policy_id: r for r in results}
    assert "DEV_VERIFY_COMMAND_REQUIRED" not in by_id


def test_policy_plugin_entrypoint_file(tmp_path: Path):
    plugin_file = tmp_path / "my_plugin.py"
    plugin_file.write_text(
        (
            "def run(stage_outputs, config):\n"
            "    return {\n"
            "        'policy_id': 'PLUGIN_NO_TODO',\n"
            "        'status': 'pass',\n"
            "        'blocking': False,\n"
            "        'message': '插件规则通过。',\n"
            "    }\n"
        ),
        encoding="utf-8",
    )

    outputs = _base_stage_outputs()
    config = PolicyConfig(plugin_entrypoints=[f"{plugin_file}:run"])
    results = evaluate_policies(outputs, config, repo_root=tmp_path)
    by_id = {r.policy_id: r for r in results}
    assert "PLUGIN_NO_TODO" in by_id
    assert by_id["PLUGIN_NO_TODO"].status == "pass"


def test_policy_plugin_failure_returns_blocking_fail(tmp_path: Path):
    plugin_file = tmp_path / "bad_plugin.py"
    plugin_file.write_text(
        (
            "def run(stage_outputs, config):\n"
            "    raise RuntimeError('boom')\n"
        ),
        encoding="utf-8",
    )

    outputs = _base_stage_outputs()
    config = PolicyConfig(plugin_entrypoints=[f"{plugin_file}:run"])
    results = evaluate_policies(outputs, config, repo_root=tmp_path)
    plugin_results = [r for r in results if r.policy_id.startswith("PLUGIN_EXEC::")]
    assert plugin_results
    assert plugin_results[0].status == "fail"
    assert plugin_results[0].blocking is True


def test_evaluate_execution_policies_with_block_and_warning():
    report = {
        "status": "failed",
        "reports": [
            {
                "round": 1,
                "fix_commands": [],
                "verify_commands": [
                    {
                        "command": "python -m pytest -q",
                        "allowed": False,
                        "timed_out": False,
                        "warnings": [],
                    },
                    {
                        "command": "python -c \"print('ok')\"",
                        "allowed": True,
                        "timed_out": True,
                        "warnings": ["缺少必需参数: -q"],
                    },
                ],
            }
        ],
    }

    results = evaluate_execution_policies(report)
    by_id = {r.policy_id: r for r in results}
    assert by_id["EXECUTION_COMMAND_ALLOWED"].status == "fail"
    assert by_id["EXECUTION_COMMAND_TIMEOUT"].status == "fail"
    assert by_id["EXECUTION_COMMAND_WARNINGS"].status == "fail"
    assert by_id["EXECUTION_COMMAND_WARNINGS"].blocking is False
