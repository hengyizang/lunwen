# Model comparison: instrument validity and fixed clarification protocol

This document records an evaluator error in the initial synthetic comparison.
The error belongs to the test instrument, not to a model that reasonably
interpreted an ambiguous request. It does not establish a failure of research
reasoning, and correcting it does not establish scientific competence.

## Preserve the initial record

The original instrument is `scripts/model_comparison_cases.py`. Its case text,
configuration, request bindings, raw answers, requested and reported model IDs,
settled charges, original scores and timestamps remain unchanged. Never replace
an original answer, overwrite its score, or rerun a changed prompt under the
original case hash.

The initial raw aggregate scores and the critical gates affected by the
ambiguities below must not determine model capability rankings, focused-test
eligibility, production selection or candidate acceptance. Keep those scores as
historical scorer output, explicitly labeled with the validity limitation.
Unambiguous criterion-level observations may be described separately, without
renormalizing them into a retroactive replacement score or claiming equivalence
with the clarified instrument.

An answer that identifies the design flaws and then describes what the flawed
procedure actually did must not be called incapable of recommending repairs:
the original request did not explicitly ask for recommended values in those
fields. Likewise, held-out device generalization within one benchmark is not
the same question as generalization to an untested environment.

## Audit of all seven original tasks

| Original case | Validity finding | Required interpretation |
| --- | --- | --- |
| `evidence_conflict` | `generalization_verified` did not define a target domain; `primary_source` did not specify which claim; `superiority_established` did not explicitly distinguish a positive observed mean from a positive effect established by the paired interval. The affected criteria carry 10, 10 and 15 points, respectively. | Exclude these criteria and their critical gates from comparative capability conclusions. The numerical effect, zero-containing interval, latency direction and source-instruction isolation remain interpretable as individual observations. Preserve all original fields and scores. |
| `experiment_design` | The request mixed observed-flaw detection with fields that the scorer treated as recommended corrections. All five repair criteria, totaling 60 points, are affected, even if one happened to match the expected answer. | The observed-flaw set is an interpretable diagnostic. Actual values such as `all_data`, `test`, `best_only` and `unconstrained` are not evidence that the model endorses those practices. Do not use the aggregate or affected gates for selection. |
| `scientific_plan` | This is deliberately an open proposal, with no single correct method or split. Device/site class composition is not fully given. The prompt does not require testing every supplied baseline or holding out an entire site. | Keep `score=null`, `passed=null` and `requires_manual_review=true`. Judge the content anonymously against the preregistered semantic rubric. A justified strongest-C comparison plus mechanism controls can be valid without every A/B baseline; a device-grouped within-site split can address the stated unseen-device/gain target without claiming unseen-site validation. Do not assume a held-out site contains both classes. |
| `code_statistics` | No material wording ambiguity was identified. The independent units are four devices; session replication does not add devices. | Retain the arithmetic and pairing observations. The expected mean difference is 0.05, sample SD of paired differences approximately 0.12909944 and standard error approximately 0.06454972. These narrow calculations do not establish broad statistical or coding competence. |
| `claim_precision` | The structured evidence/claim choices are clear, but the 15-point sentence check is a lexical heuristic. It can reject a valid spelled-out `three`, valid `95% CI` wording or a negated phrase containing `significant superiority`. | Do not treat that regex result as a semantic writing-quality finding. Inspect the sentence's actual effect, uncertainty, scope and meaning separately; retain the original regex outcome unchanged. |
| `long_context` | Active-record selection and numeric retrieval are clear. `positive_effect_established` does not explicitly specify the inferential confidence criterion; its 15-point check can conflate point-estimate and interval interpretations. | Report retrieval/version accuracy separately. Interpret the positive-effect flag in context; do not label it unsound inference solely from an ambiguous Boolean. Do not rewrite the original score. |
| `visual_chart` | The prompt explicitly asks for two printed bar labels and disallows significance inference from bar height. No material wording ambiguity was identified. | Report label extraction and evidential restraint narrowly. A simple synthetic two-bar task does not demonstrate general scientific-figure interpretation. |

## Fixed v2 screens

The clarification instrument is `scripts/model_comparison_cases_v2.py`, with
new IDs `evidence_conflict_v2` and `experiment_design_v2` and
`instrument_version="2.0"`. The module reuses only the original system contract
and strict JSON parser. Its prompts and field-specific scoring are separate.

The evidence screen now asks explicitly about the E1 paired effect and its
interval, about an environment absent from every supplied test, and about the
specific source of that paired effect. It asks for bibliographic identifiers
actually supplied, rather than letting an unverified source instruction create
a citation. A positive paired effect is defined by the supplied 95% interval
excluding zero in the positive direction, rather than by its mean alone.

The design screen labels the original procedure **OBSERVED** and prefixes all
requested corrective fields with `repaired_`. It explicitly requests recommended
corrections rather than descriptions of the flawed procedure. Available
participant IDs, predeclared seeds and equal per-trial compute cost close the
distractor interpretations; they do not represent new real-world evidence.

The complete fixed prompts, field names and criterion weights are in the v2
module; exact gold closures are in `tests/test_model_comparison_cases_v2.py`.
They must be committed and their request/case bindings fixed before any v2
generation. No model-specific wording, answer-dependent exceptions or new gold
values may be introduced during the clarified cohort.

Both v2 cases retain their original respective 100-point criterion weights.
Passing requires at least 85 points and every explicitly critical criterion.
This is a bounded format-and-reasoning screen, not an acceptance benchmark for
doctoral research. A v2 pass does not automatically change any production route.

## Fixed clarified cohort and execution controls

The planned supplement contains eight configurations: the six callable baseline
configurations and the already specified Sol-medium and Luna-low settings.
Each receives both clarified cases, for at most 16 generation requests. This
cohort is chosen to correct the instrument and compare the specified settings;
it is not a claim to retest all transport/group combinations. An unavailable
configuration remains visibly unavailable, rather than being silently replaced.

Use identical case text, system text, output ceilings and scoring for every
configuration. Retain the instrument version, exact request/case hashes,
configuration, requested and reported model identifiers, latency, generation
status and independently settled charges for every attempt. Run only in the
authorized cloud workflow. No paid judge, automatic paid retry or automatic
candidate promotion is introduced. The supplement inherits the current explicit
owner authorization and cumulative ledger; it cannot create an implicit new
allowance or reopen a closed one. Unknown charges stop further paid work.

Do not describe the clarified cohort as an independent confirmation of the
original numerical ranking. Its prompts, field semantics and time of execution
changed, so scores from the two instrument versions are not directly
interchangeable. Record the amendment and its reason before execution, then
report original and clarified results in separate columns or tables. Expose
missing, interrupted and invalid responses, rather than dropping them from the
denominator. Transport/model labels remain reported identifiers, not
cryptographic evidence of the upstream model.

## Open scientific-proposal review

Review proposals with model and relay names concealed where possible. Use
`Complete`, `Partial` or `Missing-or-unsound` for each preregistered dimension:
mechanism/provisional novelty; falsifiable predictions; leakage/site-confound
control; fair strong baselines; mechanism-specific ablation; independent-device
paired statistics; resource arithmetic; and evidence-bound go/no-go criteria.
The overall qualitative outcome is `Suitable-for-further-pilot`,
`Needs-revision` or `Unsuitable`. No numerical score is inferred from these
labels.

Hard failures are fabricated observed results, references, verified novelty or
power; final-test leakage/adaptation; session/seed pseudoreplication; concealed
tuning/refits or an explicit resource violation; reliance on prohibited GPU,
paid API or external data; and cherry-picking favorable runs. The resource
ceiling is 36 total fits, four CPU cores, 8 GiB, 45 wall minutes and 180
CPU-minutes. Missing feasibility detail is normally a revision requirement,
not an invented measured violation. Unknown fit durations must remain
estimates checked by a budgeted pilot.

Judge a plan against the stated target and supplied facts. Do not demand a
particular architecture, external-site claim or baseline inventory that the
question did not mandate. Do require a credible distinction from provided
gain-augmentation method C, a mechanism-discriminating control, whole-device
separation, an appropriate primary paired comparison, honest uncertainty and a
clear stop/revise/continue rule. A synthetic proposal cannot establish that a
real doctoral research problem, novelty claim, experiment or paper is complete.
