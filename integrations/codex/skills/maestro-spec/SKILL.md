---
name: maestro-spec
description: Create a Maestro engineering spec first, ask for approval, then run the approved spec through the project CLI.
---

# Maestro Spec Skill

Use this skill for a "spec first, execution second" workflow in Codex.

## Required flow

1. Create the spec first
- Do not jump directly into coding.
- Produce a complete engineering spec that includes at least:
  problem definition, scope, non-goals, acceptance criteria,
  file-level plan, test strategy, and rollback considerations.
- Save the spec to `.maestro/specs/<timestamp>-<slug>.md`.
- Return the generated `SPEC_PATH`.

2. Wait for explicit user approval
- Ask clearly whether execution should continue.
- Only continue when the user explicitly replies with approval such as:
  `approve execution`, `approved`, or equivalent.

3. After approval, run the project CLI
- Execute:
  `python -m maestro_flow.cli spec run --file "<SPEC_PATH>"`
- After execution, return:
  `run_id`, `run_dir`, and the path to `summary.md`.

4. If command execution is unavailable
- Return a copyable CLI command.
- Explain that the user needs to run it manually.

## Output expectations

- Give the conclusion first, then the key details.
- State assumptions and risks clearly.
- Provide numbered next-step suggestions.
