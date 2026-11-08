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
4. Run `python3 scripts/api_orchestrator.py cycle <slug> <current-stage> --planner-provider uuapi-anthropic --writer-provider uuapi-openai --critic-provider uuapi-anthropic --context <confirmed-context>`. `autopilot.py resume --project <slug>` is a compatibility command over that same API cycle; local model subprocesses are retired. Preserve evidence, disagreements and uncertainty.
5. Use one current independent critique after planning/writing. Repair and re-review only actual actionable findings. Final submission uses the mutually blind three-family panel; preserve sources, disagreements and itemized responses. See the A/B/C rules in workflow.md; C observations never create a repair loop.
6. Create required persistent artifacts only through Codex/OpenAI; Claude output stays in internal planning/audit records.
7. Run `gate-check` and `ready`. The controller records automated G0/G3/G4/G5 decisions after current checks pass; continue through `advance` within the authorized scope.
8. At G1 and G2 present the actual topic dossier and retain the owner's decision. Never fabricate human approval, source rights, data, experiment receipts or additional spending authority.
