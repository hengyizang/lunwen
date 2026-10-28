---
name: research-synthetic-openscience
description: Apply synthetic-sciences openscience's evidence-bound idea queue, canonical configuration deduplication and explicit unavailable-output states to bounded research planning in lunwen.
---

# Evidence-bound research queue

Codex adaptation of [synthetic-sciences/openscience](https://github.com/synthetic-sciences/openscience/tree/58aff317b3d4a1a23cc202ad1a500ac5c58effe7), pinned on 2026-10-28. It provides this planning workflow; the Bun/TypeScript workbench, `study`, `experiments`, `compute_job` and tracking SDK are not deployed by copying this entry.

Read the selected lunwen checkout's `AGENTS.md`, current stage contract and `docs/EXPERIMENT-EVIDENCE.md`. Use existing hypothesis, experiment and claim records instead of another source of scientific authority.

1. Establish the question, baseline receipts, approved evaluation, available cloud resources and budget. Distinguish development exploration from frozen final evaluation.
2. Build a short queue: hypothesis, evidence gap, discriminating observation, estimated resources, correctness requirements and stop condition. Rank expected information per resource while preserving indispensable controls.
3. Compare effective configurations with actual registry records: data/split, code, environment, parameters, metrics and phase. A renamed identical configuration is a duplicate. Repetition needs a scientific reason, such as an approved independent seed.
4. Submit eligible ideas through human-approved G3 and `scripts/experiment_runner.py`. Count failures, interruptions and cancellations against actual recorded resource use. Preserve every original attempt and outcome.
5. Distinguish queued, running, failed, cancelled, interrupted, inconclusive and completed states. Record per-field unavailable reasons instead of fabricated values or blanket success. Bind lessons to receipts and applicability limits.
6. Stop at authorized bounds or information plateau. State what was learned and what remains unknown. The queue cannot approve gates, change frozen scope, adopt models or buy compute.

Return the deduplicated evidence-linked queue and unresolved inputs. Neat tracking and source completeness do not prove novelty, inference or scientific completion. Reuse unchanged inputs and existing approved model cycles.

Use `docs/RESEARCH-AUTOMATION-TOOLKIT.md`, operation `research_toolkit`, tool ID `synthetic-openscience` for a source-bound packet. `RESEARCH_TOOLKIT_PACKET=<project-relativepath>` loads selected guidance into the current model cycle.

## Pinned source and attribution

Canonical staged source: `D:\ad\codex\research-automation\sources\synthetic-openscience`; verify its manifest before local use.

- [core/autoresearch](https://github.com/synthetic-sciences/openscience/blob/58aff317b3d4a1a23cc202ad1a500ac5c58effe7/backend/cli/skills/core/autoresearch/SKILL.md): finite contract and baseline-first evaluation.
- [research-workflows](https://github.com/synthetic-sciences/openscience/blob/58aff317b3d4a1a23cc202ad1a500ac5c58effe7/backend/cli/skills/research/research-workflows/SKILL.md): durable state and pre-execution manifest.
- [study.ts](https://github.com/synthetic-sciences/openscience/blob/58aff317b3d4a1a23cc202ad1a500ac5c58effe7/backend/cli/src/tool/study.ts): deduplication and launch accounting.
- [provenance envelope](https://github.com/synthetic-sciences/openscience/blob/58aff317b3d4a1a23cc202ad1a500ac5c58effe7/backend/cli/src/science/provenance/envelope.ts): unavailable reasons and states.

Retain repository Apache-2.0, `NOTICE`, `backend/cli/skills/ATTRIBUTION.md` and component-specific licenses when copying material. The larger library has other licenses and host/service dependencies; this adapter does not automatically enable it.
