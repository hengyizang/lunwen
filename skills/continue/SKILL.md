---
name: continue
description: Resume the current research stage, coordinate focused agents and Codex, and stop at the next human gate.
argument-hint: <project-slug>
disable-model-invocation: true
---

# Continue

1. Read `references/workflow.md` and `references/research-integrity.md`.
2. Run `python3 scripts/researchctl.py status --project $ARGUMENTS --json`.
3. Read only the current section of `references/stage-contracts.md`.
4. Prefer `python3 scripts/autopilot.py resume --project $ARGUMENTS` to run the bounded author/critic loop. Delegate additional bounded analysis only when the stage needs it. Preserve evidence, disagreements and uncertainty.
5. Require initial and final schema-bound Codex audits at G1–G5. Save both plus an itemized resolution.
6. Create the required artifacts without inventing missing evidence or results.
7. Run `gate-check` and `ready`. Present a concise dossier and stop.
8. Never approve a gate. Advance only when an explicit approval is already recorded and the human asked to resume.
