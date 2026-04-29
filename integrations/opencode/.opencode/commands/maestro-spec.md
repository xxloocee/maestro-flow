---
description: Create a spec first, then run Maestro after approval
agent: plan
---

Follow this two-stage Maestro spec workflow exactly.

Stage A: create and confirm the spec, but do not execute implementation yet.
1. Write a complete engineering spec from the current repository context and command arguments.
2. The spec must include: problem definition, scope and non-goals, acceptance criteria, file-level plan, test strategy, and rollback considerations.
3. Save the spec to `.maestro/specs/<timestamp>-<slug>.md`.
4. Return the generated `SPEC_PATH`.
5. Ask the user for explicit approval before execution continues.
6. Accept approval only when the user clearly confirms execution.
7. Before approval, do not perform coding changes or run the Maestro execution CLI.

Stage B: after approval, execute the spec automatically.
1. Run `python -m maestro_flow.cli spec run --file "<SPEC_PATH>"`.
2. Return `run_id`, `run_dir`, and the path to `summary.md`.
3. Recommend the next review focus, especially `summary.md`, `run_state.json`, and `policy_report.json`.
4. If command execution is unavailable, return a copyable command and stop.
