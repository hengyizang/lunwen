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
ideas with reasons. Use sensitivity analysis for direction weights only;
do not let a weighted score waive originality or falsification requirements.

The control plane creates program/hypothesis-audit.json. Its pass means that
the register is structurally complete and anchors are replayable. It does not
validate the science, select a topic or approve G1.
