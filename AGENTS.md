# Repository operating rules

This repository is a research workflow, not a publication generator.

1. Never invent citations, data, experiments, results, reviews, author contributions, journal metrics, or submission status.
2. Treat every scientific claim as provisional until linked to evidence in the claim-evidence matrix.
3. Use current primary sources for journal rules, degree rules, datasets, software APIs, and market facts. Record the URL and access date.
4. Never confuse JCR/JIF quartiles, CiteScore quartiles, SJR quartiles, and Chinese Academy of Sciences partitions.
5. Require explicit recorded human decisions on the doctoral topic at G1 and each paper topic at G2. Other research-stage transitions use recorded automated checks and must not fabricate human decisions. Retain actual budget authority and all evidence, rights, identity and experiment controls. Test affected confirmation paths; software acceptance alone never establishes a successful unattended research project.
6. Keep raw datasets, publisher template archives, secrets, credentials, and large experiment artifacts out of Git.
7. Before acquiring data, verify license, research-use rights, privacy, terms, provenance, version, and leakage risk. Do not bypass access controls.
8. Pre-register paper-level hypotheses, baselines, splits, metrics, statistics, compute ceiling, and falsification criteria before final experiments.
9. Preserve negative results and failed runs. Do not select only favorable seeds, datasets, metrics, or subgroups.
10. Enforce role separation: Claude may produce only read-only semantic plans and internal independent audits. Codex/OpenAI writes and remediates every persistent scientific artifact. Result-bearing charts must be rendered locally from recorded data, never supplied as Claude-generated files. GPT Image may make a separately labeled, disclosed conceptual illustration, never a data figure.
11. Never auto-submit a manuscript. G5 produces a complete package; external authorship and submission requirements remain applicable.
12. Read `references/workflow.md` and the relevant section of `references/stage-contracts.md` before changing a research project.
13. Run model orchestration through `scripts/autopilot.py` or `scripts/api_orchestrator.py`; preserve Claude plans internally, the actual independent critique and any problem-triggered repair/review, the non-Claude writer's itemized decision log, and output-provenance hashes. Ordinary cycles use planner → writer → critic; final submission uses three mutually blind, different-family source views as defined in `references/workflow.md`.
14. Execute experiments only through `scripts/experiment_runner.py` after the approved G3 plan and budget hashes match.
15. Treat dataset discovery metadata and DOI lookup results as leads to verify, never as license, fitness, or claim-support decisions.
16. Treat third-party gateways as untrusted transport: use HTTPS, keep keys out of files and URLs, record requested and reported model IDs, and stop on missing or mismatched model identity.
17. The author and independent critic must use different model families. A different endpoint or account does not make the same family independent.
18. Never package a file whose current provenance hash identifies Anthropic/Claude as its persistent writer. Human or deterministic local edits must create a new file hash; do not use paraphrasing merely to conceal AI use.
19. Keep the six-paper venue ambitions, including the existing ≥3 Q1 target, as planning targets and observations. Use source-bound venue fit, actual article type and final venue requirements for preparation; Q1/Q2 or IF thresholds do not block scientific gates or packaging. Never invent ranking/year/category evidence or silently replace an existing target; unknown ranking remains unknown.
20. Write every manuscript-bound artifact in English. Use the deterministic language observations to find actual non-English material; do not treat a heuristic score as scientific clearance or a new blocking gate.
21. At submission-phase G5, use line-level academic-style findings for targeted evidence-preserving revision. A user-supplied detector score may guide a separate optional editing pass, but it cannot override scientific quality or claim/citation/numeric integrity, or silently erase an existing disclosure. Journal AI-policy compliance is not a research gate. Never spin synonyms, remove warranted uncertainty or conceal model assistance.
22. Keep all six papers within one overarching doctoral question and cumulative knowledge contribution. Core theme A and independently evidenced extension B must serve that same doctoral topic. Each paper needs standalone value and an explicit contribution to the approved thesis synthesis. Evidence-led reframing stays within that scope; a substantive change to the doctoral question or paper-to-thesis mapping needs human review of the affected G1/G2 records before dependent work continues. Never silently turn the portfolio into unrelated topics or waive paper independence.
23. Manage dynamic routes through the structured task profiles and cloud controls in `docs/DYNAMIC-MODEL-ROUTING.md`. Classify work before execution; never label a core scientific task routine to obtain a cheaper route. Transport/group/effort/context candidates require task-specific evidence before scientific promotion. Preserve selected-route receipts and independent audits. The current payment policy in `docs/TOTAL-COST-POLICY.md` overrides older payment restrictions: calculate and record costs and enforce existing cumulative project totals only. Do not add per-paper/per-request sublimits, paid opt-ins, tranche steps, manual billing approvals or blanket stops on bounded reservations. Use verified charges when available and honestly labeled conservative upper estimates otherwise. Every attempt counts; never increase the configured total automatically.
24. Keep the six-paper G2 architecture and individual human topic decisions. After checked G2 decisions, new unexecuted portfolios complete the active paper's G3–G5 before the next paper enters G3. Use the canonical per-paper plan, ledger, dataset snapshot and claim paths; preserve other papers' sealed inputs and results. Never silently migrate an already frozen or executed legacy batch protocol. All primary and supplemental attempts share the original cumulative totals.

## Codex Cloud development environment

Use `bash scripts/bootstrap-codex-cloud.sh` for the reusable Linux Codex Cloud
setup; see `docs/CODEX-CLOUD.md`. Do not run the Windows/D-drive installer there.
Before Python commands in a cloud task, run
`source .runtime/codex-cloud-env.sh` from the repository root. If that file is
missing, run the bootstrap first. This activates the repository virtual
environment and keeps its caches and temporary output under `.runtime/`.
Installing development tools does not make Codex Cloud an approved scientific
executor. Continue actual research through the existing cloud controls and
experiment runner; do not copy secrets or reset project records during setup.

Run repository checks after code or schema changes:

For task-selected methods from the research automation tools, read
`docs/RESEARCH-AUTOMATION-TOOLKIT.md`. Use `research_toolkit` in the existing cloud
literature control and pass only the selected immutable packet to existing model
roles. Adapted Codex skills are not deployed upstream services. Preserve central
budget/identity controls, independent review, all attempts and approved G3 execution.

For The AI Scientist V1/V2 methods, read `docs/AI-SCIENTIST-INTEGRATION.md`.
Use receipt-bound `research_search_tree` only as a declared branch view within
existing controls. It cannot prove a repair, select favorable results, reclassify
frozen analysis phases or authorize execution. Raw upstream launchers remain
disabled; preserve the pinned custom source license and required disclosures.

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

For innovation candidate screening, use `docs/INNOVATION-SCREENING.md` and the
required innovation_screening section of the existing hypothesis register.
Retain original rounds, explicit assumptions, existing candidate comparisons, data
exposure and candidate decisions. Exploratory records may remain incomplete;
final decisions require their applicable focused or full comparison coverage.
Narrative dispositions need no invented scores. Reuse existing independent audits. Scores or
structural completeness never verify novelty or authorize science or spending.

For reference-image discovery, original main-figure briefs, shared six-paper
visual tokens or editable SVG/PPTX/draw.io, read `skills/figures/SKILL.md` and
`docs/FIGURE-REFERENCE-WORKBENCH.md`. Reuse source-bound reports and supply only
explicitly selected references to model roles. Reference relevance and native
editability never replace scientific evidence, image rights or human approval.

Use the pinned CCFA family through `docs/CCFA-INTEGRATION.md`. Humanization and Common establish the shared baseline before the task specialist. Ordinary API/CLI cycles receive compact native rules, current scientific evidence and exact retrievable source identities. Load complete pinned entries/references for explicitly selected skills, full-reference review or a concrete dependent task; do not attach every stage guide to every call. All 17 authoritative native entries are under `skills/`; `.agents/skills/` contains generated discovery pointers. Preserve native roles, stages, cumulative budgets, G1/G2 topic decisions and the experiment runner. CFH01–CFH38, H01–H26, AD01–AD08 and style/hygiene findings remain available as contextual observations, not compulsory scorecards or scientific blockers. Submission performs its source-bound venue/package checks once per unchanged snapshot. Rule coverage never proves validity or authorship.

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts
python3 scripts/validate_repo.py
```
