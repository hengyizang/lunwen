---
name: research-pi-autoresearch
description: Apply pi-autoresearch's persistent session and all-attempt journal to bounded development-set optimization in lunwen, preserving correctness and scientific evidence.
---

# Bounded autoresearch session

Codex adaptation of [davebcn87/pi-autoresearch](https://github.com/davebcn87/pi-autoresearch/tree/04b8a50dac7efe80ffc91648bd00ed9b022e24c2), pinned on 2026-10-28. Pi's extension and `init_experiment`, `run_experiment`, `log_experiment` tools are not installed into Codex by this entry. Use lunwen's cloud controls.

Read the selected checkout's `AGENTS.md`, current stage contract and `docs/EXPERIMENT-EVIDENCE.md`. Apply this workflow to a bounded exploration or implementation optimization, distinct from confirmatory evaluation.

1. Define the question, baseline receipt, allowed changes, development split, metric direction, correctness constraints, trial/time/cost caps and stop conditions. Leave the final test untouched. Without authorization prepare the contract only.
2. Inspect all-attempt history. For each candidate state its hypothesis and changed assumption; skip tested configurations unless new evidence justifies repeating them.
3. Run one eligible candidate at a time through approved `scripts/experiment_runner.py` cloud execution. Bind actual attempt IDs and complete outputs, including crashes and non-improvements. Preserve full logs; provide bounded diagnostic excerpts to model roles.
4. Check correctness and planned coverage before interpreting a metric gain. Record hypothesis, observation, keep/reject recommendation, reason, next-action hint and source/configuration hashes in existing records.
5. Stop at authorized caps, unresolved spend, unchanged failures, invalid evaluation or an information plateau. Summarize every attempt and uncertainty. Development retention is neither scientific acceptance nor permission to rerun final tests.

Use `docs/RESEARCH-AUTOMATION-TOOLKIT.md`, operation `research_toolkit`, tool ID `pi-autoresearch` to prepare source-bound guidance. `RESEARCH_TOOLKIT_PACKET=<project-relativepath>` selects it for an existing model cycle.

Do not copy metric-only retention, `NEVER STOP`, automatic `git checkout` or `git clean` into the shared checkout. Preserve failed code snapshots and negative results. Upstream heuristic confidence is not a statistical interval or p-value.

## Pinned source

Canonical staged source: `D:\ad\codex\research-automation\sources\pi-autoresearch`; verify its manifest before local use.

- [autoresearch-create](https://github.com/davebcn87/pi-autoresearch/blob/04b8a50dac7efe80ffc91648bd00ed9b022e24c2/skills/autoresearch-create/SKILL.md): session setup and correctness requirements, within the finite contract above.
- [autoresearch-finalize](https://github.com/davebcn87/pi-autoresearch/blob/04b8a50dac7efe80ffc91648bd00ed9b022e24c2/skills/autoresearch-finalize/SKILL.md): session accounting.
- [extension](https://github.com/davebcn87/pi-autoresearch/blob/04b8a50dac7efe80ffc91648bd00ed9b022e24c2/extensions/pi-autoresearch/index.ts): structured logging; host-specific tools and destructive rollback are reference only.

Upstream is MIT licensed. The separate Node/Pi runtime is not deployed; this entry adds no paid calls or model changes.
