# Research-first workflow

Start with the user's current question and the evidence already available. Choose a useful action, carry it out, save what actually happened, and continue. Existing user instructions and budget authority remain in effect. Ask for a consequential missing choice only when the next action depends on it; perform independent work meanwhile.

## Commands

```bash
python3 -m scripts.researchctl init --project demo --question 'Current research question'
python3 -m scripts.researchctl work --project demo --paper P01 --task 'Read the closest work and compare the evidence'
python3 -m scripts.researchctl status --project demo --json
python3 -m scripts.researchctl add-paper --project demo --question 'A distinct contribution worth a separate paper'
python3 -m scripts.autopilot plan --project demo --context 'Next useful research action'
python3 -m scripts.autopilot start --project demo --context 'Next useful research action'
python3 -m scripts.autopilot resume --project demo --paper P01 --context 'Continue from the actual results'
```

Initialization and task/status commands do not spend model budget. A new project starts with one paper and no automatically authorized spending. `autopilot` uses configured providers and existing cumulative authority. Choose free tools or work directly on local material when a model route is unavailable; report the affected dependency precisely.

## Research choices

Read, experiment, analyze and draft in the order useful for the question. Add or merge papers when their contributions warrant it. A literature review, observational study, qualitative analysis, mathematical proof and empirical benchmark need different evidence. Use an appropriate tool even when a native adapter does not support that method; describe what was actually checked.

Review important claims with adequate original material. A second perspective can be helpful, but neither fixed model families nor a fixed number of reviews establish independence or correctness. Repair actual findings; optional extensions do not automatically become required experiments. Reuse unchanged source preparation and valid results.

Keep source facts, author statements, model interpretations, planned work and observed outcomes distinct. Preserve relevant failed, negative and inconclusive results. Draft missing-result sections as plans; never write an invented result to complete a template. Manuscripts explain the contribution, while full run records remain separately available.

## Background records and actual boundaries

Record task, sources, outputs, important method choices, failed attempts and costs with the existing tools. A checksum identifies bytes; it does not certify their meaning. Do not create a second ledger just to satisfy a workflow. Respect known privacy and access restrictions, keep credentials out of artifacts, and stay within the authorized cumulative total. Conservatively bounded pending charges occupy funds without freezing unrelated affordable work.

A prepared export or ZIP is not an external submission. Follow the user's actual authority for publication or other external actions. Do not fabricate a human signature or overwrite original approvals.

## Compatibility

G0–G5 names remain task labels for existing projects and adapters. `gate-check`, `ready`, `approve`, `advance`, old `start.sh` aliases and existing cloud requests can still inspect or maintain historical records. They are not prerequisites for the normal research path. `status --legacy-checks` requests the detailed historical checks explicitly.

Retain existing sealed protocols, sources and outcomes. New follow-up work records its relationship to earlier evidence without rewriting its analysis phase. See [task guidance](stage-contracts.md) and [research integrity](research-integrity.md). Date-stamped audits, old owner decisions and third-party instructions remain historical or methodological sources; the current nine principles in [AGENTS.md](../AGENTS.md) govern this implementation.
