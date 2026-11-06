# Stage contracts

Current financial policy: [TOTAL-COST-POLICY.md](../docs/TOTAL-COST-POLICY.md).
Only cost accounting and configured cumulative project totals are financial
controls. Older payment approval or fixed-tranche examples below do not apply.

The owner's current policy requires human decisions for the doctoral topic and
each paper topic only. Other research-stage decisions use evidence-bound
automated records. Preserve every
scientific, source-rights, budget, identity and execution check; unknown
evidence remains unknown. Missing rights, data or successful execution block the
affected work; they are never converted into invented human approval.
Quality reports at G1/G2 require their human-topic-review flag; G3/G4/G5 use
automated decisions. A legacy report flag never creates or replaces authority.

Current review-remediation contracts: [REVIEW-REMEDIATION.md](../docs/REVIEW-REMEDIATION.md).
Formal G1-G5 quality reports use schema 1.2 factual assessments. The current
novelty matrix uses 1.1 source-bound candidate/prior-work comparisons, bounded
retrieval dispositions and actual initial/final independent novelty assessments
at G1/G2/G5. G2 scientific bindings preserve primary outcomes and falsification
conditions through G3-G5; negative-result plans, typed dependencies and thesis
claim/result alignment retain failures and uncertainty. Empty templates and
legacy scores are not evidence and cannot waive these requirements.

Scientific reasoning: [SCIENTIFIC-REASONING.md](../docs/SCIENTIFIC-REASONING.md)
strengthens source-bound problem value, discriminating tests and conclusions in
the existing G1-G5 contracts. Missing inputs block; completeness never proves
scientific validity, doctoral merit or Q1 acceptance.

Experiment/evidence extensions: [RESEARCH-EXTENSIONS.md](../docs/RESEARCH-EXTENSIONS.md).
Declared comparability, pinned baseline adoption, fine-grained reading anchors and review worklists are revalidated at research gates. Actual topics, data and method trials remain required; optional human calibration needs real attributed ratings when requested. No template or regression fixture fills those gaps. Model routing and effort remain unchanged.

Follow-up quality input and receipt contracts: [RESEARCH-IMPROVEMENTS-FOLLOWUP.md](../docs/RESEARCH-IMPROVEMENTS-FOLLOWUP.md). Changed frozen canonical manuscripts require a complete revision ledger at G5; statistics require explicit sample-flow/missingness/repetition declarations bound to actual sources. Optional research-support and review-packet inputs require fresh protected audits when present. Their reports and human ratings never establish scientific completion automatically.

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
- direction ranking weights for funded PhD position supply, employment and salary, future growth, separately scored funded-PhD and job-market competition, background fit and application-route fit, applied only after feasibility and data-rights screening;
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
- automatic broad-data evidence followed by Codex scientific-fit screening against the human-confirmed G0 ranking weights; preserve rejected datasets and unresolved license, sample, bias, leakage, compute and external-validity concerns.
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
decisions still require the actual current independent assessments, verified
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

- `program/paper-map.json` conforming to `schemas/paper-map.schema.json`, including every pairwise paper comparison, independently sufficient primary evidence, standalone value and a justification for any shared outcome;
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
- `program/venue-candidates.json`, generated from a local authorized JCR export, with at least two current SCI/SCIE candidates meeting each paper's declared Q1/Q2 target and current official policy links; the six-paper portfolio needs at least three Q1 targets;
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
machine-frozen plan and the native runner with independent initial/final audits.
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

Scientific drafting is the default. A frozen paper contract can declare its
initial `writing_phase`; the controller stores the current paper phase in the
existing `state.writing_phases`, without editing the frozen contract. Scientific
drafting retains source/fact/citation/numeric/claim integrity, the result-to-claim
argument, current revision records and fresh independent initial/final audits.
It does not require every editorial criterion, venue check or package file each
cycle, and cannot pass final G5. Passing scientific checks and both audits lets
the controller record `submission` for the next G5 cycle. Submission runs all
final requirements below and fresh submission audits; scientific receipts cannot
approve the final package. Existing sealed legacy submission states keep that
scope. No extra human stage decision is required.

Every G1-G5 cycle also appends the actual current decision to
`program/research-notebook.json`: `cycle_id`, stage/paper, phase, outcome,
discriminating test, decision, rationale, next action, evidence IDs, failure
condition and stop rule under the relevant question. Pending/unchanged decisions
can state explicit missing evidence; changed claims require actual evidence.
The final independent audit binds that current record. G0 is exempt, and this
record adds no report, paid role or automatic claim of scientific improvement.

Apply [evidence-first writing](../docs/EVIDENCE-FIRST-WRITING.md) in existing
records: current paragraph takeaway/warrant preparation, located three-axis
closest-work comparison, design-specific contribution facts tied to real executor
outputs, and an explicit frozen-expectation versus observed-outcome review.
The existing manuscript and increment audits revalidate these at G5 and packaging.
Missing inputs block preparation; scientific meaning still requires the existing
independent scientific review. Human selection is limited to G1/G2 topics.

Revalidate the actual study identity and selected venue's research-article policy.
Secondary quantitative studies need successful approved executor evidence; the
manuscript must state the actual secondary/Meta method at a verified canonical
location. Keep the review/synthesis scientific checklist when applicable even if
the publisher calls the paper Research. The dedicated study routes supply the
applicable Meta/formal-theory G3/G4 checks; unsupported methods remain blocked.

At submission, the complete [editorial skill contract](../docs/EDITORIAL-SKILLS.md) applies: Humanizer H01–H26 and defensive AD01–AD08 are reviewed in the existing writer/remediation calls with individual reasoned dispositions; the protected academic audit is recomputed. An extra remediation call is unnecessary only when the initial independent audit has no actionable findings and the writer already supplied all applicable dispositions. The fresh independent final audit and decision log remain required. Mandatory [automatic manuscript hygiene](../docs/MANUSCRIPT-HYGIENE.md) cleans eligible source prose before builders, scans after each pass, and is recomputed at G5 and packaging. Protected originals, differences, current source hashes and unchanged authorship ancestry are required; unknown statistical watermarks never become a passing absence claim. The optional explicit watermark_cleanup operation still creates traceable candidates only. Scientific meaning, disclosure and G1/G2 topic decisions remain protected.

A source-bound internal review may request a separate `Ixxx` supplemental study;
real external reviewer requests retain `Rxxx`. Both use the existing child
protocol, executor and cumulative total. A `supplemental_protocol` audit can seal
only that reviewed child design. Its automated result confirmation records
evidence checks, not scientific validity or parent G5 approval. Full parent
manuscript and independent G5 audits resume after actual results are reported.

Required:

- fresh passing `reviews/statistical-reporting.json` from the cloud control plane, with `statistical-reporting-map.json` covering every registered comparison, independent sample counts, seed/repetition layers, uncertainty, raw/adjusted p, multiplicity, assumptions and actual Methods/Results/caption locations; no omission of adverse results;
- if a tracked DOCX revision package exists, a fresh passing `reviews/docx-revision.json` and verified clean/tracked/baseline/response hashes and accept/reject round trips; real Word visual inspection remains mandatory.

- manuscript source, figures, tables, supplement and data/code availability statements;
- citation audit with zero unresolved fabricated/unverified references;
- passing `reviews/ref-verify.json` for DOI-bound abstract-level topline and numeric claims, while mechanism, procedure, table and figure claims retain exact full-text evidence locations;
- two simulated review rounds and itemized response matrices;
- when real reviewer rounds have been opened, complete coverage of the exact
  frozen external comments, source-bound responses and a fresh protected
  reviewer-round audit; simulated reviews cannot fulfill this requirement;
- a current, venue-bound official AI disclosure policy assessment and verified
  statement location where required; no automatic AI-generated branding;
- a fresh configured-statistical-watermark assessment, with unknown schemes
  explicitly unassessed; missing configured prerequisites and positive results
  require resolution, while a negative result never proves universal absence;
- `reviews/pre-submission-checklist.json` conforming to `schemas/pre-submission-checklist.schema.json`, covering all seven universal criteria and the applicable article-type criteria in `config/pre-submission-criteria.json`; every assessed criterion needs current manuscript/evidence anchors, rationale, uncertainty and a resolution test. Run `scripts/pre_submission_review.py` to generate the protected `reviews/pre-submission-review.json`. Unresolved criteria block G5; judgements are categorical and never aggregated into acceptance odds;
- passing, current `reviews/revision-trace.json` proving promised response-matrix changes are present, and `reviews/revision-integrity.json` proving numeric, citation and claim-strength changes match the exact source-bound revision record. Current independent audits assess the scientific meaning;
- official venue manifest and imported template inventory;
- passing venue compliance report and successful compile/render when tooling permits;
- author contributions, conflicts, funding, ethics and AI-use disclosures;
- current JCR/venue-policy re-verification;
- current output-provenance hashes showing no packaged manuscript, table, figure, supplement, disclosure, response or cover-letter file was persistently written by Claude/Anthropic;
- figures registered in `figures/figure-provenance.json` and rendered by deterministic local code from recorded data, with current input, run, output and non-Claude renderer hashes retained, plus actual rendered-file visual/English-label checks bound to model identity and the central usage ledger;
- native publication figures retain a hash-bound layout audit generated at export: panel-alignment checks and final-PDF text/line collision checks are recomputed at G5. A missing dependency, stale source or mechanical failure cannot pass; the actual final rendering also needs a current automated visual record;
- all manuscript-bound text—including title, abstract, body, captions, tables, supplement, responses and cover material—written in English, with `scripts/manuscript_language.py` passing on the final manuscript source.
- `style/academic-style-audit.json` generated by `scripts/academic_style.py`, passing and hash-matched to the current manuscript source tree. Resolve its line-level academic findings—including stock phrasing, conversational artifacts, empty significance claims, vague attribution, mechanical transitions, repeated openings/sentences and excessive sentence-length patterns—without changing scientific meaning, numbers, equations, citations, limitations or uncertainty. Reviewed GitHub pattern sources must be recorded in the report; optional local grammar tools remain advisory. This is a writing-quality control, not an AI-authorship detector or evasion tool.
- evidence-led result placement: lead the abstract and conclusion with the strongest supported contribution and its decisive evidence. Reframe the narrative when a different bounded contribution is better supported, retaining original hypotheses, outcomes and actual analysis phases. Use the existing claim/argument records; a scope or frozen-protocol change still follows the approved revision route. Every registered outcome remains locatable in the manuscript or supplement. Main-text versus supplement placement follows predeclared role, relevance and statistical adequacy rather than result direction; primary outcomes, falsification tests, required baselines, material robustness failures and interpretation-changing results stay visible in the main text. State exact advantages under justified comparison conditions; material limitations qualify the relevant claim once, without repeated apologetic caveats. Apply [the evidence-led narrative guide](../docs/EVIDENCE-LED-NARRATIVE.md).
- an applicable reporting-guideline checklist routed from `references/reporting-guidelines.md`, with manuscript locations and explicit reasons for genuinely non-applicable items.
- a current `reviews/paper-facts.json` plus passing `reviews/manuscript-audit.json`, covering source-bound facts, canonical claims, allowed versus actual inference strength, result status, title/abstract/question/results/conclusion anchors, theory→measurement chains, paragraph argument roles, terminology/acronyms and mathematical symbols;
- current concern-card artifacts for the final simulated or external review set: original comments, one card per comment, coverage JSON, internal full response, concise venue-budgeted response and editor/Area Chair summary;
- when Word is canonical, `manuscript/main.docx` plus current `reviews/docx-build.json` bound to non-Claude Markdown/metadata sources and an actual source-bound automated visual inspection.

Result-bearing charts still require deterministic data/run provenance. An optional conceptual illustration from GPT Image or a user-operated ChatGPT web session is separate: the source/prompt hash, claimed model ID, named visual inspection and AI-use disclosure location must be registered before it can appear in the package. Such imagery cannot substantiate a result, replace a method/data chart or hide uncertainty.

Complete G5 for `state.active_paper`. In independent execution, a checked machine decision moves the next configured paper to G3; only the last paper can move the project to `submission-ready`. After a paper is marked `submission_ready`, `scripts/submission_package.py` may create a deterministic local ZIP and manifest. Actual publisher submission remains outside this research workflow; agents do not log into portals, upload or submit.

## Executable experiment evidence supplement (G3 and G4)

Empirical protocols require critical_tests linking questions, rival predictions,
claim/hypothesis IDs, every comparator and explicit decision conditions. Bind the
current G1 hypothesis register when it exists. These fields are frozen with the
existing protocol; they alter no execution authority. Protected G4 summaries
expose every linked numeric decision while retaining unresolved alternatives.
Meta/theory retain their dedicated route contracts.

G3 also requires the active empirical paper's `experiment-evidence-plan.json`, following `schemas/experiment-evidence-plan.schema.json` and [the experiment evidence contract](../docs/EXPERIMENT-EVIDENCE.md). It binds claims to hypotheses, datasets, outcomes, exact comparator runs, all seeds, independent units, inference scope, practical thresholds and multiplicity families. Every design baseline, ablation, negative control and robustness condition must have executable coverage. Preregistration includes this plan; the paper-scoped G3 approval binds that paper's frozen preregistration hash. Legacy batch approvals retain their original scope. Pilot assertions and technical success criteria are locked before full runs.

At G4 the cloud control plane computes `papers/Pxx/experiment-evidence.json` from exact successful executor receipts. Claims must list every linked `comparison_ids` and source `analysis_ids`; supported claims cannot omit adverse or inconclusive confirmatory comparisons. The numerical report cannot be written by a model. Successful execution, a small p-value or passing software acceptance never establishes novelty, causal identification, scientific completion, doctoral merit or journal acceptance. Keep the G1/G2 human topic decisions and independent scientific audits.
