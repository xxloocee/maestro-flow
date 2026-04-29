from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    name: str
    prompt_file: str
    temperature: float = 0.2


class QualityGate(BaseModel):
    name: str
    command: str
    required: bool = True


class ExecutionCommandPolicy(BaseModel):
    enabled: bool = True
    description: str = ""
    mode: Literal["prefix", "regex"] = "prefix"
    pattern: str
    required_args: list[str] = Field(default_factory=list)
    forbidden_args: list[str] = Field(default_factory=list)
    missing_required_action: Literal["block", "warn"] = "block"
    forbidden_arg_action: Literal["block", "warn"] = "block"


class WorkflowConfig(BaseModel):
    max_retries: int = 1
    parallel_workers: int = 2
    execution_enabled: bool = False
    max_fix_loops: int = 2
    command_timeout_seconds: int = 180
    execution_workspace_mode: Literal["inplace", "copy"] = "inplace"
    cleanup_execution_workspace: bool = False
    sync_back_on_success: bool = False
    sync_back_only_if_policies_pass: bool = True
    sync_back_conflict_action: Literal["block", "overwrite"] = "block"
    allowed_execution_commands: list[str] = Field(
        default_factory=lambda: [
            "python -m pytest",
            "pytest",
            "python -m unittest",
            "npm test",
            "npm run test",
            "pnpm test",
            "pnpm run test",
            "yarn test",
            "yarn run test",
        ]
    )
    command_policies: list[ExecutionCommandPolicy] = Field(default_factory=list)
    unmatched_command_action: Literal["block", "warn"] = "block"
    blocked_command_fragments: list[str] = Field(
        default_factory=lambda: [
            "rm -rf",
            "del /f /s /q",
            "format ",
            "shutdown",
            "reboot",
            "git reset --hard",
            "git checkout --",
        ]
    )


class RollbackConfig(BaseModel):
    enabled: bool = True
    mode: str = "command"
    commands: list[str] = Field(default_factory=list)
    stop_on_error: bool = True


class KnowledgeConfig(BaseModel):
    enabled: bool = True
    include_patterns: list[str] = Field(
        default_factory=lambda: [
            "README.md",
            "docs/**/*.md",
            "agents/prompts/*.md",
        ]
    )
    max_files: int = 12
    max_chars_per_file: int = 2500
    max_total_chars: int = 12000


class PolicyRuleOverride(BaseModel):
    enabled: bool = True
    blocking: bool | None = None
    message: str = ""


class PolicyConfig(BaseModel):
    enabled: bool = True
    require_tester_cases: bool = True
    require_dev_verification_commands: bool = True
    max_dev_file_changes: int = 120
    block_on_critical_review: bool = True
    secret_patterns: list[str] = Field(
        default_factory=lambda: [
            r"AKIA[0-9A-Z]{16}",
            r"(?i)api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]",
            r"(?i)password\s*[:=]\s*['\"][^'\"]+['\"]",
        ]
    )
    plugin_entrypoints: list[str] = Field(default_factory=list)
    rules: dict[str, PolicyRuleOverride] = Field(default_factory=dict)


class AppConfig(BaseModel):
    default_model: str = "gpt-5.4-mini"
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    quality_gates: list[QualityGate] = Field(default_factory=list)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    rollback: RollbackConfig = Field(default_factory=RollbackConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)


def _expand_env(value: str) -> str:
    if not isinstance(value, str):
        return value
    if not value.startswith("${") or not value.endswith("}"):
        return value

    body = value[2:-1]
    if ":" in body:
        name, fallback = body.split(":", 1)
    else:
        name, fallback = body, ""
    return os.getenv(name, fallback)


def _walk_expand(node):
    if isinstance(node, dict):
        return {k: _walk_expand(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk_expand(x) for x in node]
    if isinstance(node, str):
        return _expand_env(node)
    return node


def load_config(path: Path) -> AppConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    expanded = _walk_expand(raw)
    return AppConfig.model_validate(expanded)


def load_prompt(repo_root: Path, prompt_path: str) -> str:
    p = repo_root / prompt_path
    return p.read_text(encoding="utf-8").strip()

