---
name: start
description: Initialize a doctoral research program, record actual constraints, and continue after automated G0 checks until a G1/G2 topic decision or missing evidence requires the owner.
argument-hint: <project-slug> [goal and constraints]
disable-model-invocation: true
---

# Start

Use `$ARGUMENTS` as the project slug followed by optional context.

1. Read `references/workflow.md`, the Intake section of `references/stage-contracts.md`, and `references/research-integrity.md`.
2. Run `python3 scripts/check_env.py --soft` and explain only actionable gaps.
3. Prefer the API-first `bash scripts/start.sh <slug> <confirmed-context>` path. It delegates Claude planning/auditing and GPT writing to the configured gateway. `autopilot.py start/resume/plan` and the historical `scripts/start.sh --cli` alias also use the shared API cycle; local model subprocesses are retired. Never overwrite an existing project.
4. Populate `intake/constraints.json` only from confirmed user information. Mark unknown material fields explicitly.
5. Ask at most one high-value clarification at a time while continuing any safe work that does not depend on it.
6. When the constraints are complete, set their status to `ready_for_review` and run `gate-check` then `ready`.
7. G0 records an automated decision after its evidence checks pass. Continue through the native controller; do not impersonate the owner or invent missing constraints. Present the doctoral topic at G1 and each paper topic at G2 for their actual human decisions. Other checked stages need no additional human approval.
