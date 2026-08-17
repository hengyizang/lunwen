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
4. Delegate bounded analysis to the matching specialist agents. Preserve their evidence, disagreements and uncertainty.
5. Ask the Codex MCP server for an independent audit at G1–G5. Save the raw audit and an itemized resolution.
6. Create the required artifacts without inventing missing evidence or results.
7. Run `gate-check` and `ready`. Present a concise dossier and stop.
8. Never approve or advance a gate unless the human explicitly instructs that exact action after seeing the dossier.

