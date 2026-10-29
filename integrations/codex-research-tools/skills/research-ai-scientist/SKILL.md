---
name: research-ai-scientist
description: Apply The AI Scientist's experiment-branch tracking, failure recovery and figure-to-text review methods to an existing lunwen research plan using real cloud evidence.
---

# The AI Scientist research methods

Codex adaptation informed by Sakana AI's [V2](https://github.com/SakanaAI/AI-Scientist-v2/tree/96bd51617cfdbb494a9fc283af00fe090edfae48) and [V1](https://github.com/SakanaAI/AI-Scientist/tree/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb), pinned on 2026-10-29. This independently written workflow uses lunwen's existing controls. It does not deploy or launch either upstream agent.

Read the user-selected lunwen checkout's `AGENTS.md`, `references/workflow.md`, current stage contract and `docs/AI-SCIENTIST-INTEGRATION.md`. Research scripts, experiments and validation run on the existing GitHub Actions runner.

## Use the method that answers the current question

- **Develop an idea:** distinguish a template-backed extension with a reproducible starting implementation from open-ended exploration. Tie the proposed mechanism, closest works, discriminating observable and failure condition to the approved doctoral question. Use `research_frontier` and the existing full-text originality matrix to pursue missing evidence. Semantic Scholar matches and similarity scores are discovery leads; absence of a match never verifies novelty. Open-ended ideation does not authorize changing the six-paper scope.
- **Trace experiments:** obtain a current `research_iteration` report from actual executor receipts. Prepare `research_search_tree` only when branch purpose or debugging ancestry needs comparison. Select exact run/attempt IDs; retain failed, unfavorable and independent replication attempts. Declared investigation/tuning/main/ablation labels organize workflow and do not change the sealed exploratory/confirmatory analysis phase. A debug child requires actual failed or timed-out parent execution; a weak metric is not a software error. Branch ancestry remains a declared relationship, not proof a fix worked. Use the bounded worklist to propose one informative next step, with resource ceiling and stop condition, through the existing G3 approval and `experiment_runner.py` route.
- **Review figures with the manuscript:** use the actual rendered figure, current caption, corresponding main-text passage, claim IDs and exact data/run outputs. Compare units, groups, uncertainty, axes, legends, numeric values and inference strength across all four. Use existing `figure_story`, output QA and figure provenance rather than redrawing from an image or a model's remembered number. A missing image, failed extraction or mechanical pass leaves visual/scientific inspection unresolved. Revise the existing figure/text sources and regenerate current artifacts; keep unsupported links in the existing issue/decision records.
- **Review a manuscript:** supply the actual source-bound artifact and applicable venue rubric to the existing independent initial/final critics. Require located findings and an itemized writer response. Reconcile disagreements in the existing decision log. Do not add a fixed five-reviewer fan-out or interpret same-model responses as independent model families. An internal score or agreement cannot establish validity, doctoral merit, Q1 quality or acceptance.

Return the evidence-linked observation, proposed action and unresolved question. Do not select a best seed, collapse unlike metrics, drop failed paths, rename negative findings as bugs or tune frozen final evaluation. Keep current model assignments, requested/reported identity checks, spending holds, CNY500 ceiling and human gates. Claude remains a read-only planner/critic; OpenAI writes persistent scientific artifacts. This skill authorizes no new paid call, retry or GPU rental.

For controlled model context, use `research_toolkit` with tool ID `ai-scientist` and explicitly bind the current required reports and scientific inputs. Select the returned packet using `RESEARCH_TOOLKIT_PACKET=<project-relativepath>` in the existing cycle. The critic receives observed facts without the author's task prose, workflow preference or next-step worklist.

## Pinned sources and license

Canonical source snapshots are `D:\ad\codex\research-automation\sources\ai-scientist` (V2) and `D:\ad\codex\research-automation\sources\ai-scientist-v1` (V1). Verify the matching `receipts/<tool-id>.json` before relying on local bytes. Read only relevant implementation details:

- [V2 journal](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/treesearch/journal.py) and [agent manager](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/treesearch/agent_manager.py): branch relationships and phase management; do not inherit its automatic winner selection or launcher.
- [V2 visual review](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/perform_vlm_review.py): inspect figure/caption relationships without treating extraction as verification.
- [V1 review](https://github.com/SakanaAI/AI-Scientist/blob/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb/ai_scientist/perform_review.py): rubric and disagreement handling, while retaining lunwen's independent-family controls.

Both pins use **The AI Scientist Source Code License, Version 1.0, December 2025**, not Apache/MIT. Keep the complete license with any distributed upstream code. If upstream software or its derivative generates a manuscript, section 3.2.e.i requires prominent intelligible disclosure of machine generation or use of The AI Scientist; preserve applicable downstream terms and journal disclosures. Do not remove required disclosure or provenance. Source staging and this adapter do not establish that an upstream research run has succeeded.
