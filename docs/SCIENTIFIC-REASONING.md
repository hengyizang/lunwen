# Scientific reasoning and paper quality

Reviewed 2026-10-18. This extends the existing G1-G5 contracts and five role
calls. It changes no model, effort, gateway, paid service, budget, approval or
experiment execution. Engineering checks do not establish novelty, doctoral
merit or journal acceptance.

## Important questions before drafting (G1)

Every hypothesis, including candidate ideas in optional paper cards, requires
scientific_value with problem, affected_community, why_unresolved, knowledge_gain,
practical_or_theoretical_relevance, resource_fit, remaining_uncertainty and
source_anchors. Anchors use the existing path/hash/locator/bounded-excerpt format.
Importance needs actual evidence under evidence/, literature/, results/ or data/;
an author's own program, review or approval cannot be its source.

decision_test requires observable, expected_if_hypothesis, priority_reason,
continue_if, revise_if, stop_if and remaining_uncertainty. Compare the focal
prediction with each of the two or more competing explanations. Rivals may
share an outcome with one another. Different strings do not prove scientific
identifiability; the actual design, assumptions and importance still need review.
The original nearest-work, adjacent-field, search saturation, negative-result,
resource and human-G1 requirements remain.

Old registers missing these fields must be completed from real material and
audited again. The internal 1.0 schema has strengthened required fields; missing
material is never automatically filled with a plausible story. G1 receipts bind
both checker implementations and explicitly leave scientific_value_verified false.

## Distinct contribution and audience (G2)

The stage-scoped prompts ask existing actors to express the knowledge increment,
nearest-work difference, decisive evidence and scope in existing paper contracts.
Keep standalone value, reuse disclosure, six-paper independence, cloud feasibility
and current venue/article-type evidence. New evidence, a meaningful boundary or
theory can be a contribution; a new algorithm is not imposed on every study.

## Key tests tied to real comparisons (empirical G3)

papers/Pxx/experiment-evidence-plan.json now requires critical_tests. Every row has:

    test_id, hypothesis_id, claim_ids, scientific_question,
    mechanism_or_rationale, expected_if_hypothesis,
    alternative_explanations[{explanation, expected_if_true}],
    comparison_ids, priority_reason, practical_or_theoretical_relevance,
    continue_if, revise_if, stop_if, remaining_uncertainty

Every hypothesis/claim/comparison combination must be covered, including strong
baselines, controls and robustness conditions. Invented IDs, cross-hypothesis
bindings, duplicate tests and nondiscriminating focal predictions block validation.

If program/hypothesis-register.json exists, add hypothesis_register with that exact
path and its current sha256 to the protocol. Test hypothesis IDs must exist in the bound
register. A changed register invalidates the binding. The entire protocol is
already inside the paper's frozen preregistration and G3 approval.

A priority rationale is not a scheduling command or permission to omit required
comparisons. Continue/revise/stop conditions authorize no action. Keep existing
pilot dependencies, fair tuning/data/compute, sample-size justification, leakage,
negative results, statistics and clean-room replay. Never edit an executed frozen
protocol to pass a new check; use the existing approved revision/supplemental route.

Meta/theory keep their own protocols and validators, without empirical critical_tests.
Their prompts instead address extraction/dependence/bias or assumptions/proofs/
counterexamples. Reviewer-requested empirical studies retain these requirements
within their separately approved supplemental scope.

## What the evidence establishes (G4)

Protected experiment-evidence.json includes critical_test_results. Every test
exposes all linked numeric decisions, threshold_not_established_ids, remaining
uncertainty, rival predictions and declared next-step conditions. Missing/failed
comparisons stay incomplete; adverse and inconclusive evidence remains visible.

Even when all thresholds are met, mechanism_established,
scientific_significance_verified and automatic_stop_or_execution_authorized stay
false: they describe what the program itself has not established. Scientific
judgment and human decisions remain separate. Reports bind the reasoning checker
hash in addition to existing protocol, registry, software and result hashes;
saved reports are recomputed by the existing gates.

## Scientific claims and pre-review (G5)

The existing writer/remediation and fresh independent reviews examine importance,
contribution, discriminating power, statistical suitability and conclusion strength.
Use the existing categorical checklist and METHOD/STATISTICS/CONTRIBUTION views;
record serious rejection reasons, evidence, resolutions and unresolved disagreements.
Do not add paid reviewer agents for each perspective.

Abstract, introduction, discussion and conclusion must agree with the actual
effects, uncertainty and tested populations. Nonsignificance is not equivalence;
association is not causal identification. Exploration cannot be promoted to
prospective confirmation. Preserve contrary results and material limitations.
Human expertise assesses scientific meaning; a checklist or model score cannot.

## Prompt integration and cost

config/scientific-reasoning.json supplies only the current stage/role text through
research_methods.stage_context, already used by API and CLI planning, writing,
remediation and both critics. The policy is validated and its hash appears in the
prompt. Changing it invalidates exact-request response caches. The critic receives
rules, never the preferred verdict or previous review.

The added policy is capped at 5,000 UTF-8 bytes per stage/role plus a hash header.
It adds bounded input to existing calls, not another model round. Validators use
the standard library and existing evidence/numeric tools. Existing CI jobs test
the change; no new runner job or paid provider/OCR/embedding/GPU is enabled.

## Basis and limits

This is a native adaptation of the user-approved roadmap and existing research
contracts, not a new third-party skill installation. Primary guidance consulted
2026-10-18 includes the [Nature Communications reviewer FAQ](https://www.nature.com/ncomms/for-reviewers/reviewer-faqs),
the applicable [NeurIPS checklist](https://neurips.cc/public/guides/PaperChecklist),
the [ASA p-value statement](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf)
and [Clarivate's category-quartile explanation](https://clarivate.com/academia-government/blog/a-primer-on-ties-in-the-jcr/).
These do not constitute one universal Q1 standard.

Cloud fixtures check source integrity, binding coverage, adverse results and
restrained summaries. They are not real research, domain calibration or evidence
of improved acceptance odds. The current my-phd project remains at G1; this
implementation does not invent its question, data, experiments or approvals.

