# Experiment and evidence extensions

The source-located closest-work object/method/result axes and structured writing
actions extend these same comparison/finding rows. Their contracts, current
contribution reporting and persistent issue history are documented in
[Evidence-first writing](EVIDENCE-FIRST-WRITING.md). Missing material remains
pending and never becomes a scientific resolution merely through a status edit.

These additions implement the engineering work from the October 10 assessment. They leave model IDs, routing, effort, budgets, G0–G5 approvals and manual submission unchanged. Tests use synthetic fixtures in GitHub Actions. A usable tool is not a reproduced scientific method, a calibrated editorial policy or a completed paper.

The owner confirmed on October 11 that no selected research question, closest methods, dataset or independent raters are currently available. Do not invent them. The saved `my-phd` project remains at G1. Actual method reproduction requires a selected method, applicable rights, a frozen design and G3 approval. Domain calibration requires actual materials and qualified independent raters.

## Operations

Use the existing `program/cloud-operations.json` queue (maximum 16 operations per cycle):

```json
{
  "schema_version": "1.0",
  "operations": [
    {"action": "research_extensions"},
    {"action": "evidence_context"},
    {"action": "calibration_analysis", "packet_id": "domain-editing"},
    {"action": "word_render", "paper_id": "P01"}
  ]
}
```

Only declare operations whose actual inputs exist. Word rendering is limited to writing-and-review; the other three are available at research stages G1–G5. The cloud-only improvement CLI also exposes `research-extensions`, `evidence-context`, `calibration-analysis --packet ID`, and `word-render --paper P01 [--source PATH]`. Outputs are protected from both API and CLI model writers, including new files and directories.

## 1. Actual method adoption

`program/research-extensions.json` has `schema_version: "1.0"` and optional arrays `methods`, `comparisons`, `reading_anchors`, `review_findings`. Omitted sections remain explicit pending inputs. Empty forms never establish completion.

Each method row needs `id`, `paper_id`, `method_tool_id`, `baseline_id`, `baseline_class` (simple/domain-standard/strong-recent), `design_path`, `fair_comparison`, `resource_rationale`, `transfer_limitations`, and `evidence`.

The builder checks the actual paper question, the baseline in that paper's design, run membership and the existing pinned method contract. Method contracts still require original example, unseen input, invalid input and independent reference validation. All actual execution remains through `method_tools.execute` → `experiment_runner`; source links or an MCP interface cannot bypass G3 or compute limits. Qualification retains failed attempts and never certifies scientific transferability.

Evidence anchors throughout this file use `{path, sha256, locator, quote}`. Quotes must occur uniquely in the actual bounded UTF-8 source; a source hash alone does not establish semantic support. Keep primary source extracts authorized and retain original provenance.

## 2. Comparability and discriminating experiments

A comparison row needs `id`, `question`, `left`, `right`, `disposition`, and explanations for any changed conditions. Each side contains `evidence` and `conditions` with population, dataset_version, split, leakage, metric_definition, comparator, tuning_budget, assumptions and independent_unit. Unknown conditions remain unknown and cannot yield a comparable disposition. A difference is recorded even when a scientist argues it does not invalidate comparison.

`disposition` is `comparable`, `not_comparable` or `insufficient_evidence`; it remains an unverified scientific declaration. Optional `discriminating_test` has hypothesis, design, observable, failure_condition, stop_rule and exactly two predictions, each with explanation and expected_observation. Identical predictions are rejected. Nothing runs or becomes resolved because this document exists.

## 3. Independent-arm statistical evidence

Experiment evidence plans now support `analysis_mode: "welch_t"` with `unit_design: "independent"`. Independent-arm `registered_result` is also supported. Existing paired plans remain compatible.

- Use globally unique independent-unit IDs in the two arms; overlapping IDs, changing coverage across seeds, non-finite observations and too-small arms are rejected.
- Repeated rows and seeds are averaged within each unit. `minimum_units` is a per-arm minimum; report total n and both arm counts. Seeds are not independent units.
- Welch intervals use unequal-variance standard errors and Welch–Satterthwaite degrees of freedom. Superiority tests the prespecified minimum effect, while equivalence uses TOST. Metric direction and family-wide interval coverage remain explicit; Holm adjustment and adverse outcomes remain in the existing report.
- Welch planning requires the existing executable Monte Carlo power protocol for the intended unequal-variance design. The interface does not silently substitute a pooled-variance power approximation.
- A custom independent result must bind both arm counts, unit design, estimand-related fields, method, comparison and every raw-output hash. Its statistical result is **not** recomputed by the importer. Clustered, hierarchical and time-dependent models still need a specifically validated registered implementation; the software does not claim universal statistical applicability.
- Statistical reporting additionally requires `treatment_units` and `comparator_units` in manuscript/caption mappings and `repetition.independent_units_by_arm` in the sample-flow declaration.

The numerical tests compare this implementation with the independent [SciPy Welch API](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind.html), including unequal sample sizes, thresholds, metric reversal and equivalence. Synthetic numerical agreement does not validate a study's assumptions.

## 4. Blinded calibration and costs

Before collecting ratings, add an `analysis` object to a calibration packet:

```json
{
  "minimum_raters": 2,
  "qualification_thresholds": {"fidelity": 3},
  "case_partitions": {"case-a": "calibration", "case-b": "holdout"},
  "cost_run_ids": ["actual-cycle-a", "actual-cycle-b"],
  "additional_cost_receipts": []
}
```

Threshold keys must exactly cover rubric dimensions. Both partitions are required; identical source hashes cannot appear across the split. Related versions of the same source still require human leakage review. The existing protected packet hashes freeze this analysis protocol with the materials. Changing it invalidates earlier ratings.

Candidate `run_ids` connect each attempt to its full recorded model cycle. Cost scopes must include planning, writing, initial/final criticism, remediation and failures, not only the successful generation. Summary aggregation uses the latest current observation for each named rater; duplicate identities across confirmation records are rejected. Until all required raters provide complete judgments, no candidate results are released.

Afterward, the summary reports dimension means/ranges, all critical errors, exact pairwise agreement, failed attempts, conservative qualification and source partitions. Any reported critical error disqualifies the candidate regardless of style scores; every rater must meet each frozen threshold. Failures remain in the denominator. This is descriptive evidence, not chance-corrected reliability, independent case-level inference, proof of noninferiority or a model-selection action. Keep `NOT_CALIBRATED` until a separately reviewed real evaluation warrants any policy change.

Recorded model costs come from the protected usage ledger, including all calls in selected runs. Unknown settlement blocks complete-cost reporting. Additional `{path, sha256, locator}` receipts must have current provenance and actual `receipt_id`, `currency: "CNY"`, `amount_cny` fields. They can cover paid validation/tool/compute costs; distinguish cash costs from unpriced human effort. The authenticated owner may include in the existing review confirmation judgments:

```json
{
  "cost_scope_confirmation": {
    "analysis_sha256": "ACTUAL_FROZEN_ANALYSIS_HASH",
    "ledger_sha256": "ACTUAL_CURRENT_USAGE_LEDGER_HASH",
    "all_calls_retries_tools_compute_and_validation_included": true,
    "no_double_counting": true
  }
}
```

Without that exact scope reconciliation, total cash cost remains unknown. When no candidates qualify, cost per qualified candidate is null, never zero. No paid calls are started by the builder and no saving percentage is assumed.

## 5. Question-scoped contexts and incremental dependencies

Optional `program/context-plan.json` contains schema_version `1.0` and a `stages` object. Each current-stage entry needs `question`, `items` and optional `dependencies`. Each item has path, reason, stance (`supports`, `contradicts`, `mixed`, `neutral`, `constraint`) and optional 1-based start_line/end_line and expected_sha256. Dependencies are additional `{path}` entries.

Actual intake/state, core/extension/hypothesis contracts and every paper contract remain complete. Sensitive paths, prior reviews, unsupported formats and escaped paths are rejected. Full-file hashes and exact snippet hashes/lines are recorded separately. Current contrary/mixed notebook sources must be included completely. Reviewers receive no prior verdicts; this source-selection contract does not make external source text trustworthy instructions.

The complete output-provenance registry, review packets and rating confirmations remain protected control-plane records and are excluded from model snapshots and selected contexts. The registry itself is preserved for deterministic audit: its anonymous material paths and original author metadata must not become a side channel for revealing blind identities.

The API path uses the packet when declared. If evidence does not fit, it stops with an explicit error instead of cutting off required text. Omitted eligible paths remain listed for further reading. Refresh reports fingerprints, changed/removed dependencies and whether an identical packet is reusable. This reuses source preparation; it does not skip new independent scientific audits or final gates. Existing exact-request caching remains tied to the complete prompt/model/configuration. No model identity, role or effort changes.

## 6. Cloud Word rendering and final review

Word rendering builds a controlled runtime from the repository's existing digest-pinned Debian/Python base. The build context contains only the fixed installation recipe. Actual conversion uses the resulting immutable image ID, no network, no capabilities, a read-only root and source, a private temporary profile, two CPUs and 2 GB RAM. Model/provider credentials are not forwarded.

Each attempt has its own protected directory, PDF, page PNGs, renderer implementation hash, input/output hashes and actual installed package versions. The base and recipe are fixed; Debian package repository updates can produce a different image on a fresh runner, and that exact image/version inventory is recorded rather than claiming byte-identical builds. To reproduce a retained environment, provision its exact image ID on the runner and set `DR_OS_WORD_IMAGE`. This variable cannot take a mutable tag or model-proposed command.

Canonical `main.docx` receives a real PDF page/line index through `revision_render`. Clean/tracked revision documents may be rendered separately with `source`; their previews never impersonate canonical pages. Visual packets accept the actual DOCX as a render input and its PDF/PNGs as outputs. Review formulas, glyphs, tables across pages, image size, references, change visibility and final layout. PDF-extracted line numbers are not printed manuscript line numbers. LibreOffice output is not certified to paginate identically to Microsoft Word. Complex visual/semantic review remains human.

## 7. Fine-grained paper reading

A `reading_anchors` row needs id, kind (`figure`, `table`, `equation`, `assumption`, `claim`), label, page, interpretation, inference_boundary, source PDF binding and controlled reader_receipt binding. A quote must appear on the exact actual PDF page; a non-text object instead needs a valid page rectangle `bbox: [x0,y0,x1,y1]`. Source maps and receipt hashes must remain current.

These anchors locate existing evidence; they do not infer reliable numerical observations from a screenshot, perform OCR automatically or certify a formula's meaning. Use the existing authorized reader with only the required pages/translation scope. Actual semantic verification remains separately visible.

## 8. Three review perspectives within existing roles

Both API and CLI critics now separately consider METHOD, STATISTICS and CONTRIBUTION before synthesizing the verdict. A perspective is not a new independent rater or a new paid model role.

`review_findings` rows need id, perspective, severity (`fatal`, `major`, `minor`), question, evidence, required_action and status (`open`, `answered_pending_review`). An answer requires actual response_evidence. Model-authored `verified_resolved` is rejected. Declared major/fatal open findings block gates and submission; an answer still requires the normal fresh independent audit and human gate. Findings and source hashes are rechecked, not trusted from an old report.

## Remaining real work

1. Select the actual research question and primary sources at G1; preserve a serious shortlist and rejection reasons.
2. Choose strong baselines, authorized data and fair resource limits; preregister and approve the actual G3 design.
3. Execute original/unseen/invalid/reference method trials and the actual study in cloud; retain all failed and adverse results.
4. Collect independent domain judgments on real English material and review cost scope; current regression cases cannot substitute for this.
5. Visually inspect the actual final manuscript, figures and revision package.

All five remain explicit because the owner has not yet supplied the corresponding materials. Engineering validation can complete independently; scientific completion cannot be asserted from it.
