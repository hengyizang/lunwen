---
name: start
description: Initialize a new doctoral research program, capture constraints, and stop at the G0 human approval gate.
argument-hint: <project-slug> [goal and constraints]
disable-model-invocation: true
---

# Start

Use `$ARGUMENTS` as the project slug followed by optional context.

1. Read `references/workflow.md`, the Intake section of `references/stage-contracts.md`, and `references/research-integrity.md`.
2. Run `python3 scripts/check_env.py --soft` and explain only actionable gaps.
3. If the project does not exist, run `python3 scripts/researchctl.py init --project <slug>`. Never overwrite an existing project.
4. Populate `intake/constraints.json` only from confirmed user information. Mark unknown material fields explicitly.
5. Ask at most one high-value clarification at a time while continuing any safe work that does not depend on it.
6. When the constraints are complete, set their status to `ready_for_review` and run `gate-check` then `ready`.
7. Present the G0 dossier and stop. Do not run `approve` or `advance` for the user.

