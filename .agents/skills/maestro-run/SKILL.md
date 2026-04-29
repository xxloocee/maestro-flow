---
name: maestro-run
description: Run the default Maestro requirement-driven workflow in the current repository and return the key run outputs.
---

# Maestro Run Skill

Use this skill to execute the default Maestro requirement-driven workflow in the current repository.

## Required flow

1. Clarify the requirement briefly
- Summarize the current requirement in one or two sentences.
- State any critical assumptions only if they materially affect execution.

2. Run the project CLI
- Execute:
  `python -m maestro_flow.cli run --requirement "<REQUIREMENT_TEXT>"`
- If the environment is not ready for real model execution, suggest:
  `python -m maestro_flow.cli run --mock --requirement "<REQUIREMENT_TEXT>"`

3. Return the key run outputs
- Return:
  `run_id`, `run_dir`, and the path to `summary.md`.
- Tell the user to inspect:
  `summary.md`, `run_state.json`, and `policy_report.json` when relevant.

4. If command execution is unavailable
- Return a copyable CLI command.
- Explain what the user should run manually.

## Output expectations

- Lead with the result.
- Keep the response concise and actionable.
- Highlight blockers, assumptions, and next steps when necessary.
