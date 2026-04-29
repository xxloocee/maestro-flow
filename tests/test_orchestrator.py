import json
from pathlib import Path

from maestro_flow.config import load_config
from maestro_flow.mock_data import mock_stage_output
from maestro_flow.orchestrator import DevFlowOrchestrator


class FlakyLLM:
    def __init__(self):
        self.calls: dict[str, int] = {}

    # 故意不接收 prompt_text，用于验证向后兼容调用。
    def complete_json(self, *, stage, agent, schema, requirement, context):
        self.calls[stage] = self.calls.get(stage, 0) + 1
        if stage == "tester" and self.calls[stage] == 1:
            raise RuntimeError("json parse failed once")
        return mock_stage_output(stage, requirement)


class FailingLLM:
    def complete_json(self, *, stage, agent, schema, requirement, context):
        if stage == "dev":
            raise RuntimeError("forced stage failure for rollback test")
        return mock_stage_output(stage, requirement)


class PolicyFailLLM:
    def complete_json(self, *, stage, agent, schema, requirement, context):
        output = mock_stage_output(stage, requirement)
        if stage == "dev":
            output.verification_commands = []
        return output


def test_mock_orchestration_runs_end_to_end(tmp_path: Path):
    repo = Path.cwd()
    config = load_config(repo / "agents/agents.yaml")

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
    )

    result = orch.run(
        requirement="Build a reviewable multi-agent software delivery workflow",
        execute_quality_gates=False,
    )

    assert result.run_dir.exists()
    assert (result.run_dir / "summary.md").exists()
    assert (result.run_dir / "run_state.json").exists()
    assert (result.run_dir / "knowledge_snapshot.json").exists()
    assert (result.run_dir / "prompt_registry.json").exists()
    assert (result.run_dir / "policy_report.json").exists()
    assert result.verdict in {"approve", "approve_with_conditions", "request_changes"}


def test_stage_retry_and_state_machine():
    repo = Path.cwd()
    config = load_config(repo / "agents/agents.yaml")
    config.workflow.max_retries = 1

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=FlakyLLM(),
    )

    result = orch.run(
        requirement="Validate retry behavior",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "succeeded"
    assert state["stages"]["tester"]["status"] == "succeeded"
    assert state["stages"]["tester"]["attempts"] == 2


def test_failure_triggers_rollback_commands():
    repo = Path.cwd()
    config = load_config(repo / "agents/agents.yaml")
    config.workflow.max_retries = 0
    config.rollback.enabled = True
    config.rollback.mode = "command"
    config.rollback.commands = ['python -c "print(\'rollback-ok\')"']
    config.rollback.stop_on_error = True

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=FailingLLM(),
    )

    result = orch.run(
        requirement="Trigger rollback",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "rolled_back"
    assert state["rollback"]["status"] == "rolled_back"
    assert len(state["rollback"]["steps"]) == 1
    assert (result.run_dir / "rollback_report.json").exists()


def test_failure_without_rollback_when_disabled():
    repo = Path.cwd()
    config = load_config(repo / "agents/agents.yaml")
    config.workflow.max_retries = 0
    config.rollback.enabled = False

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=FailingLLM(),
    )

    result = orch.run(
        requirement="Failure should stay failed",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["rollback"]["status"] == "skipped"


def test_policy_gate_blocks_run_when_required_rule_fails():
    repo = Path.cwd()
    config = load_config(repo / "agents/agents.yaml")
    config.rollback.enabled = False

    orch = DevFlowOrchestrator(
        repo_root=repo,
        config=config,
        model=config.default_model,
        mock=True,
        llm_client=PolicyFailLLM(),
    )

    result = orch.run(
        requirement="Trigger policy gate",
        execute_quality_gates=False,
    )

    state = json.loads((result.run_dir / "run_state.json").read_text(encoding="utf-8"))
    report = json.loads((result.run_dir / "policy_report.json").read_text(encoding="utf-8"))

    assert state["status"] == "failed"
    assert state["error_code"] == "POLICY_GATE_FAILED"
    assert any(item["policy_id"] == "DEV_VERIFY_COMMAND_REQUIRED" and item["status"] == "fail" for item in report)
