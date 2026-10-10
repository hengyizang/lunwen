# Source-bound research support examples

These are synthetic contract examples, not project findings. Replace placeholders with actual records. A placeholder hash or fabricated source receipt must fail. Research, retrieval and validation run only in the authorized cloud runner. These aids grant no scientific gate, data rights, paid call or upload.

Edit `program/research-support.json` with `schema_version: "1.0"` and optional arrays `clarifications`, `method_dissections`, `data_availability`, `metadata_sources`. Request `research_support` to build protected `reports/research-support.json`; its statuses are `pending_inputs`, `blocked`, `needs_scientific_review`. `support_sources` performs explicitly requested bounded public metadata retrieval. Refresh never fetches implicitly.

## Clarify the human question

A vague request such as “find a strong topic and prove the method works” omits the population, comparator, outcome and falsification boundary. The following format exposes those missing decisions before generating a solution:

```json
{
  "schema_version": "1.0",
  "clarifications": [{
    "id": "Q-SYNTHETIC",
    "question": "Which out-of-sample population should the proposed benchmark address?",
    "estimand": {
      "population": "Proposed benchmark units; owner confirmation pending",
      "intervention_or_exposure": "Candidate method under the frozen comparison protocol",
      "comparator": "A version-pinned domain-standard baseline",
      "outcome": "A preregistered metric",
      "time_horizon": "Prespecified evaluation period",
      "unit_of_analysis": "Independent benchmark unit, not seed or repeated prediction"
    },
    "assumptions": [{"status": "proposed", "statement": "Evaluation units are independent.",
      "failure_consequence": "Account for clustering and reassess precision."}],
    "boundaries": {"included": ["Prespecified benchmark population"], "excluded": ["Causal conclusions"],
      "inference_ceiling": "No inference beyond the actual design and evidence."},
    "pending_owner_questions": [{"id": "OWNER-POPULATION", "question": "Which population is intended?",
      "choices": ["Benchmark population", "Separately sampled external population"], "status": "pending_owner"}]
  }]
}
```

All six estimand components are required. Assumptions must be `proposed`, `source_supported` or `unresolved`; source-supported assumptions require actual source anchors. Included/excluded boundaries cannot conflict. This builder cannot mark owner questions answered or infer approval.

## Dissect primary methods with honest reading scope

Each `method_dissections` row requires `id`, `primary_source:{path,sha256}`, `source_scope` (`full_text`, `abstract`, `excerpt`, `metadata`), `methods_assessed`, `fields`, `worked_example`.

`fields` must cover all of: `research_question`, `design_type`, `estimand`, `sampling`, `measurements`, `comparators`, `analysis`, `assumptions`, `falsification`, `limitations`. For unseen details use `{"status":"not_assessed","reason":"Actual full methods not supplied."}`; keep `methods_assessed:false`, actual scope and `worked_example:{"status":"pending","reason":"No source-bound worked example supplied."}`. Do not fill unseen methods from an abstract or metadata.

Assessing full methods requires the actual supplied full primary source and its protected `confirm_source_scope` record, referenced as `scope_record:{path,sha256}`. A supplied-full-text confirmation does not certify human reading or scientific validation. An assessed field uses:

```json
{
  "status": "analyst_interpretation",
  "value": "A provisional account of this aspect of the method.",
  "boundary": "Textual presence does not establish transferability or validity.",
  "evidence": [{"path": "evidence/supplied-primary.txt", "sha256": "REPLACE_WITH_ACTUAL_SHA256",
    "locator": "L12-L14", "quote": "REPLACE_WITH_SHORT_EXACT_PASSAGE_AT_THESE_LINES"}]
}
```

Use `source_statement` for an attributed statement and `analyst_interpretation` for inference. All method anchors must point to the confirmed primary source. Text locators use actual `L12`/`L12-L14`, PDF anchors include `pdf_page`, and Word anchors use `paragraph 12`. Quotes must occur at those locations and are bounded to 25 words/1000 characters. Entailment remains a scientific review task.

## Worked arithmetic is an illustration

Write an actual independent record, for example `evidence/method-illustration.json`:

```json
{
  "schema_version": "1.0", "problem": "Illustrate subtraction of synthetic scalar values.",
  "input_origin": "synthetic_illustration", "scientific_limit": "Not empirical evidence or method validation.",
  "inputs": {"a": 3, "b": 1},
  "steps": [{"name": "difference", "expression": "a - b", "result": 2, "absolute_tolerance": 0,
    "reason": "Subtract the second toy value from the first."}]
}
```

Reference it with `worked_example:{status:"documented",record:{path,sha256},method_anchor:{path,sha256,locator,quote}}`. The method anchor must identify the actual primary passage. `input_origin:source_example` additionally requires `input_evidence`, keyed by every input name and containing actual primary-source numeric quotes.

The checker independently recomputes bounded scalar `+`, `-`, `*`, `/` and bounded integer powers, allowing at most 20 inputs/20 steps and absolute tolerance 0–0.000001. It permits no calls, attributes, file access or code execution. Complex algorithmic/statistical examples belong in the existing approved experiment runner. `not_applicable` needs an explicit reason and primary evidence; `pending` remains honest until actual material exists.

## FAIR and data availability

Each `data_availability` row must bind an existing `data/datasets.jsonl` ID and exact version, declare `access_mode:open|restricted|embargoed|unavailable`, and address separate `fair.findable`, `fair.accessible`, `fair.interoperable`, `fair.reusable` fields. Each uses the evidence object above or explicit `not_assessed`. Registered research-use/redistribution rights remain authoritative.

A pending deposit uses `deposit:{status:"planned",reason:"No actual repository record verified or upload performed."}`. Metadata observation cannot certify uploaded files, contents, ownership, fitness or publication permission. FAIR does not require unrestricted open access. See the [original FAIR principles](https://doi.org/10.1038/sdata.2016.18) and [GO FAIR guidance](https://www.gofair.foundation/fair-principles).

To inspect an existing actual record, declare `metadata_sources:[{url:"https://ACTUAL_REPOSITORY/records/ACTUAL_ID",purpose:"public_metadata",official_domains:["ACTUAL_REPOSITORY"]}]`. Verify the domain's real identity first; a declared allowlist cannot authenticate its owner.

The controlled fetch uses credential-free GET only: at most 10 URLs per operation, 80 planned URLs, 500000 bytes per response, seven-day source cache and six-hour failed-request cooldown. It rejects unsafe/private URLs, credential parameters, data/full-text binary paths/types and redirects outside declared domains. It never uploads, publishes, acquires datasets or calls a model. Protected receipts retain original response bytes as `.response.txt`, normalized text, HTTP status, actual date/final URL and current provenance/hashes.

After that actual receipt exists, `deposit.status:record_observed` requires `url`, `identifier`, exact `version`, `access_label`, plus `identifier_anchor`, `version_anchor`, `access_anchor`, `license_anchor` bound to the receipt's actual normalized text and verified locator. Each quote must contain its declared value; the license must match the registered manifest, and explicit access category must agree. Expired, forged, conflicting or missing receipts fail. Unknown remains pending.
