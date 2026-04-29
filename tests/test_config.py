from pathlib import Path

from maestro_flow.config import load_config


def test_load_config():
    config = load_config(Path("agents/agents.yaml"))
    assert "pm" in config.agents
    assert config.agents["reviewer"].prompt_file.endswith("reviewer.md")
    assert config.workflow.max_fix_loops >= 1
    assert config.workflow.allowed_execution_commands
    assert isinstance(config.workflow.command_policies, list)
    assert config.workflow.unmatched_command_action in {"block", "warn"}
    assert config.workflow.execution_workspace_mode in {"inplace", "copy"}
    assert config.workflow.sync_back_conflict_action in {"block", "overwrite"}

