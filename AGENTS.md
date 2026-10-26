# Repository operating rules

This repository is a research workflow, not a publication generator.

1. Never invent citations, data, experiments, results, reviews, author contributions, journal metrics, or submission status.
2. Treat every scientific claim as provisional until linked to evidence in the claim-evidence matrix.
3. Use current primary sources for journal rules, degree rules, datasets, software APIs, and market facts. Record the URL and access date.
4. Never confuse JCR/JIF quartiles, CiteScore quartiles, SJR quartiles, and Chinese Academy of Sciences partitions.
5. Do not cross G0–G5 without an explicit human approval recorded by `scripts/researchctl.py`.
6. Keep raw datasets, publisher template archives, secrets, credentials, and large experiment artifacts out of Git.
7. Before acquiring data, verify license, research-use rights, privacy, terms, provenance, version, and leakage risk. Do not bypass access controls.
8. Pre-register paper-level hypotheses, baselines, splits, metrics, statistics, compute ceiling, and falsification criteria before final experiments.
9. Preserve negative results and failed runs. Do not select only favorable seeds, datasets, metrics, or subgroups.
10. Enforce role separation: Claude may produce only read-only semantic plans and internal independent audits. Codex/OpenAI writes and remediates every persistent scientific artifact. Result-bearing charts must be rendered locally from recorded data, never supplied as Claude-generated files. GPT Image may make a separately labeled, disclosed conceptual illustration, never a data figure.
11. Never auto-submit a manuscript. G5 produces a submission-ready package for human review.
12. Read `references/workflow.md` and the relevant section of `references/stage-contracts.md` before changing a research project.
13. Run model orchestration through `scripts/autopilot.py` or `scripts/api_orchestrator.py`; preserve Claude plans internally, both initial and final independent model-family audits, the non-Claude writer's itemized decision log, and output-provenance hashes.
14. Execute experiments only through `scripts/experiment_runner.py` after the approved G3 plan and budget hashes match.
15. Treat dataset discovery metadata and DOI lookup results as leads to verify, never as license, fitness, or claim-support decisions.
16. Treat third-party gateways as untrusted transport: use HTTPS, keep keys out of files and URLs, record requested and reported model IDs, and stop on missing or mismatched model identity.
17. The author and independent critic must use different model families. A different endpoint or account does not make the same family independent.
18. Never package a file whose current provenance hash identifies Anthropic/Claude as its persistent writer. Human or deterministic local edits must create a new file hash; do not use paraphrasing merely to conceal AI use.
19. Enforce the declared six-paper venue portfolio: at least three current JCR Q1 SCI/SCIE targets and every remainder at least current JCR Q2, all with IF >1.0. Q2 changes only the venue target and never weakens doctoral/originality/experiment/writing gates. Re-check category/year evidence.
20. Write every manuscript-bound artifact in English. G5 must pass the deterministic manuscript-language check; a model's assertion that prose is English is not sufficient.
21. At G5, use line-level academic-style findings for targeted evidence-preserving revision. A user-supplied detector score may guide a separate optional editing pass, but it cannot override scientific quality, claim/citation/numeric integrity, human review or required AI-use disclosure. Never spin synonyms, remove warranted uncertainty or conceal model assistance.
22. Keep all six papers within one overarching doctoral question and cumulative knowledge contribution. Core theme A and independently evidenced extension B must serve that same doctoral topic. Each paper needs standalone value and an explicit contribution to the approved thesis synthesis. Evidence-led reframing stays within that scope; a substantive change to the doctoral question or paper-to-thesis mapping needs human review of the affected G1/G2 records before dependent work continues. Never silently turn the portfolio into unrelated topics or waive paper independence.
23. Manage dynamic routes through the structured task profiles and cloud controls in `docs/DYNAMIC-MODEL-ROUTING.md`. Classify work before paid execution; never label a core scientific task routine to obtain a cheaper route. Transport/group/effort/context candidates require task-specific evidence before promotion. Preserve actual selected-route receipts, independent audits and cumulative budgets. Unknown charges stop new paid work; selecting a candidate never authorizes a paid test or retry. Use deterministic selection for ordinary requests rather than adding another model call to choose a model.

Run repository checks after code or schema changes:

For actual CPU semantic retrieval/reranking, bounded PaperQA2 SDK vector-store
use, complete-text reading comparisons, cloud Zotero reads, discovery categories
or PDF overlays/annotated copies, use docs/LITERATURE-COMPLETION.md. These are
explicit existing-cloud operations. Preserve unchanged indexes/requests, source
rights, original versions, unknown semantic ratings and the central spending
boundary. No upstream agent may bypass that boundary; OCR never self-verifies
original evidence. Actual independent review is not supplied by acceptance tests.

For row-level data provenance, remembered-claim tracing, criterion-level AI
screening advice, tiered bilingual searches, matrix-based synthesis outlines or
Mermaid export, use docs/RESEARCH-TASK-SCENARIOS.md. Reuse existing source, formal
decision and figure-story authority; a suggestion or location never self-verifies
science. Preserve unknown dates/counts, adverse evidence, phases and originals.

For source-scoped literature retrieval, sentence/page navigation, question-level
reading coverage, evidence matrices and quality/cost comparisons, use
docs/LITERATURE-EVIDENCE-READING.md. Reuse existing model cycles and progress;
preserve original ranges, unknowns, adverse evidence and actual cost receipts.
Do not enable an embedding service or adopt a model from synthetic tests.

For variable dictionaries, cleaning, panel/time checks, economic vintages or causal
estimators, use docs/EMPIRICAL-DATA-WORKFLOW.md. Preserve raw inputs, every registered
specification and source/runner seals. Do not promote a diagnostic or fit into a
causal validity claim. Use the exact limited reviewed estimator or block for a
suitable adapter; never silently substitute paired t tests or a different design.

For concrete contributions, paragraph reasoning and actionable scientific writing
findings, use `docs/EVIDENCE-FIRST-WRITING.md` within existing records. Preserve
unknown evidence and stable issue history; source completeness is not semantic
validation. Reuse current author/critic cycles rather than extra paid passes.

For reference-image discovery, original main-figure briefs, shared six-paper
visual tokens or editable SVG/PPTX/draw.io, read `skills/figures/SKILL.md` and
`docs/FIGURE-REFERENCE-WORKBENCH.md`. Reuse source-bound reports and supply only
explicitly selected references to model roles. Reference relevance and native
editability never replace scientific evidence, image rights or human approval.

Apply the complete pinned CCFA family through `docs/CCFA-INTEGRATION.md`: `ccf-humanization` then `ccf-common` are mandatory preflights, followed by the specialist for the actual task. All 17 native entries are available under `.agents/skills/`; API and CLI research roles load the same source-bound guidance through `scripts/research_methods.py`. Read complete relevant references or prepare a controlled CCFA task packet before specialist work. Do not replace native roles, stages, budgets, approvals or the experiment runner with upstream example paths or a parallel state system. Record all CFH01–CFH38 contextual dispositions at G5 alongside existing editorial criteria. Complete rule coverage never proves scientific validity or authorship.

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts
python3 scripts/validate_repo.py
```
