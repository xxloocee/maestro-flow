from __future__ import annotations

from maestro_flow.contracts import (
    ArchitectOutput,
    DebugItem,
    DebugOutput,
    DesignDecision,
    DevOutput,
    FileChange,
    PMOutput,
    ReviewFinding,
    ReviewOutput,
    SubTask,
    TestCase,
    TestOutput,
)


def mock_stage_output(stage: str, requirement: str):
    if stage == "pm":
        return PMOutput(
            feature_name="MVP Delivery Flow",
            goals=[
                "Convert requirement into small executable tasks",
                "Automate delivery while keeping human review gates",
            ],
            subtasks=[
                SubTask(
                    title="Define agent roles and JSON contracts",
                    owner="PM",
                    acceptance_criteria="Every stage emits strict JSON and can be consumed downstream",
                    risk="Loose contracts can break orchestration",
                ),
                SubTask(
                    title="Implement orchestrator and artifact archiving",
                    owner="Dev",
                    acceptance_criteria="Each run creates an isolated run directory",
                    risk="Weak logs make postmortem hard",
                ),
            ],
            dependencies=["OpenAI API key (for non-mock mode)", "Git CLI (optional)"],
        )

    if stage == "architect":
        return ArchitectOutput(
            architecture_summary="Use sequential orchestration with structured outputs and explicit human gate checks.",
            module_plan=[
                "maestro_flow/contracts.py: stage output contracts",
                "maestro_flow/orchestrator.py: workflow scheduler",
                "maestro_flow/git_ops.py: git automation",
            ],
            decisions=[
                DesignDecision(
                    topic="Traceability",
                    decision="Persist each stage output to run directory",
                    tradeoff="Uses more disk, improves auditability",
                )
            ],
            rollout_strategy=[
                "Validate full workflow in mock mode first",
                "Switch to real model calls with API keys",
                "Add CI and PR automation last",
            ],
        )

    if stage == "dev":
        return DevOutput(
            implementation_summary=f"Build the baseline multi-agent workflow around requirement: {requirement}",
            file_changes=[
                FileChange(path="src/maestro_flow/orchestrator.py", action="create", purpose="workflow orchestration"),
                FileChange(path="src/maestro_flow/cli.py", action="create", purpose="command entrypoint"),
            ],
            verification_commands=["python -m pytest -q"],
        )

    if stage == "tester":
        return TestOutput(
            strategy_summary="Focus on contract tests and end-to-end smoke run for workflow stability.",
            test_cases=[
                TestCase(name="config-load", type="unit", scenario="configuration can be parsed correctly"),
                TestCase(name="mock-run", type="integration", scenario="mock mode executes all six stages"),
            ],
            run_commands=["python -m pytest -q"],
            known_gaps=["real LLM malformed JSON branch not fully covered"],
        )

    if stage == "debugger":
        return DebugOutput(
            triage_summary="Prioritize guarding against JSON parsing failures and git command failures.",
            likely_failures=[
                DebugItem(
                    issue="model returns non-JSON output",
                    likely_cause="weak output constraints or noisy context",
                    fix_steps=["strengthen system prompt", "add robust JSON extraction fallback"],
                )
            ],
            rollback_plan=["retain run artifacts", "disable auto-commit and require manual approval"],
        )

    return ReviewOutput(
        verdict="approve_with_conditions",
        findings=[
            ReviewFinding(
                severity="medium",
                finding="Add pre-commit hooks and type checks in real repositories.",
                file_ref=".github/workflows/ci.yml",
                recommendation="Add ruff and mypy steps",
            )
        ],
        merge_conditions=["pytest passes", "API keys are read from environment variables"],
    )

