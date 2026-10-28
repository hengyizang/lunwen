---
name: research-autoresearchclaw
description: Diagnose failed or incomplete experiments using AutoResearchClaw's deficiency categories and turn actual cloud run evidence into bounded repair proposals for lunwen.
---

# AutoResearchClaw experiment diagnosis

Codex adaptation of [aiming-lab/AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw/tree/be4ba4755bf1b52220f25e13b2293b5956590070), pinned on 2026-10-28. This entry supplies diagnosis guidance; the Python agent and MCP service are not deployed. Audited upstream MCP pipeline/search/review handlers are stubs.

Read the selected lunwen checkout's `AGENTS.md`, current stage contract, `docs/AUTOMATIC-RECOVERY.md` and `docs/EXPERIMENT-EVIDENCE.md`. Use actual cloud logs and executor receipts, not local research runtimes.

1. Identify original attempt ID, frozen plan/configuration, command, environment and input/output hashes. Preserve the original failure and full log.
2. Classify each deficiency with its exact source anchor: dependency/permission error, resource exhaustion, interrupted/time-limited run, missing conditions/seeds, identical ablation outputs or missing/invalid evidence. An unproven cause stays a hypothesis.
3. Compare coverage with the approved plan. Separate environment repair from scientific redesign. Dropping baselines, repetitions or changing metrics requires the existing amendment/human-review route.
4. Propose the smallest repair, success check, allowed scope and stop condition. Check earlier receipts for the same failed fix. Use existing recovery controls and `scripts/experiment_runner.py`; this skill grants no spending or execution authority.
5. Record a reusable lesson with original failure evidence, applicability hashes, changed assumptions and invalidation condition. Supply it only to relevant tasks.

Return diagnosis, repair proposal and unresolved evidence. Numeric verification must bind metric, unit, group, condition, seed and original output; similar numbers elsewhere are insufficient.

Use `docs/RESEARCH-AUTOMATION-TOOLKIT.md`, cloud operation `research_toolkit`, tool ID `autoresearchclaw` for a source-bound packet. `RESEARCH_TOOLKIT_PACKET=<project-relativepath>` loads selected guidance into the existing model cycle.

Do not inherit upstream `--auto-approve`, gate-bypass recovery, LLM-generated simulated results, cost errors treated as zero or best-run-only evidence. Unknown costs remain unresolved under central controls. This adapter changes no model routes.

## Pinned source

Canonical staged source: `D:\ad\codex\research-automation\sources\autoresearchclaw`; verify its manifest before local use.

- [experiment_diagnosis.py](https://github.com/aiming-lab/AutoResearchClaw/blob/be4ba4755bf1b52220f25e13b2293b5956590070/researchclaw/pipeline/experiment_diagnosis.py): deficiency checks and failure lessons.
- [experiment_repair.py](https://github.com/aiming-lab/AutoResearchClaw/blob/be4ba4755bf1b52220f25e13b2293b5956590070/researchclaw/pipeline/experiment_repair.py): inspect proposed fixes without inheriting automatic scientific redesign.
- [built-in experiment skills](https://github.com/aiming-lab/AutoResearchClaw/tree/be4ba4755bf1b52220f25e13b2293b5956590070/researchclaw/skills/builtin/experiment): task-specific reference material.

Upstream is MIT licensed; retain its notice when copying components.
