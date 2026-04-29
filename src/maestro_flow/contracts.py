from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SubTask(BaseModel):
    title: str
    owner: str
    acceptance_criteria: str
    risk: str = ""


class PMOutput(BaseModel):
    feature_name: str
    goals: list[str] = Field(default_factory=list)
    subtasks: list[SubTask] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class DesignDecision(BaseModel):
    topic: str
    decision: str
    tradeoff: str


class ArchitectOutput(BaseModel):
    architecture_summary: str
    module_plan: list[str] = Field(default_factory=list)
    decisions: list[DesignDecision] = Field(default_factory=list)
    rollout_strategy: list[str] = Field(default_factory=list)


class FileChange(BaseModel):
    path: str
    action: Literal["create", "update", "delete"]
    purpose: str
    content: str = ""


class DevOutput(BaseModel):
    implementation_summary: str
    file_changes: list[FileChange] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)


class TestCase(BaseModel):
    name: str
    type: Literal["unit", "integration", "e2e", "smoke"]
    scenario: str


class TestOutput(BaseModel):
    strategy_summary: str
    test_cases: list[TestCase] = Field(default_factory=list)
    run_commands: list[str] = Field(default_factory=list)
    known_gaps: list[str] = Field(default_factory=list)


class DebugItem(BaseModel):
    issue: str
    likely_cause: str
    fix_steps: list[str] = Field(default_factory=list)


class DebugOutput(BaseModel):
    triage_summary: str
    likely_failures: list[DebugItem] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    file_changes: list[FileChange] = Field(default_factory=list)
    fix_commands: list[str] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    severity: Literal["critical", "high", "medium", "low"]
    finding: str
    file_ref: str = ""
    recommendation: str


class ReviewOutput(BaseModel):
    verdict: Literal["approve", "approve_with_conditions", "request_changes"]
    findings: list[ReviewFinding] = Field(default_factory=list)
    merge_conditions: list[str] = Field(default_factory=list)


STAGE_TO_MODEL = {
    "pm": PMOutput,
    "architect": ArchitectOutput,
    "dev": DevOutput,
    "tester": TestOutput,
    "debugger": DebugOutput,
    "reviewer": ReviewOutput,
}

