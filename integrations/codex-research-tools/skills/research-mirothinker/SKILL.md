---
name: research-mirothinker
description: Prepare a durable, evidence-preserving handoff for a long research task using MiroThinker context-management ideas. Use when research spans many tool calls or needs continuation after context compaction.
---

# MiroThinker context methods for Codex

Continue research without losing evidence or decision boundaries. MiroThinker is a model family and harness, not a native Codex skill. This adapter does not install weights, deploy an endpoint or change the model.

## Evidence-preserving handoff

- Read current task state. Preserve the research question, doctoral scope, accepted constraints, active stage, approvals, budgets, unresolved disagreements and next executable step. A progress question does not replace the ongoing task.
- Separate short-lived operational output from scientific evidence. Compact repeated directory listings, transport chatter or redundant tool previews when useful. Keep originals, hashes, exact citation ranges, raw results, failed runs, provenance and spending/approval authority in existing durable records.
- For each scientific statement needed next list its current original source/location, evidence inspected and missing dimension. Rehydrate that evidence before relying on a summary. If a reference is missing or stale mark the affected conclusion unverified and recover the source; do not fill gaps from memory.
- Preserve enough chronology to explain changed decisions: old position, new evidence and resulting next step. Reuse an unchanged source-bound handoff instead of rewriting or rereading everything.
- End with completed outputs, unresolved dependencies and one concrete continuation point. Distinguish prepared, executed and verified work.

The selected upstream `keep5` profile retains recent tool output for operational context. Do not apply that count to scientific evidence or delete older material. Its 200-turn cap is not permission to spend or a quality target.

## In lunwen

Read the active checkout's `AGENTS.md`, `references/workflow.md` and current stage contract. Read `docs/RESEARCH-AUTOMATION-TOOLKIT.md` to bind selected recipes and current inputs into the task packet. Reuse `scripts/context_efficiency.py`, `scripts/cloud_checkpoint.py` and existing progress/source records. For question-specific reading use `docs/LITERATURE-EVIDENCE-READING.md`; sentence/page locations assist navigation without establishing entailment.

Run project operations only on the existing cloud runner. Retain current bounded model roles; do not add a summarizer call, embedding service or MiroThinker route. This skill authorizes no new paid call, experiment, gate approval or global memory update.

## Pinned upstream resources and limits

Source: [MiroMindAI/MiroThinker at 1c4253f6774bf40314271a827304b842100e054c](https://github.com/MiroMindAI/MiroThinker/tree/1c4253f6774bf40314271a827304b842100e054c), Apache-2.0; audited 2026-10-28.

Inspect `apps/miroflow-agent/conf/agent/mirothinker_1.7_keep5_max200.yaml` for this context profile. Reading transport is in `libs/miroflow-tools/src/miroflow_tools/mcp_servers/reading_mcp_server.py`; it is not a scientific evidence validator. Staged source is expected at `D:\ad\codex\research-automation\sources\mirothinker`; verify its receipt and existence first.

Independent execution needs Python 3.12+, an endpoint or substantial weights, and optional search/reading/sandbox services. Those dependencies are not deployed here; do not download weights, rent GPUs or configure paid services merely to use this method.
