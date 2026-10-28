---
name: research-deer-flow
description: Develop a source-linked literature research plan or audit a research repository using selected deer-flow methods. Use for question-driven discovery, paper-method review, or an explicit deer-flow request.
---

# deer-flow research methods for Codex

Use these portable research methods with Codex's available tools. The independent deer-flow server, sandbox and frontend are separate software; this entry does not deploy them.

## Select the relevant workflow

- **Literature discovery:** Write the research question, thesis scope, inclusion criteria and missing evidence dimension before searching. Inspect current search logs and reading coverage. Search a gap that current sources do not answer; retain the exact query, source, filters, access date and actual result count. Stop when requested evidence is covered or the agreed search boundary is reached, and state remaining gaps.
- **Paper-method review:** Trace the question to the proposed mechanism, closest competing explanation, discriminating experiment and actual evidence. Locate original methods, results, appendix and relevant figures. Abstracts can prioritize reading; they cannot establish novelty or methodological validity. Record each finding with its source location, consequence and necessary check; a numeric rubric is not verification.
- **Research-code audit:** Pin the repository commit. Inspect entry points, dependencies, license, data access, test/experiment commands, default model calls and actual outputs. Separate implemented code from examples, stubs and README claims. Report reproducibility requirements and a bounded validation plan.

Keep a source-linked answer or comparison table with an explicit unknown for an unsupported item. A fixed paper count, search count or confidence percentage is not a completeness criterion. Preserve contradictory evidence and unsuccessful searches.

## In lunwen

Locate the active checkout and read its `AGENTS.md`, `references/workflow.md` and current stage contract. Read `docs/RESEARCH-AUTOMATION-TOOLKIT.md` to prepare selected, source-bound recipes for the current model cycle. For discovery/reading use `docs/RESEARCH-TASK-SCENARIOS.md`, `docs/LITERATURE-EVIDENCE-READING.md` and `docs/LITERATURE-COMPLETION.md` as needed. Existing `literature_retrieve`, `literature_coverage` and `literature_matrix` operations retain source/version authority. Do not add another author/critic cycle merely to imitate upstream agents.

Run project scripts, tests, extraction and experiments only through the existing cloud runner. This skill grants no paid call, new model/provider, gate approval or experiment authority. Experiments still require the approved G3 plan and `scripts/experiment_runner.py`.

## Pinned upstream resources and limits

Source: [bytedance/deer-flow at a7d8971078593461e14f9b464eafe6db6388e9d7](https://github.com/bytedance/deer-flow/tree/a7d8971078593461e14f9b464eafe6db6388e9d7), MIT; audited 2026-10-28.

Read only the relevant pinned resource when needed: `skills/public/systematic-literature-review`, `skills/public/academic-paper-review` or `skills/public/github-deep-research`. Staged source is expected at `D:\ad\codex\research-automation\sources\deer-flow`; verify its receipt and existence first. Upstream host paths/task tools, fixed query quotas and arXiv-only abstract workflow need adaptation. Do not install its maintainer orchestrator as a research skill.

The independent runtime needs Python 3.12+, Node 22/pnpm and backend/frontend/sandbox configuration. Report it unavailable unless an actual authorized cloud deployment and smoke test establish otherwise.
