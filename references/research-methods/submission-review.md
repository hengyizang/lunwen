# Evidence-anchored submission questions

Method sources: academic-research-skills, ars-codex, nature-skills, paperspine.
Based on Academic Research Skills by Cheng-I Wu,
https://github.com/Imbad0202/academic-research-skills .
The retained ARS framework and rubric use CC BY-NC 4.0; see integrations/licenses.

Use config/pre-submission-criteria.json as the pre-submission question set.
Apply seven universal dimensions: originality, methodological rigor, evidence
sufficiency, argument coherence, writing quality, literature integration and
significance. Add the criteria for empirical/computational, theoretical,
review/meta-analysis, case-study or policy work. Use the target venue's current
official criteria and reporting standards where their scope applies.

The writer independently writes reviews/pre-submission-checklist.json with
schema_version=1.0, article_type, calibration_status=NOT_CALIBRATED and checks[].
Every check contains criterion_id, criterion_source, judgement, rationale,
uncertainty, decision_bearing, resolution_test, manuscript_anchors[] and
evidence_anchors[]. Anchors use path, sha256, locator and an exact bounded
excerpt; PDF anchors also need pdf_page. Text locators must be L1 or L1-L3;
DOCX locators use paragraph 1. Manuscript anchors must belong to the canonical
TeX include tree or DOCX document, not an unused draft in the
active paper's manuscript tree.

Judgements are EXCEEDS, MEETS, PARTLY_MEETS, DOES_NOT_MEET or NOT_ASSESSED.
A genuinely inapplicable article-specific criterion may use NOT_APPLICABLE
with non_applicability_reason. Universal dimensions cannot be skipped.
Keep evidence gaps visible. A strength elsewhere cannot cancel a blocking
methodological or evidence failure. No points, weights, totals, rankings or
acceptance probabilities belong to this checklist. These criteria are not
empirically calibrated.

The control plane runs scripts/pre_submission_review.py and creates
reviews/pre-submission-review.json. It checks coverage, anchors and current
hashes and blocks unresolved criteria. This mechanical pass is not independent
scientific validation; keep the existing independent model-family reviews and
human G5 approval.

Give each critic the same immutable manuscript/evidence packet and its
predeclared focus. Exclude prior reviews, writer preferences and desired
verdicts. Freeze a review before synthesizing disagreements. Do not call
shared-context roleplay an independent or mutually blind panel. Sequential
pre-/post-remediation rounds are different manuscript snapshots, not a panel
of simultaneous blind reviewers.

Each substantive finding should identify the criterion ID, claim/manuscript
location, evidence location, decision impact, missing evidence and a
proportionate resolution test. Do not impose finding quotas or fabricate
reviewer identities. Audit arithmetic, aggregation, uncertainty, exclusions,
duplicate displays, result placement, source provenance and reproducibility
after the independent reviews. Preserve genuine disagreement.

For each rendered figure, inspect the entire figure and each panel at final
physical size. Apply the pinned Nature panel-alignment and PDF collision
helpers through scripts/figure_layout.py. A mechanical failure requires source
repair; an unauditable figure cannot be called passed. Review warnings and
retain human visual inspection. AI imagery cannot substantiate data.
