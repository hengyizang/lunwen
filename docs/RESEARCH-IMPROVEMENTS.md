# Research quality and efficiency improvements

This increment applies the worthwhile gaps identified in the 19-article assessment. It does not install complete upstream frameworks, change model routing, rent compute, make paid API calls, approve a scientific gate, or establish a paper's scientific completion. Model selection and reasoning effort remain unchanged at the owner's request on 2026-10-09.

## Scope and limits

| Improvement | Implementation | Remaining scientific work |
| --- | --- | --- |
| Scientific meaning during editing | Numeric/unit/negation/uncertainty/citation context signatures, TeX/Word formula protection, DOCX citation fields and links, inspect-only Unicode findings, exact human authorization | Conservative checks can flag legitimate edits or miss semantic changes; independent human scientific review remains necessary |
| Complete model replies | Responses status, Chat finish reason and Claude stop reason; refuse truncated/refused/tool-only replies before persistent writes; billable failures remain recorded; cache schema changed | Actual gateway acceptance requires the user's credentials; absent termination metadata blocks authorized cloud calls |
| Billing identity | Provider/endpoint/model scoped quotes, quote version, cache read/write and total output billing; unknown cache pricing keeps the reservation for reconciliation | Supply verified CNY quotes; official dollar prices and channel multipliers are not invoices |
| Evidence and decisions | Question-centred notebook with opposing evidence, reading scope, hashes, locators, failure conditions and stop rules; append-only incremental snapshots | Interpretations and decisions require review and cannot grant G0–G5 approval |
| Paper-method reuse | Pinned source/license/entrypoint contracts, four validation categories, evidence-bound cloud qualification, runner delegation | Select relevant methods after G1; reproduce actual methods after approved G3; no fabricated pilot qualification |
| Statistical reporting | Rerun actual experiment evidence; map every comparison to Methods/Results, and captions when applicable; preserve adverse/exploratory evidence | Choose suitable designs/estimands/tests and review semantic meaning; mechanical matching is not statistical or causal validity |
| Actual figure QA | Editable SVG text, expected label checks, PDF physical size/font measurements and separate grayscale previews | Review mathematical labels, color-vision discrimination and readability at final publication size |
| Word revision package | Real OOXML `w:ins`/`w:del`, clean/tracked/response/change-note package, source hashes, accept/reject round trips | Text paragraph changes supported; structural or changed fields/equations/images/tables are refused; Word visual inspection remains required |
| Journal economics and policies | Dated official-source APC, tax, OA choice, waivers, page charges, review-time definitions, portal and AI policies | Official evidence and authorized JCR information must be supplied/rechecked; no acceptance probability or guaranteed decision date |
| Editing/review evaluation | Engineering counterexamples including legitimate scientific qualifiers; offline evaluator | NOT_CALIBRATED; add field-specific blinded human evaluations before any model/effort downgrade |

Original files and scientific provenance are preserved. No AI detector score, watermark removal, image regeneration or style preference can authorize changes to science. Optional Jev sorting, multimedia interpretation, screenshot-to-PPT and Chinese style tooling are deferred until an actual task and measured net benefit justify them; they are not missing prerequisites for English scientific manuscripts.

## Cloud entry points

Use the existing authorized GitHub cloud cycle. `program/cloud-operations.json` now accepts these additional deterministic actions:

```json
{
  "operations": [
    {"action": "research_notebook", "stage": "topic-intelligence"},
    {"action": "method_tools", "stage": "experiment-design"},
    {"action": "journal_sources", "stage": "paper-architecture"},
    {"action": "journal_dossiers", "stage": "paper-architecture"},
    {"action": "statistical_reporting", "stage": "writing-and-review", "paper_id": "P01"},
    {"action": "docx_revision", "stage": "writing-and-review", "paper_id": "P01"}
  ]
}
```

Only request an action when its input artifacts exist. This queue does not expose arbitrary commands or a method execution bypass. The method operation inspects contracts and available registered validation evidence; it does not execute experiments.

For explicit cloud maintenance, `python scripts/research_improvementctl.py ACTION --project SLUG --paper P01` supports `notebook`, `statistics`, `word-revision`, `journals`, `method-contracts` and `style-eval`. The CLI refuses execution outside a cloud executor. Tests and research execution must occur in cloud jobs, not on the owner's PC. It never calls a paid model.

Generated notebook history, method reports, statistical reports, journal dossier reports and Word packages are protected from API writer bundles. Repeating an unchanged notebook does not append another snapshot. Changed source hashes block stale interpretations instead of treating missing evidence as zero.

## Question notebook

Author `program/research-notebook.json` with `questions`:

```json
{
  "questions": [{
    "id": "Q1", "question": "What boundary makes the proposed mechanism fail?",
    "evidence": [{
      "id": "E1", "stance": "contradicts", "read_scope": "abstract",
      "observation": "Describe the source observation without inventing full-text reading.",
      "source": {"path": "evidence/authorized-source.json", "sha256": "CURRENT_SHA256", "locator": "abstract / record ID"}
    }],
    "decisions": [{
      "phase": "idea", "decision": "Investigate the boundary condition", "rationale": "Explain why",
      "evidence_ids": ["E1"], "failure_condition": "Prespecified adverse result", "stop_rule": "Frozen stopping rule"
    }],
    "missing_evidence": ["Full-text method details still unavailable"]
  }]
}
```

Stances: `supports`, `contradicts`, `mixed`, `unknown`. Reading scope: `metadata`, `abstract`, `fulltext`, `experiment`. Phases: `idea`, `planned`, `running`, `exploratory`, `confirmatory`, `failed`, `stopped`. These describe the author's record; they do not certify experimental registration. Omitting contrary evidence from a decision needs an explicit `contrary_evidence_rationale`. Outputs: `reports/research-notebook.json`, `.md`, and `-history.jsonl`.

## Statistical mapping at G5

`papers/Pxx/statistical-reporting-map.json` contains one row per actual `experiment-evidence.json` comparison. All registered comparisons, including negative, ablation, robustness and exploratory comparisons, must be covered exactly once. For each row:

- `comparison_id`, `reporting_notes` covering exclusions/missingness/repetition/assumptions; `has_figure: true` if figure reporting is present.
- `locations`: field, project-relative path within this paper's final materials, unique actual quote, section (`Methods`, `Results`, `Caption`, `Table`, `Supplement`), and exact evidence `value` for semantic fields.
- Numeric fields have `decimals` from 0–12. Only `ci_confidence` supports explicit `display_scale: 100` for percentage display. Numeric conversions in other fields are refused.

Required fields: `method`, `analysis_unit`, `independent_units`, `estimate`, `ci_low`, `ci_high`, `ci_confidence`, `p_value`, `p_adjusted`, `seeds`, `aggregation`, `family`, `family_size`, `direction`, `assumptions`, `sample_size_rationale`, `decision`, `analysis_phase`. Both Methods and Results anchors are required; declared statistical figures also need caption anchors. The independent sample count cannot be substituted with the seed count. CI confidence locations must declare `uncertainty: "CI"`; SD or SE are not interchangeable.

Example location (replace quote and values with actual manuscript/evidence):

```json
{"field":"ci_confidence", "path":"papers/P01/manuscript/main.tex", "section":"Results",
 "quote":"The estimated difference was 0.12 (95% CI, -0.10 to 0.35).",
 "value":0.95, "decimals":0, "display_scale":100, "uncertainty":"CI"}
```

The author can use readable prose while the mapping's `value` preserves the machine decision. The report explicitly does not verify that a paraphrase entails its mapped scientific meaning. G5 requires a fresh passing `reviews/statistical-reporting.json`, produced by the control plane against rerun numerical evidence. Seed effects and within-unit repetitions remain separate from independent units. Existing registered custom analyses are hash-bound; their statistical appropriateness still requires review.

Methods/Results locations must belong to the canonical manuscript and its actual TeX includes; unrelated draft files cannot satisfy these anchors. Figure build records sharing a comparison's claim IDs require a caption anchor even if the proposed map sets `has_figure` to false. Numeric matching distinguishes registered `20` from `120`, supports sentence punctuation, and preserves declared precision.

## Pinned method-tool contracts

`program/method-tools.json` has `tools`. Each tool needs:

- Unique `id`; `source.repository` HTTPS GitHub URL, full 40-character `source.commit`, `source.paper_url`; `applicability` and `limitations`.
- `license` and `entrypoint`, each with project-relative `path`, current `sha256`, and `locator`.
- Non-empty `run_ids` already present in `experiments/plan.json`. Every run must explicitly invoke the pinned entrypoint as an argument and include it in the approved input hashes.
- `validation` for exactly the four categories `original_example`, `unseen_input`, `invalid_input`, `reference_comparison`. Each has `run_id`, declared executor `output`, and prespecified `success_rule`. The reference comparison also has a hash-bound JSON `reference` containing `expected_values`, a justified non-negative `absolute_tolerance`, and `tolerance_rationale`.

Each executor validation output contains `method_tool_id`, `validation_kind`, `passed`, and non-empty `checks` with `name`, `actual`, `expected`. Reference values are reloaded from the frozen reference instead of trusting a model's claimed expected number. Recorded outputs and all attempts are checked against the current G3-approved plan; a failed validation attempt remains pending for disposition. `cloud_checks_passed` is engineering qualification, not proof of scientific applicability.

`scripts.method_tools.execute` delegates only declared run IDs to `experiment_runner.execute`, which retains existing cloud, isolation, plan, dependency and budget checks. No MCP direct command executor is added. A GPU/API-dependent method keeps that dependency after wrapping; wrapping does not make paid resources free.

## Word revisions and package consistency

Inputs are the canonical `manuscript/main.docx`, `reviews/revision-base/main.docx`, a current passing revision-integrity report/authorization, and a passing response trace for `reviews/response-matrix.csv`.

Outputs under `submission-materials/revision/`: `clean.docx`, `tracked.docx`, `response-matrix.csv`, `changes.md`; receipt: `reviews/docx-revision.json`. The creator is accurately recorded as Doctoral Research OS. Accepting tracked revisions reconstructs the clean document; rejecting reconstructs the baseline. Non-document package resources must match, preserving unchanged references, styles, images and equations. Changed complex content is refused, rather than converted to plain text. G5 and manual submission packaging recheck hashes and round trips. A passing XML check does not replace opening and visually checking Word/PDF.

Specification references: [Microsoft inserted runs](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.insertedrun?view=openxml-3.0.1), [deleted runs](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.deletedrun?view=openxml-3.0.1).

## Journal dossiers

`program/journal-dossiers.json` has `journals`, each with a unique existing `venue_id`, `official_domains`, and all seven `fields`: `apc`, `page_charges`, `oa_policy`, `waivers`, `review_time`, `submission_url`, `ai_policy`.

Every field is either `{status: "unknown", reason: "..."}` or `verified` with a concrete `value`, official HTTPS `url`, preserved UTF-8 source `path`/hash/locator, matching `quote`, `accessed_at` and `expires_at`. Evidence expires within at most 120 days; dates require timezones. Fees include `currency` and `tax: included|excluded|unknown`. OA is `optional|required|subscription|diamond`. Review time includes `definition`, `statistic`, `historical_period`; it is historical information, not an individual promise. Hash matching and an official-domain claim still require human assessment that the source/value is authentic and interpreted correctly. Existing candidate/JCR requirements remain authoritative.

Request `journal_sources` first to retrieve the declared publisher URLs through the existing public-HTTPS network safeguards. It performs at most twenty bounded, non-billable GETs per operation, uses a seven-day hash-checked cache and records pending URLs for a later operation (at most 140 URLs per project plan). Failed sources have a six-hour cooldown so they cannot starve remaining journals. Protected `evidence/journal-sources/index.json` records actual retrieval time, final URL, normalized and raw hashes. Copy the resulting exact source path/hash/retrieval time into each field before `journal_dossiers`. A model-written text file or invented receipt cannot satisfy this check. Fee numbers must occur in the actual quoted publisher passage. Expired, changed or missing sources block stale dossiers at G5.

## Pricing and quality evaluation

`DR_OS_MODEL_PRICING_JSON` retains legacy exact model keys. It also supports the more specific key `PROVIDER|ENDPOINT|MODEL` plus `provider`, `endpoint`, `currency: CNY`, `price_version`, `cache_read_per_million`, `cache_write_per_million`. Legacy quotes remain labelled `legacy-model-only`, not silently presented as channel-specific invoices. Endpoint/provider mismatches are refused before transport. Cache tokens are accounted once; output totals already include reasoning. Unknown cache billing retains the reservation and blocks another paid request pending reconciliation. No autonomous paid generation retry is introduced.

`config/scientific-editing-eval.json` is a regression dataset, with harmful changes and legitimate edits. It does not claim domain calibration, AI detection accuracy, equal quality across models, or a percent cost saving. Actual model comparisons need separately authorized cost ceilings, frozen evidence/tasks, blinded scientific judgments, all attempts, critical-error criteria and total qualified-task cost. Existing pre-submission review remains NOT_CALIBRATED.

## Validation

GitHub CI runs all unit tests, script compilation, repository manifests, cloud checkpoint/recovery, synthetic gateway acceptance, human controls, registered experiment evidence and Windows syntax checks. New regression coverage includes termination states, billable truncation, cache/reasoning accounting, scientific counterexamples, sample-size and CI/SE errors, omitted adverse results, incremental notebook hashes, genuine Word accept/reject, preserved objects, stale journal quotes and method-runner delegation. No real scientific experiments or paid gateway evaluations are implied by passing these engineering checks.
