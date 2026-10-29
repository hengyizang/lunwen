# Specific topics and competing hypotheses

Method sources: kdense-topic-methods, nature-skills. Read the pinned originals
under third_party/kdense and third_party/nature-methods when deeper guidance is
needed. Apply this module after direction screening.

Keep the G0 direction weights for funded PhD supply, employment/salary, growth,
PhD competition, job competition, background and application-route fit.
Cloud feasibility is mandatory for every current paper. Novelty, doctoral depth
and original contribution are separate topic requirements, never tradeable
direction-score weights. Keep future laboratory extensions outside current
paper evidence.

Write program/hypothesis-register.json using
schemas/research-hypotheses.schema.json. Set schema_version=1.0,
scope=specific_topics_after_direction_screening, direction_id to the screened
direction, automatic_selection=false, and hypotheses to at least three
distinct concrete hypotheses.

For each hypothesis record hypothesis_id, hypothesis, source_observation,
precise_difference, prediction, falsifying_result, null_result_value,
source_anchors, alternative_explanations, failure_modes and test_plan.
Keep evidence_status=hypothesis and novelty_status=prior_art_search_required;
only the existing originality audit and novelty matrix can establish a
comparative novelty judgement. Do not interpret search absence as novelty.

Each source_anchor contains a project-relative path, current sha256, locator
and an exact bounded excerpt (at most 25 words and 1000 characters). PDF anchors
also require the positive PDF page index, separate from printed page labels.
For text sources use verifiable line locators such as L1 or L1-L3; for DOCX
use paragraph 1 (one-based paragraph index). An excerpt found elsewhere does
not confirm the declared location.
At least two alternative_explanations each need explanation,
discriminating_test and expected_if_true. Specify at least two failure_modes.
test_plan contains comparator, controls[], metric, dataset, cloud_execution,
budget_cny (finite, nonnegative estimate) and deadline (ISO date). An estimate
never authorizes spending. Include why a null or negative result would still
inform the research question.

Build argument_plan with research_question, allowed_claims[], forbidden_claims[],
planned_evidence[] and stopping_conditions[]. Establish facts and uncertainty
before paragraphs. Do not write favorable results before experiments run.
Materialize each paper's allowed/forbidden claims and evidence plan in its
existing paper contract, claim matrix and paragraph argument ledger.

Before drafting, compare each candidate with closest and adjacent work, use
different perspectives without manufacturing agreement, and preserve rejected
ideas with reasons. Direction-ranking weights remain separate from optional
candidate-rating weights; neither can waive originality or falsification.

The register also requires innovation_screening (schema_version=1.0):
- scope: focal_question matching argument_plan, one doctoral_question, in/out
  scope and real/assumed/negotiable/unknown constraints;
- generation: chosen method/reason, truthful contributors and represented/missing
  perspectives, prior examples, independence/deviations, hash-bound initial and
  post_evidence round records, and any cluster/merge/split events retaining originals;
- assumptions: IDs, category/status, affected candidate IDs, located evidence,
  test_or_check and failure_consequence;
- candidates: exactly one record per hypothesis with mechanism, assumption_ids,
  support/challenge anchors, evidence_gaps/search_limits, prior_exposure,
  adversarial_checks, disposition and gate_status;
- comparisons: every unordered candidate pair, mechanism/prediction differences,
  distinguishing_test, exact shared_assumption_ids and common_failure_risk;
- evaluation: explicit criteria/anchors, narrative or optional weighted_matrix,
  original/revised ratings, missingness, dissent and limitations. Never fill a
  missing rating with zero or present plausible ranges as confidence intervals.

Keep the native schema and docs/INNOVATION-SCREENING.md available while preparing
these records. Exact duplicate hypothesis/prediction/difference tuples fail;
semantic independence remains a question for the existing independent critic.
Candidates may share legitimate doctoral background assumptions. They must not
silently become unrelated doctoral topics. Retain all rejected/deferred ideas.

Record seen data, outcomes and analyses. Same-observation follow-up remains
exploratory; describe new data or untouched holdout for a future confirmatory
test. If human-first or independent generation did not happen, record that
deviation rather than inventing participants or independence. Keep adversarial
checks as proposed challenges/responses until actually independently reviewed.
The existing critic must assess candidate differences, joint failure risks,
source gaps and dispositions, and the writer resolves those findings item by item.

Choose one useful creative method for the current obstacle: assumption reversal,
boundary/scale change, source-to-target analogy with mismatches, morphological
combinations, SCAMPER, constraint ladder or failure premortem. Use the relevant
pinned brainstorming reference; do not stack all methods or manufacture an
expert panel/Delphi process from repeated model samples. Separate source-system
evidence from target-system predictions. Include an inconclusive/control-failure
condition in the minimum test, alongside existing continue/revise/stop criteria.

The control plane creates program/hypothesis-audit.json. Its pass means that
the register is structurally complete and anchors are replayable. It does not
validate the science, select a topic or approve G1.
