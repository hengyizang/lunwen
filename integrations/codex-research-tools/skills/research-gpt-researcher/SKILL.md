---
name: research-gpt-researcher
description: Prepare a bounded research query frontier and an evidence-linked report while reusing retrieved sources. Use for explicit GPT Researcher tasks or multi-source background research with a defined question.
---

# Bounded GPT Researcher methods for Codex

This entry adapts planning and source reuse. The upstream Python service and separate GPT Researcher MCP server are not connected by installing this skill.

## Research workflow

1. Define the question, intended decision, requested depth and stopping boundary. Check existing source receipts, search logs and question-level reading coverage before creating a new query.
2. Keep a small query frontier: for each unresolved subquestion record the evidence gap, proposed query, visited canonical URLs/DOIs and expected new information. Follow the most useful unresolved item first. Avoid recursive agents repeating a source or an already completed parent query.
3. Reuse unchanged, permitted source content with its current hash and provenance. For a small bounded set read relevant original text directly; do not add an embedding call solely to compress it. Larger corpora use the existing index and explicit retrieval controls.
4. Write source-linked findings. Separate what the original source says, interpretation and unknowns. Verify the original location before giving a page/paragraph or scientific support verdict. Retain disagreements and failed retrievals.
5. Deliver the answer, compact source/evidence table, unresolved items and stop reason. Report length and query breadth are not research quality measures.

Source reuse includes version and rights, not just a matching URL. A changed or inaccessible original invalidates current-text verification. Operational summaries point to originals rather than replacing them.

## In lunwen

Read the active checkout's `AGENTS.md`, `references/workflow.md` and stage contract. Read `docs/RESEARCH-AUTOMATION-TOOLKIT.md` to prepare only selected recipes for the current model cycle. Use `docs/LITERATURE-EVIDENCE-READING.md` for retrieval/coverage/matrices and `docs/LITERATURE-COMPLETION.md` for explicit semantic/PaperQA SDK work. Reuse current literature attempts/progress; carry unresolved evidence into the normal writer/independent critic workflow.

Project execution stays on the existing cloud runner. Upstream `deep_research`, `quick_search` or `write_report` tools, if present elsewhere, do not override central budget, provider identity checks, model routes, human gates or experiment runner. This skill authorizes no new paid call. Prepare the research contract first; model/search execution needs existing explicit authorization and accounting.

## Pinned upstream resources and limits

Source: [assafelovic/gpt-researcher at 3582a6841fe7dc801e2a34e34ee408641aea9bce](https://github.com/assafelovic/gpt-researcher/tree/3582a6841fe7dc801e2a34e34ee408641aea9bce), Apache-2.0; audited 2026-10-28.

For source reuse inspect `gpt_researcher/skills/researcher.py`; for the small-source bypass inspect `gpt_researcher/context/compression.py`. Staged source is expected at `D:\ad\codex\research-automation\sources\gpt-researcher`; verify its receipt and files first. Native `skills/gpt-researcher/SKILL.md` is a brief MCP setup pointer, not the runtime; `.claude/SKILL.md` is a development guide.

Independent execution needs Python 3.12+, dependencies and configured model/search/embedding services. Defaults include Tavily and paid OpenAI embeddings/models. No such service, key, budget or MCP registration is implied here.
