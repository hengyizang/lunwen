---
name: continue
description: Resume the current research stage with Claude planning/auditing and Codex writing, then stop at the next human gate.
argument-hint: <project-slug>
disable-model-invocation: true
---

# Continue

1. Read `references/workflow.md` and `references/research-integrity.md`.
2. Run `python3 scripts/researchctl.py status --project $ARGUMENTS --json`.
3. Read only the current section of `references/stage-contracts.md`.
4. Run `python3 scripts/api_orchestrator.py cycle <slug> <current-stage> --planner-provider uuapi-anthropic --writer-provider uuapi-openai --critic-provider uuapi-anthropic --context <confirmed-context>`. Do not invoke local model CLIs unless the user explicitly selects CLI mode. Preserve evidence, disagreements and uncertainty.
5. Require initial and final schema-bound independent audits at G1–G5. Save both plus the non-Claude writer's itemized resolution.
6. Create required persistent artifacts only through Codex/OpenAI; Claude output stays in internal planning/audit records.
7. Run `gate-check` and `ready`. Present a concise dossier and stop.
8. Never approve a gate. Advance only when an explicit approval is already recorded and the human asked to resume.
