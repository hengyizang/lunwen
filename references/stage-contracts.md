# Stage contracts

Current financial policy: [TOTAL-COST-POLICY.md](../docs/TOTAL-COST-POLICY.md).
Only cost accounting and configured cumulative project totals are financial
controls. Older payment approval or fixed-tranche examples below do not apply.

The owner's current policy requires human decisions for the doctoral topic and
each paper topic only. Other research-stage decisions use evidence-bound
automated records. Preserve every
scientific-integrity, source/version, privacy, budget, identity and execution check; C observations do not create blocking gates. Unknown
evidence remains unknown. Licence/research-use verification is optional. Missing data or successful execution blocks the
affected work; they are never converted into invented human approval.
Quality reports at G1/G2 require their human-topic-review flag; G3/G4/G5 use
automated decisions. A legacy report flag never creates or replaces authority.

Current review-remediation contracts: [REVIEW-REMEDIATION.md](../docs/REVIEW-REMEDIATION.md).
Formal G1-G5 quality reports use schema 1.2 factual assessments. The current
novelty matrix uses 1.1 source-bound candidate/prior-work comparisons, bounded
retrieval dispositions and actual current independent novelty assessments
at G1/G2/G5. A scientific-integrity failures block; B submission checks bind the final unchanged snapshot; C numeric/editorial and administrative findings are warnings. G2 scientific bindings preserve primary outcomes and falsification
conditions through G3-G5; negative-result plans, typed dependencies and thesis
claim/result alignment retain failures and uncertainty. Empty templates and
legacy scores are not evidence and cannot waive these requirements.

Scientific reasoning: [SCIENTIFIC-REASONING.md](../docs/SCIENTIFIC-REASONING.md)
strengthens source-bound problem value, discriminating tests and conclusions in
the existing G1-G5 contracts. Missing inputs block; completeness never proves
scientific validity, doctoral merit or Q1 acceptance.

Experiment/evidence extensions: [RESEARCH-EXTENSIONS.md](../docs/RESEARCH-EXTENSIONS.md).
Declared comparability, pinned baseline adoption, fine-grained reading anchors and review worklists are revalidated at research gates. Actual topics, data and method trials remain required; optional human calibration needs real attributed ratings when requested. No template or regression fixture fills those gaps. Model routing and effort remain unchanged.

Follow-up quality input and receipt contracts: [RESEARCH-IMPROVEMENTS-FOLLOWUP.md](../docs/RESEARCH-IMPROVEMENTS-FOLLOWUP.md). Revision ledgers remain visible observations; actual unsupported numerical, citation or claim changes block as scientific-integrity failures. Confirmatory statistics require explicit sample-flow/missingness/repetition declarations bound to actual sources. Optional research-support and review-packet inputs require fresh protected audits when present. Their reports and human ratings never establish scientific completion automatically.

## Intake — G0

Required:

- `intake/constraints.json` conforming to `schemas/intake-constraints.schema.json`, with every material feasibility value explicit and status `ready_for_review`;
- target application routes and time horizon;
- available skills, time, budget, compute, data and equipment;
- keep system availability separate from human time: cloud-only projects may explicitly use `human_review_mode: on_request` with `weekly_hours: null`; `system_execution_hours_per_day: 24` describes cloud automation, never 168 hours of weekly human work. Human topic decisions apply at G1/G2; G0 uses its recorded automated checks;
- explicit cumulative model/API and cloud compute/cash totals with their actual authorization history; the model default is CNY 300 and configured totals never increase automatically. Preserve every charge, failure and bounded reservation under [TOTAL-COST-POLICY.md](../docs/TOTAL-COST-POLICY.md); do not add fixed tranches, per-paper/per-call caps, paid opt-ins or routine manual billing gates. A material budget/date amendment uses the existing hash-bound [operating amendment](../docs/OPERATING-CONSTRAINT-AMENDMENTS.md) without rewriting prior authority or costs;
- an explicit execution mode; for `cloud_only`, GitHub Actions is the runtime and local GPU/RAM/storage values may be null;
- excluded domains and ethical/legal boundaries;
- cloud-only feasibility as a pass/fail prerequisite for the six current papers: authorized data, experiments, and evidence must be obtainable and executable on the declared cloud runner without a physical laboratory or the researcher's machine;
- direction ranking weights for funded PhD position supply, employment and salary, future growth, separately scored funded-PhD and job-market competition, background fit and application-route fit, using the actual user-supplied weights, never forced equal weights, applied only after feasibility and data-rights screening;
- use `references/direction-ranking.md` to collect dated, route-specific primary evidence and score the seven factors without double-counting positions;
- novelty evidence, doctoral depth and original contribution as mandatory topic and research-plan requirements that cannot be traded against direction scores.

Do not begin broad topic scoring while critical constraints are unknown.

## Topic intelligence — G1

Required:

- `evidence/search-log.jsonl` with each line conforming to `schemas/search-record.schema.json`; every claimed database, query family and closest-work inclusion must be traceable to an executed provider receipt, exact raw/normalized hashes and recorded screening decisions. New automated screening uses the existing writer request and retains uncertain records, exact prompt/response binding and model identity;
- `program/topic-shortlist.json` with at least three serious candidates and explicit rejection reasons;
- `program/hypothesis-register.json` conforming to `schemas/research-hypotheses.schema.json`, with at least three concrete hypotheses after direction screening, two competing explanations per hypothesis, discriminating tests, failure modes, cloud/budget/deadline estimates and a proposal-first argument plan; `program/hypothesis-audit.json` must be generated by `scripts/research_candidates.py` and recompute against the current sources. This register cannot grant novelty or automatically choose the topic;
- `program/core-thesis.json` for doctoral proposition A;
- `program/extension-thesis.json` for separately doctoral-level extension B, with disjoint claims/papers, independent primary evidence, falsification conditions and a survives-core-failure rationale;
- one overarching doctoral question and integrated knowledge contribution for all six papers. Core A and extension B must serve that same topic; B's independent claims and evidence protect scientific validity if A fails, rather than create an unrelated second doctoral topic. Explain this relationship in the existing doctoral case and `relationship_to_core` records;
- `program/originality-audit.json` conforming to `schemas/originality-audit.schema.json`, including at least five closest primary works, three adjacent fields, three query families, counterevidence, residual novelty risk, a doctoral case and a reliability strategy;
- `program/novelty-claim-matrix.json` schema 1.1; every originality claim distinguishes known elements from the candidate contribution, compares against at least three closest works with actual retrieval and original-source anchors, and records mechanism, falsification, predictions, boundaries and residual uncertainty. Bind retrieval dispositions and round counts to executed receipts; explain coverage-, time- or budget-based stopping honestly rather than inventing saturation or equating all new DOIs with new closest works;
- `program/topic-decision.md` with novelty, contribution, feasibility, competition, PhD-position supply and job-market evidence.
- automatic broad-data evidence followed by Codex scientific-fit screening against the actual user-supplied G0 ranking weights; preserve rejected datasets and unresolved license, sample, bias, leakage, compute and external-validity concerns.
- `program/topic-shortlist.json` records `selected_direction_cloud_feasibility` with `current_papers_feasible: true`, `no_future_lab_dependency: true`, and concrete authorized-data, cloud-experiment and current-paper-scope plans. If a proposed direction requires post-admission laboratory work to establish a current paper's result, reject it before weighted ranking. Future laboratory extensions can be retained as separate, unproven plans.

Stress-test novelty against adjacent literatures, not only exact keywords. Distinguish “not found” from “novel.” Reject a proposed topic that lacks a defensible original contribution or doctoral depth, regardless of its direction ranking score.

These are the final G1 decision requirements. During exploration, the novelty
matrix may remain `status: in_progress`, with `search_saturation.status` set to
`exploring` or `reopened`. Preserve unresolved gaps, affected claim IDs and next
searches; retain historical rounds when the current no-new-work count resets.
Do not invent completed chaining, empty gaps or two saturation rounds.
`research_quality.py novelty-check` checks a draft without granting a gate;
`--for-gate` requires the current decision-ready source-bound record. Schema 1.1
records the actual bounded stopping rule, retrieval dispositions and remaining
limitations rather than requiring universal saturation. Formal G1/G2/G5 novelty
decisions still require the actual current independent assessments, source-bound
candidate-to-prior-work differences and resolution of blocking scientific
objections. An honest search limit never supplies missing evidence or novelty.

Every hypothesis also requires scientific_value with located importance evidence
and decision_test with a focal observable prediction and distinguishable continue,
revise and stop conditions. The actual problem value and identifiability remain
scientific judgments. See the strengthened research-hypotheses schema.

The same register requires innovation_screening: explicit assumptions and source
gaps, decision-relevant candidate differences and shared failure dependencies,
retained generation rounds, prior data exposure, candidate-level dispositions
and honest evaluation uncertainty. Exploratory mode retains the rounds actually
performed. Final decision mode requires a real post-evidence round and either
full pair coverage or a justified focused policy comparing every focal candidate
with every alternative. Narrative evaluation may omit numerical criteria and
ratings. The native audit rechecks bindings and optional matrix calculations.
Existing independent critics assess scientific meaning; records or
scores cannot grant novelty, select a topic, override a gate or authorize spend.
Use docs/INNOVATION-SCREENING.md. Keep all candidates within one doctoral scope.

## Paper architecture — G2

Required:

- `program/paper-map.json` conforming to `schemas/paper-map.schema.json`, using `independence_basis: cumulative` and one `thesis_synthesis.cumulative_contributions` row per paper: knowledge increment, primary evidence, standalone value, merge trigger and exact claims. Existing legacy pair tables remain readable; fifteen repeated pair forms are not required;
- six default paper contracts under `papers/P01`–`papers/P06`;
- `papers/Pxx/research-identity.json` for each paper, following
  `schemas/research-identity.schema.json` and
  [the original-research policy](../docs/ORIGINAL-RESEARCH-POLICY.md): primary
  research preferred; summary-only reviews excluded; secondary quantitative
  work needs a substantive protocol and truthful, source-bound research-article
  eligibility for its actual design at every candidate venue. Assign types only
  after assessing real research questions and materials;
- for each current paper, a cloud-feasibility declaration with a specific authorized data-access plan, GitHub Actions compute plan and rationale that no laboratory or local hardware is required. The current claim and primary evidence may not depend on post-admission laboratory work, including for papers assigned to extension B;
- dependency graph, shared assets, independent contribution, falsification condition and fallback venue for each paper;
- source-bound venue candidates and fit evidence for scope, audience, actual article type and desk-rejection risks. Preserve existing Q1/Q2 ambitions as planning observations; no ranking/IF floor blocks science or packaging. Use lawful JCR evidence when available and record missing ranking as unknown;
- `program/journal-screening.json`, deterministically bound to the JCR registry and dated official evidence, with decomposed scope/article/audience/tier/practicality/access/reputation scores, explicit risk flags and challenge/target/safety choices for every paper;
- thesis synthesis showing how all six papers answer the same overarching doctoral question through distinct subquestions and cumulative contributions. Use each paper contract's `relationship_to_core` / `relationship_to_extension` and the paper map's existing role, dependencies and `thesis_synthesis` fields to make the connection explicit; shared data, tools or keywords alone do not establish doctoral coherence.

Avoid salami slicing. Each paper must answer a distinct research question and remain scientifically coherent.

At G3-G5 and during reviewer revisions, preserve each paper's approved contribution
to this doctoral synthesis when designing tests, interpreting results or reframing
the narrative. A substantive change to the doctoral question or paper-to-thesis
mapping requires human review of the affected G1/G2 records before dependent work
continues. Preserve the one-thesis requirement, independent paper contributions
and frozen scientific records; a writing revision cannot authorize topic drift.

## Experiment design — G3

After G2, new unexecuted portfolios use one paper at a time through G3–G5.
The requirements below apply to the active paper. Native canonical plan, budget
declaration, ledger and source-bound dataset snapshot paths are
`experiments/papers/Pxx/`. Legacy names used below resolve to the active canonical
paths in native prompts and helpers; sealed legacy work retains its original
paths and scope. Migration refuses previously frozen or executed protocols.
Other papers need not have experiments or results yet. All share the same
doctoral scope and cumulative project totals; no copied budget creates money.

An explicit `plan.json.research_phase: exploratory` selects a bounded scientific
experiment. Missing phase remains `confirmatory`. The plan's `exploration`
object requires `unknown`, `discriminating_test`, `continue_if`, `revise_if`,
`stop_if`, `claim_limit` and the boolean `prior_outcomes_seen`. It still needs
actual rights/provenance, data/input hashes, remaining cumulative authority, a
machine-frozen plan and the native runner with the current independent scientific critique.
Do not fill unknown power or a final baseline suite merely to start a justified
exploration. The detailed confirmatory requirements below remain mandatory
before the separate formal protocol runs. Exploration never waives G3 or permits
arbitrary commands, fabricated outcomes or expanded claims.

For confirmatory tabular/causal studies, use [empirical data contracts](../docs/EMPIRICAL-DATA-WORKFLOW.md)
within the existing paper contract. Freeze dictionaries, explicit cleaning,
complete calendars, source vintages and all estimator specifications. Prepared
data do not authorize estimation. Configured diagnostics and current numerical
reporting remain required at G4/G5; unsupported estimators require a reviewed adapter.

The empirical requirements below apply to confirmatory empirical papers. Actual Meta/theory
identities instead use the positive protocol, source, uncertainty/proof,
isolated-replay and frozen-input requirements in
[SCIENTIFIC-STUDY-ROUTES.md](../docs/SCIENTIFIC-STUDY-ROUTES.md). They still need
the same automated G3 decision, sealed execution plan and actual budget authority. Never fabricate empirical
datasets, baseline classes or power calculations for another research design.

Required for confirmatory empirical work:

- selected dataset rows with licenses and provenance: independent execution captures `data/datasets.jsonl` rows in the current paper's immutable `experiments/papers/Pxx/datasets.jsonl` snapshot before sealing; legacy protocols retain their original manifest. Raw data and rights evidence remain canonical and cannot be changed after freezing;
- a deterministic `data/quality/<dataset_id>.json` for every selected dataset, bound to current local file hashes and checking complete-scan status, missingness, duplicates, imbalance and split/group overlap where applicable, plus a separate protected `<dataset_id>-confirmation.json` identifying the automated checks, unresolved warnings and current report hash;
- `experiments/plan.json` conforming to `schemas/experiment-plan.schema.json`;
- one or more JSON design files under the active `papers/Pxx/experiments/`, each conforming to `schemas/paper-experiment-design.schema.json`, with every selected paper plan run assigned to exactly one design;
- `experiments/budget.json` with `status: ready_for_review` and `hard_ceiling_usd`;
- hypotheses; traceable simple, domain-standard and strong-recent baselines with source, version, license and comparable tuning budgets; ablations; splits; primary/secondary metrics; estimands; practical-significance thresholds; effect sizes; confidence intervals; multiplicity handling; power/precision rationale; at least three seeds for stochastic designs; robustness, negative controls and stopping rules;
- leakage, privacy, bias and external-validity assessment.
- `papers/Pxx/power-analysis.json` from pinned `statsmodels` or a Monte Carlo script/result with at least 1,000 simulations and two exact control-plane reruns in clean temporary directories; narrative claims of adequate power do not count;
- `papers/Pxx/preregistration.json`, generated by the local control plane only after data quality, power, design, plan and budget are complete, with hashes for every frozen input;
- a reproduction plan in every design mapping approved run IDs to domain-standard and strong-recent baselines and to disjoint original/clean-room executions, with a digest-pinned, network-disabled isolated container, environment capture, an independent-operator plan and predeclared numeric tolerances. A linked Git worktree alone is not an isolated executor.

Freeze the confirmatory plan before final runs. Label later exploration as exploratory.

## Experiment execution — G4

Validate the active paper's registered attempts and contracted claims. Its claim
matrix is `claims/papers/Pxx/claim-evidence.csv`; its reproducibility report and
quality records stay with that paper. Failed attempts from every paper and
supplemental scope continue to consume the same cumulative project total.

Meta/theory use their dedicated computed study evidence and protected automated
study-validation confirmation in place of empirical baseline/power reports.
Confirmatory routes require exact approved executor receipts, complete claim coverage,
isolated replay, unchanged inputs and independent scientific audits.

Exploratory G4 checks the exact registered attempt and bounded test, preserving
all failures, outputs, decisions and costs. Checked continuation archives that
round and returns the same paper to G3. The next formal plan binds
`prior_exploration: [{path, sha256}]` and `prior_outcomes_seen: true`; its separate
protocol, run IDs and outputs cannot relabel exploratory results as confirmatory.
The confirmatory requirements below apply before result-bearing G5 claims.

Required:

- `experiments/registry.jsonl` including failed runs, executor-issued post-run input-integrity receipts and current hashes for every successful expected output, each tied to the exact G3-approved plan; recognized command-file arguments must be hash-declared inputs or approved outputs, container executions mount every declared input read-only, and every executor re-hashes inputs after the process exits;
- immutable configs, code commit identifiers, environment lock or image digest and random seeds;
- `claims/claim-evidence.csv` exactly covering every contracted unique claim; supported claims reference successful registered analyses;
- `reports/reproducibility.md`;
- statistical audit and sensitivity analysis.
- the active `papers/Pxx/baseline-reproduction.json`, covering the G3-declared domain-standard and strong-recent comparators with exact successful registry attempt IDs, comparable protocols, unchanged source URLs, predeclared tolerances and the complete current output set of those attempts;
- the active `papers/Pxx/clean-room-reproduction.json`, using the exact G3-declared disjoint run IDs, exact successful attempt IDs, executor-issued isolation receipts from a digest-pinned, network-disabled container, identifier-independent registry environment digests, predeclared numeric equivalence checks and the complete current output set;
- protected `papers/Pxx/reproduction-confirmation.json`, created by the automated control plane after both reproduction reports and deterministic checks pass; its hashes become stale if either report changes. It does not assert human review or certify scientific interpretation.

Do not write a favorable conclusion before the claim matrix and negative results are visible.

## Writing and review — G5

The current active paper starts in `scientific`. The frozen contract's
`writing_phase` is only an initial preference; `state.writing_phases` records the
current phase. Source/fact/citation/numeric/claim integrity and the actual
result-to-claim argument apply throughout. A reviewed scientific decision and
passing A checks allow automatic transition to `submission`; this adds no human
stage signature and does not edit the frozen contract. Scientific or
supplemental-protocol review alone cannot approve parent G5.

Use the A/B/C classification and three-call/repair/final-panel rules in
[workflow.md](workflow.md). C observations are shown separately and never require
an empty CFH/H/AD/style ledger, two simulated review rounds or numeric 8/8.5
scores. Keep existing observation tools available for targeted improvements.
Actual unsupported claims, false numbers/citations or silent removal of negative
results remain A failures. Quality schema 1.2 records located factual judgments;
a score or a complete template cannot establish scientific validity.

Required scientific evidence:

- complete actual registered results and statistical-reporting mappings, with
  independent units, uncertainty, multiplicity, assumptions and concrete
  Methods/Results/table/figure locations; adverse results cannot be omitted;
- the current manuscript, figures, tables and supplement, canonical claim matrix,
  real source identities and full lawful primary passages for deeper claims;
  preserve `supports`, `contradicts` and `insufficient` judgments and unresolved
  disagreements instead of converting a DOI/abstract match into semantic proof;
  before final G5, select `claim_evidence` for this paper in the existing
  `program/research-control.json` and cover every distinct citation occurrence
  with its complete local assertion, lawful registered original text and located
  evidence. Repeated keys supporting different assertions require separate
  judgments. Use the controlled citation-audit `citation_usage.occurrences`
  inventory; manuscript locations and coverage are derived from the current
  TeX/include or Word source, never model-invented hashes. A source may use
  its DOI or, when no DOI exists, the exact registered original HTTPS URL.
  The current protected critic/domain-panel response records support; missing,
  contradictory or insufficient judgments cannot clear final submission.
  The domain panel receives claim tasks by default; explicit `panel_views`
  selects suitable existing views. Reuse these reviews without an extra paid loop;
- current source-bound paper facts and claim/inference limits. Numeric/citation/
  conclusion-strength edits must agree with actual evidence; preserve originals,
  interpretation-changing negative/null findings; archive complete runs separately;
- deterministic result-figure source/run/output/renderer provenance. Conceptual
  illustrations remain separate, labeled and unable to substantiate results;
- current output provenance showing no final scientific file persistently
  written by Claude/Anthropic; a cleanup cannot launder writer ancestry;
- actual external review comments and source-bound responses when a real round
  exists. Simulated comments cannot replace those originals.

At submission, B checks validate the actual selected venue and article type,
source-bound ranking where known, official template/format, real successful
compile/render, export, bibliographic identity, reporting checklist and truthful
existing author/funding/conflict/ethics/data/code statements. A missing renderer
or `skipped_tool_missing` is not a successful export. There is no fixed 120/180-day
expiry, Q1/Q2/IF gate, automatic AI branding, mandatory AI-use statement or
journal AI-policy gate. AI-use statements may be edited or removed by the author; truthful internal tool/provenance records remain. Real external author, rights
and ethics obligations remain applicable.

`papers/Pxx/reviews/panel-inputs.json` supplies the three distinct final source
views documented in workflow.md. The controller freezes three genuinely
independent-family responses before synthesis and preserves disagreement. It
does not vote, infer scientific validity or predict acceptance. The final machine
approval binds `submission_checks_sha256`; `advance` and ZIP creation reuse B
only while the manuscript, actual source/template bindings, implementation and
provenance remain unchanged. Changed evidence requires recomputation.

The existing notebook decision binds the current cycle, stage/paper, unknown,
discriminating test, outcome, rationale, next action and real evidence IDs.
`pending`/`unchanged` may retain missing evidence rather than fabricate progress.
The current critique binds that decision. C warning counts, tests or new receipts
do not become scientific results.

An actual internal finding can trigger a separate `Ixxx` supplemental protocol;
external review uses `Rxxx`. Preserve protected source-review hashes, frozen
parent inputs, prior exposure, cumulative costs and the original runner. A child
protocol/result confirmation cannot approve parent G5. Retain all adverse results
and resume the parent scientific/final review with the actual new evidence.

Research preparation is progressive in `papers/Pxx/research-case.json`: one
falsifiable headline/counterclaim and three reader benefits; a G3 rejection
pre-mortem linked to critical tests; real retrieved competition measures;
main/baseline/negative-boundary figure plans; title/abstract variants and keywords;
source-bound related-work, venue-fit and cover-letter evidence; and local
preprint, reproducibility, rebuttal and retarget assets. Use only the current
task's fields. `research_case.py` exports content-addressed local preparation
packages, preserves prior versions and unknown PIDs, and never uploads or submits.
Reproduction exports require actual runner replay, result CSV, environment lock,
license and rights; no raw/private/large data or secrets enter the package.

Complete G5 for `state.active_paper`; checked continuation selects the next paper
at G3. Only the final configured paper can make the project `submission-ready`.
A deterministic local ZIP is preparation, never actual publisher submission.
Software acceptance does not complete six real papers, demonstrate 0.85 semantic
agreement, supply 20–30 real review anchors or establish doctoral/publishing merit.

## Executable experiment evidence supplement (G3 and G4)

Empirical protocols require critical_tests linking questions, rival predictions,
claim/hypothesis IDs, every comparator and explicit decision conditions. Bind the
current G1 hypothesis register when it exists. These fields are frozen with the
existing protocol; they alter no execution authority. Protected G4 summaries
expose every linked numeric decision while retaining unresolved alternatives.
Meta/theory retain their dedicated route contracts.

G3 also requires the active empirical paper's `experiment-evidence-plan.json`, following `schemas/experiment-evidence-plan.schema.json` and [the experiment evidence contract](../docs/EXPERIMENT-EVIDENCE.md). It binds claims to hypotheses, datasets, outcomes, exact comparator runs, all seeds, independent units, inference scope, practical thresholds and multiplicity families. Every design baseline, ablation, negative control and robustness condition must have executable coverage. Preregistration includes this plan; the paper-scoped G3 approval binds that paper's frozen preregistration hash. Legacy batch approvals retain their original scope. Pilot assertions and technical success criteria are locked before full runs.

At G4 the cloud control plane computes `papers/Pxx/experiment-evidence.json` from exact successful executor receipts. Claims must list every linked `comparison_ids` and source `analysis_ids`; supported claims cannot omit adverse or inconclusive confirmatory comparisons. The numerical report cannot be written by a model. Successful execution, a small p-value or passing software acceptance never establishes novelty, causal identification, scientific completion, doctoral merit or journal acceptance. Keep the G1/G2 human topic decisions and independent scientific audits.
