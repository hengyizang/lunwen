---
name: continue
description: Resume the current research stage with the existing read-only planner/critics and persistent writer; continue through automated checks and request only actual G1/G2 topic decisions or missing evidence.
argument-hint: <project-slug>
disable-model-invocation: true
---

# Continue

1. Read `references/workflow.md` and `references/research-integrity.md`.
2. Run `python3 scripts/researchctl.py status --project $ARGUMENTS --json`.
3. Read only the current section of `references/stage-contracts.md`.
4. Run `python3 scripts/api_orchestrator.py cycle <slug> <current-stage> --planner-provider uuapi-anthropic --writer-provider uuapi-openai --critic-provider uuapi-anthropic --context <confirmed-context>`. Do not invoke local model CLIs unless the user explicitly selects CLI mode. Preserve evidence, disagreements and uncertainty.
5. Require initial and final schema-bound independent audits at G1–G5. Save both plus the non-Claude writer's itemized resolution. A clean initial audit with complete applicable writer dispositions may skip an extra remediation call; the fresh final audit remains required.
6. Create required persistent artifacts only through Codex/OpenAI; Claude output stays in internal planning/audit records.
7. Run `gate-check` and `ready`. The controller records automated G0/G3/G4/G5 decisions after current checks pass; continue through `advance` within the authorized scope.
8. At G1 and G2 present the actual topic dossier and retain the owner's decision. Never fabricate human approval, source rights, data, experiment receipts or additional spending authority.
