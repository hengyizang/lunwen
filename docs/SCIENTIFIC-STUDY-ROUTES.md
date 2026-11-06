# Executable study routes and scientific follow-up experiments

Implemented 2026-10-17. These are software execution/validation routes. They do
not select a real topic, establish novelty, produce data, approve science or
guarantee doctoral merit/publication. Model IDs, reasoning effort, API spending
authority, G1/G2 human topic decisions, recorded automated stage checks and manual
submission remain unchanged.

## Shared execution boundary

All routes use `scripts/experiment_runner.py`, a checked G3 protocol seal, exact
plan/budget/preregistration hashes, read-only declared inputs, bounded
network-disabled Docker execution, separate output files, immutable attempt
receipts and post-run input checks. Failed/negative/inconclusive results remain.
G4 requires real executor evidence and an honestly labeled automated evidence
confirmation. Independent scientific audits remain required. G5
requires source-bound manuscript reporting and the original independent audits.

Empirical studies retain their data, power, baseline, ablation, negative-control
and clean-room requirements. The research identity selects the alternative
route; an optional flag in a model response cannot waive empirical requirements.
Mixed portfolios can contain empirical, Meta and formal-theory papers.

## Meta analysis

Declare `secondary_quantitative` / `meta-analysis` in research-identity.json.
The original-research and journal-category policy still applies: a Meta method
does not turn a literature summary into an original research contribution.

Use `papers/Pxx/study-protocol.json` following study-protocol.schema.json, with:

Set paper-contract.study_route to meta_analysis (or theory below), consistently
with the actual research identity. The schema retains the original empirical
minimum requirements when this explicit alternative is absent.

- exact executed search receipts and complete include/exclude decisions for
  every retrieved work; no silent exclusion or disappearance of included studies;
- an extraction JSON with study/cohort/outcome IDs, common effect measure,
  effect estimate, **sampling variance**, risk-of-bias rationale, source rights
  and current text-source hashes/line anchors;
- two separately attributed extractions per effect and an actual source-bound
  adjudication when they disagree. Attribution fields do not prove independent
  work; existing scientific audits assess authenticity and independence;
- prespecified outcomes, populations, comparability, estimands, practical
  thresholds, alpha, multiplicity families, precision rationale and limitations;
- two distinct original/replay run IDs and result JSON paths, exact source
  inputs and a predeclared numerical replication tolerance.

The supported engine pools independent study-level inverse-variance effects:
mean differences, standardized mean differences and already transformed log
risk/odds/hazard ratios. Estimates/variances must already be correctly extracted
or computed; raw event-count conversion is not guessed. Repeated cohorts or
dependent effects are blocked rather than counted as independent studies.
Network, multilevel and individual-participant Meta analysis require a separately
reviewed engine and must not be labeled supported by this route.

The pinned statsmodels 0.15.0 engine computes Paule–Mandel random effects,
modified HKSJ intervals with scale at least one, Q, Q-based I-squared, tau-squared,
prediction intervals when at least three studies exist, Holm-adjusted tests of
the prespecified directional practical threshold, DL sensitivity, leave-one-out
and exclusion-of-high-risk sensitivity. Egger diagnostics are reported only
with at least ten studies and identifiable standard-error variation; they never
certify publication-bias absence. Few-study instability remains explicit.
All outcomes and sensitivities are retained, including unfavorable results.

The engine is checked against the independently recorded R/metafor numerical
fixture in the pinned statsmodels tests, in addition to closed-form cases and
actual isolated cloud executions. This validates software calculations, not
clinical/engineering applicability or the underlying extraction.

## Formal theoretical research

Declare `primary` / `theoretical`. Provide exact Lean propositions and proof
sources, readable statements, assumptions, scope, proof strategies, dependency
graph, closest-result comparisons and claim mappings. Every claim needs main,
assumption-witness and scope-check obligations. These requirements replace
irrelevant empirical datasets/power/baseline fields; they do not reduce scrutiny.

The reviewed CPU profile is Lean 4.35.0 with its pinned Init/Std library. The
official release archive is checked against SHA-256
`7289597a44543246c9227b8cae501767e095ce17f6d448b95fc4a8dc97268f6d`.
Other libraries, including Mathlib, need a separately frozen and verified runtime
profile; unsupported imports fail at planning. Proof source intentionally excludes
custom metaprograms, executable directives, unfinished proofs and custom axioms.

The runtime asks Lean to kernel-check that each registered formal type is a
proposition and that the named declaration inhabits that exact type. It runs
Lean's transitive `#print axioms` inspection, accepting only propext,
Classical.choice and Quot.sound. `sorryAx`, unknown axioms, type mismatches,
compiler failures and missing obligations block evidence. A second isolated
execution must agree. Symbolic simplification and numerical examples are not
accepted as universal proofs.

The normal G4 continuation records a protected automated study-validation
confirmation of current sources, frozen protocol, actual executor receipts,
computed outputs and isolated replay. It sets `human_confirmation: false` and
does not certify interpretation or novelty. `confirm_study_validation` retains
authenticated explicit interventions; it is not a required new human stage gate.
Existing scientific audits assess assumptions, non-vacuity, scope and manuscript
correspondence. A checked formal statement is not proof that its English
interpretation is correct or novel.

## Provisioning and manuscript integration

At G3 request `study_prepare` with paper_id in program/cloud-operations.json.
The deterministic builder copies the reviewed runtime, computes source/input
hashes and an immutable identity projection, resolves the official Python base
image to a digest and provisions the fixed CPU dependencies. It changes no gate
or spending authority. The editable research identity may later acquire actual
analysis receipts and reporting locations; its frozen scientific-method
projection cannot change.

Dependencies are installed before scientific execution, without project inputs
or provider credentials. Every later runner reconstructs/verifies the exact
G3-approved toolchain file inventory and mounts it read-only. Scientific runs
have no network. No GPU or paid model is required by these engines.

After execution the control plane computes experiment-evidence.json, compares
original/replay outputs and, for Meta, independently recomputes numerical results.
The existing claim matrix must reference every assigned outcome/obligation and
both source runs. It cannot call inconclusive or exploratory evidence supported.
Full result JSONs, including sensitivities, are copied deterministically into
supplement/study-results and verified again at G5. Statistical-reporting-map.json
maps every outcome/proof to actual canonical manuscript locations; Meta values
must match estimates, counts, intervals, heterogeneity and adjusted tests.
Meta map items also carry the actual analysis_phase and decision; exploratory
follow-ups must be explicitly identified in the manuscript.

All source excerpts must have checkpoint/distribution rights. Keep copyrighted
full texts, private/raw datasets and credentials outside tracked project outputs.

## Separate internal and external follow-up experiments

After the existing real `start_revision` operation, prepare
papers/Pxx/reviews/reviewer-required-experiment-plan.json. It records exact paper,
round and a new s001-style scope ID; every immutable reviewer comment receives an
explicit experiment disposition and rationale. Record all requested experiment
comment IDs, prior outcome access, exploratory/prospective-followup status,
scientific rationale, scope/claim limits and the unchanged original G3 hashes.

The new child study is stored at
experiments/supplemental/Pxx/Rxxx/s001. It has its own plan, budget declaration,
data/quality/power/design or Meta/theory protocol, preregistration, registry and
results. Its declaration grants no extra allowance or per-paper financial cap;
all actual attempts, including failures, consume the same project total.
Model-authored child state, confirmations, registered outputs and
receipts are protected. `supplemental_prepare` initializes an **unapproved**
candidate, imports exact declared existing data/evidence and runs the same
deterministic G3 builders. It grants no execution authority.

The normal continuation uses the existing model cycle and automatic checks:

1. The existing writer and independent initial/final critics review the exact
   proposed child design, actual data quality, remaining total and parent linkage.
   The recorded audit purpose is `supplemental_protocol`; it cannot pass parent
   G5. Successful current checks permit the controller to create honestly labeled
   automated data confirmations, preregistration and a separate G3 seal. Missing
   rights or evidence remains blocked. Authenticated owner dossiers are available
   for explicit interventions, not a required step in ordinary continuation.
2. Healthy G5 continuation executes at most one approved child run per job.
   Aggregate parent and supplemental costs share the G0 compute ceiling.
   Missing approval, changed inputs, a failed attempt or an ambiguous registry
   stops execution. Data imports are restored only from exact reviewed bytes.
3. Actual child G4 analyses, complete claim coverage and isolated reproduction
   undergo the native evidence checks. The controller records their current hashes
   with `decision_kind: automated` and `human_confirmation: false`. This does not
   certify scientific meaning or approve parent G5.
4. Map every new result into the actual revised parent manuscript. The reviewer
   audit blocks missing requests, missing approval/confirmation, changed results
   and missing or incorrect reporting. Existing response coverage, independent
   audits and the checked automatic G5 decision still apply.
   Supplemental approvals, inputs, attempts, results, exports and reporting maps
   are hashed into the reviewer audit and parent G5 approval; any change requires
   a fresh review. Read-only validation remains available during final approval
   and submission packaging, without authorizing another experiment.
   Raw/private inputs retain their approved hashes across checkpoint restores;
   final package hashing does not download them or require their continued presence.
   Their actual bytes are checked before scientific use under the existing controls.

Do not re-freeze the original study after execution. A changed proposal needs a
new supplemental scope and new approval. Failed attempts are never retried or
deleted automatically. `retire_supplemental` lets the owner seal an inspected
failed scope with a reason, retaining logs/costs and requiring an explicit failure
statement in the manuscript. It grants no scientific result; requested experiments
remain incomplete until a separate approved scope supplies the required evidence.

Internal scientific findings use the same executor at
`experiments/supplemental/Pxx/Ixxx/s001`, with `trigger_kind: internal_review`
and `source_review: {path, sha256}` referencing an actual protected independent
G5 review receipt. Stable `internal-...` comment IDs come from that audit's
findings, exposed to the existing remediation call. An internal finding is never
recorded as an external reviewer round. Its parent protocol and original results
remain unchanged, and every I/R scope is included in cumulative compute costs.
Pending protocol work uses experiment-design guidance; publication style and
package checks resume for the full parent paper. Internal studies, confirmed
outputs, failed attempts and reporting maps remain part of the paper's review
binding, including when another paper becomes active.

## Topic-specific candidates

Timestral is an owner-selected **deferred candidate**, recorded on 2026-10-17,
for a future time-series, equipment-sensor or industrial forecasting study.
The [official announcement](https://mistral.ai/news/timestral/), accessed
2026-10-17, describes probabilistic multivariate forecasting and CPU inference.
These are upstream claims, not validation on this project's data or runners.

Reassess only when the actual topic needs forecasting. Before scientific use,
review and pin the exact model revision, license, dependencies and weight hashes;
verify dataset rights and leakage-safe temporal splits; measure feasibility on
the existing cloud CPU runner; and preregister fair baselines, metrics, uncertainty,
compute limits and isolated replay under the existing G3/G4 controls.

Candidate status does not install or enable a model, select a topic, change
language-model roles, grant spending, rent a GPU or substantiate a paper claim.
Do not add it to the reviewed runtime lock until those checks are complete.

## Reviewed sources and software acceptance

The project's existing scientific-skills integration and statsmodels acceptance
informed the evidence-first, assumption-checking and uncertainty approach.
We reuse the installed statistics library rather than
install another agent framework or change model roles. SymPy was considered
for algebraic checks; Lean kernel checking is the accepted proof route here.

- [Pinned statsmodels source and tests](https://github.com/statsmodels/statsmodels/tree/b6b382183676557763bd12ce561b61e1f08c9258/statsmodels/stats).
- [combine_effects and PM/DL/HKSJ documentation](https://www.statsmodels.org/stable/generated/statsmodels.stats.meta_analysis.combine_effects.html).
- [Lean 4.35.0](https://github.com/leanprover/lean4/releases/tag/v4.35.0), Apache-2.0, commit eb6cafb7290e8bd5f2937522d8d804f58f02bafc.
- [Lean's proof/axiom validation guidance](https://lean-lang.org/doc/reference/latest/Axioms).
- [SymPy](https://github.com/sympy/sympy), evaluated as an auxiliary algebra system.

GitHub Actions' dedicated study-routes job executes synthetic Meta and theoretical
studies through real no-network Docker, invokes Lean's real kernel, exercises
owner approval/confirmation for a supplemental study, checks original G3 bytes,
and verifies manuscript reporting. Synthetic identities/approvals are software
fixtures only. No paid provider call, live project gate or scientific-completion
claim is made by acceptance.
