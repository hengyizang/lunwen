# Follow-up quality controls

This extends [the initial improvements](RESEARCH-IMPROVEMENTS.md). All research, rendering and tests run in authorized cloud jobs. Model choices, routing, roles and reasoning settings stay unchanged. These controls neither prove doctoral/Q1 merit nor authorize paid calls, compute, scientific gates or submission.

## Coverage and remaining real inputs

| Gap | Implemented control | Still needs actual research or human review |
|---|---|---|
| Scientific editing | Exact sentence/paragraph/package before-after ledger, reasons, protected facts, claim IDs and source quotes | Whether the revised claim is scientifically supported |
| Conditional prices | Exact route plus plan/group/mode, context brackets, cache rates and tool usage receipts | Current gateway quotation and actual bills; no guessed discount |
| Research notebook | Dated append-only changes and Asia/Shanghai daily briefs | Scientific interpretation of gaps, conflicts and decisions |
| Statistics | Every comparison mapped to manuscript/caption; explicit estimand, sample flow, missingness and repetitions | Actual topic-specific analysis choice and preregistered experimental results |
| Word and response letter | Genuine OOXML insertions/deletions; source, paragraph, cell and rendered PDF locations | Final visual inspection; explicitly unsupported Word edits require review |
| Figures | Actual SVG/PDF glyph/font/size checks and separate grayscale/color-vision QA copies | Mathematical semantics, final layout and accessible distinctions in the real figures |
| Clarification and primary methods | Structured question/estimand/boundaries, source-scope checks, primary design dissection and bounded worked arithmetic | Owner answers, scientific transferability and actual method pilots after G3 |
| FAIR and availability | Registered datasets, version/license/access metadata and actual retrieval receipts | Permission to share, real deposit, restricted access arrangements and data contents |
| Calibration and visual review | Blinded materials, frozen rubric, protected source key and hash-bound human rating receipts | Independent qualified raters and final review; automatic status stays NOT_CALIBRATED |
| Journal choice | Existing actual publisher retrieval, costs/policies and expiry checks | Topic-specific current venues and official JCR evidence |

Optional multimedia/Jev/Chinese-style frameworks remain deferred until a real requirement and measurable benefit exist. Provenance is retained; detector scores and watermark removal do not establish research quality.

## Controlled cloud builders

Use `program/cloud-operations.json`, maximum 16 operations per cycle. All paths are project-relative. New actions are `research_notebook_daily`, `research_support`, `support_sources`, `review_packets` and, at writing-and-review, `revision_ledger` with `paper_id`. Existing `research_notebook`, `statistical_reporting`, `docx_revision`, `compile_tex`, `render_figure` and `journal_sources` remain available.

The cloud CLI `python -m scripts.research_improvementctl` exposes `daily-brief`, `revision-ledger`, `revision-ledger-manifest`, `research-support`, `support-sources` and `review-packets`, with `--project` and `--paper` where needed. It rejects local execution. The manifest action returns actual changes for the author to explain; it does not invent explanations or authorize protected changes.

Write inputs only. Protected reports, source receipts, rendering manifests and human confirmations cannot be written by a model. A failed audit remains visible in `state/research-steps.json`; no approval is inferred.

## Revision ledger and response positions

Freeze the canonical source using the existing revision-base controller. Request `revision-ledger-manifest` after editing; populate `papers/Pxx/reviews/revision-ledger.json` with the exact source-tree hashes and every returned change ID/before/after unit. Every entry needs `reason`, `kind` (editorial or scientific), actual protected facts and scientific changes additionally need registered claim IDs and source quotes/hashes. Request `revision_ledger` to build the protected report. G5 and manual submission packaging require it whenever the frozen canonical manuscript changed. The separate existing human authorization for numbers, formulas, citations and scientific scope still applies.

In `reviews/response-matrix.csv`, the preferred location cell is a JSON object of kind `source_lines`, `docx_paragraph`, `docx_table_cell` or `pdf_lines`, with an actual source `path`, `sha256` and explicit indexes. Use the location examples in the tests and the controller's returned manifest. A legacy section name only succeeds if it identifies one actual heading and excerpt. PDF positions refer to nonempty extracted text lines on the actual PDF page; they are not verified printed line numbers.

`compile_tex` hashes the mounted manuscript/includes/figures/tables/supplement before and after the isolated render, records the implementation, cloud run and actual PDF hash, then generates protected `reviews/revision-render.json`. Source or PDF edits invalidate it. A Word paragraph is never presented as a rendered page. Missing actual Word-to-PDF conversion remains a missing input.

Supported Word operations include body and table-cell prose changes retaining unchanged citation fields, equations and pictures, and supported paragraph insertion/deletion. Resource/global-style/section/table-topology changes, unsafe drawing-ID moves and terminal-paragraph deletions that cannot round-trip are rejected. Accepting revisions must recover the clean package; rejecting must recover the baseline.

## Structured statistical reporting

Each row in `statistical-reporting-map.json` requires `reporting_semantics` alongside the existing exact field locations:

```json
{
  "estimand": "Mean paired metric difference in the registered eligible units",
  "inclusion_rule": "Exact frozen eligibility rule",
  "exclusion_rule": "Exact frozen exclusion rule, including zero exclusions when true",
  "missingness_rule": "Prespecified handling; report actual missing units",
  "uncertainty_interpretation": "CI for this estimand, with its confidence level",
  "inference_boundary": "Actual population, data split and limitations",
  "sample_flow": {"eligible_units": 20, "excluded_units": 0, "missing_units": 0, "analyzed_units": 20},
  "repetition": {"analysis_unit": "patient", "independent_units": 20, "seeds": 3,
    "aggregation": "mean_within_unit_then_mean_across_seeds", "seeds_are_independent_units": false},
  "evidence": [{"path": "papers/P01/experiment-evidence-plan.json", "sha256": "REPLACE_WITH_ACTUAL_HASH",
    "locator": "actual registered rule/sample-flow record", "quote": "REPLACE_WITH_UNIQUE_ACTUAL_QUOTE"}]
}
```

This is a synthetic format example, not study data. Flow categories must be disjoint and sum to the eligible units; analyzed n, seeds, unit and aggregation must equal actual evidence. A manuscript or its generated audit cannot support its own reporting declarations. Matching text and arithmetic do not prove the declared exclusion rules were followed; scientific review and actual flow evidence remain necessary.

## Explicit conditional billing, without changing models

Optional `DR_OS_MODEL_PRICING_JSON` schema version `2.0` holds `quotes`, each bound to exact provider/endpoint/model and explicit `plan`, `group`, `mode`, `currency:CNY`, `price_version`. Declare input/output/cache-read/cache-write rates per million, including explicit zero cache rates. Alternatively declare ordered contiguous `context_brackets` from zero to an open final upper bound, each with its own four rates. `context_basis` is `full_request_input_tokens` or `uncached_input_tokens`; cached reads cannot silently reduce full-context brackets.

`DR_OS_MODEL_BILLING_IDENTITY_JSON` supplies the exact per-provider plan/group/mode. It never becomes a model effort or inference parameter. A declared `tool_fees` entry uses `billing:flat_per_call|per_unit`, `unit`, `price_cny`; `DR_OS_MODEL_TOOL_LIMITS_JSON` supplies bounded per-provider maximum units, including explicit zero when disabled. A price declaration does not enable tools.

Tool settlement needs typed complete `usage.tool_usage` with schema `1.0`, actual provider/gateway `receipt_id`, matching `request_id` and integer-unit items. Missing or inconsistent receipts keep the reservation and block further paid requests pending explicit reconciliation. Worst-case reservations cover the expensive context tier, cache-write premiums, output ceiling and declared tool limits. No paid call is made merely to test this code.

## Human review packets

`program/review-packets.json` declares actual calibration or visual materials. The builder freezes their hashes, rubric and critical errors; blind candidate materials use opaque labels, while the protected answer key retains full source provenance and failed attempts. Do not distribute the answer key to blinded raters. Synthetic internal review text is never promoted to a scientific artifact.

Use the owner-only non-billable `review_dossier` operation `confirm_review_packet` with `packet_id` to inspect the current packet. Then `confirm_review_packet` takes the exact `expected_sha256`, a review `note` and structured `judgments`. Calibration judgments identify an independent rater and include rubric ratings, critical errors and rationales for every blinded candidate. Visual judgments include every required artifact check. Authenticated controls bind the exact dossier and record protected receipts in `state/review-packet-confirmations/` plus the human-decision audit. Changed inputs invalidate earlier ratings. Recording ratings approves no gate and changes no model configuration.

## Sources and interpretation limits

Question, method and FAIR input examples are in [Research support examples](RESEARCH-SUPPORT-EXAMPLES.md). FAIR allows controlled access when appropriate; metadata retrievability alone proves neither file contents nor deposit ownership. See [FAIR principles](https://www.gofair.foundation/fair-principles).

Color-vision simulations are approximate QA views of the rendered output, based on [Machado et al. 2009](https://doi.org/10.1109/TVCG.2009.113) and the numerical data in [colorspacious upstream](https://github.com/njsmith/colorspacious/blob/master/colorspacious/cvd.py). Original scientific output bytes and values are retained. Human mathematical, accessibility and final-size review remains required.
