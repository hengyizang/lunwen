# Literature evidence reading upgrades

The [completion operations](LITERATURE-COMPLETION.md) add explicitly triggered
CPU vector generation and independent reranking, bounded upstream SDK use,
paired complete-text reading plans/execution, cloud Zotero, discovery categories
and actual PDF overlays/annotation copies. Default lexical execution and model
routes remain unchanged. See that document for the current capability boundary.

The [research task scenarios](RESEARCH-TASK-SCENARIOS.md) add row provenance,
remembered-claim tracing, criterion-level screening advice, tiered bilingual
queries, source-bound synthesis outlines and evidence-preserving Mermaid export.
They reuse these same workbench sources, matrix and original-text boundaries.

These native cloud mechanisms extend the existing workbench, reading progress,
source rights, model runtime and budget. They do not install ten competing apps,
require desktop Zotero, add a model, change reasoning effort, spend a new API
allowance or grant G1/G3/G5 approval. Production retains CNY 500 and the owner
target date; this implementation does not mutate production project state.

## Available operations

All execute through the existing cloud literature request or writer queue:

| action | parameters | output |
| --- | --- | --- |
| literature_retrieve | request_file, default program/literature-retrieval.json | reports/literature-retrieval/latest.json and index.html |
| literature_reading_index | paper_id; optional locate_pdf boolean | reports/literature-reading/ID/index.json and index.html |
| literature_coverage | request_file, default program/literature-coverage.json | question-and-scope-bound coverage JSON/HTML under reports/literature-reading |
| literature_matrix | request_file, default program/literature-extraction.json | reports/literature-matrix/matrix.json, matrix.csv, index.html, manifest.json |
| literature_benchmark | request_file, default program/literature-benchmark.json | reports/literature-benchmark/latest.json |

These operations make zero model/embedding requests. The owner nonpaid
`action:literature` route accepts one bounded operation, with allow_paid:false.
The normal stage writer can request the same operations; generated reports
are executor-owned and cannot be rewritten by that model. New request files
are data, not execution instructions, and never acquire access rights.

Cloud CLI examples:

```sh
python -m scripts.literaturectl retrieve --project my-phd --request-file program/literature-retrieval.json
python -m scripts.literaturectl reading-index --project my-phd --paper-id sourceA --locate-pdf
python -m scripts.literaturectl coverage --project my-phd --request-file program/literature-coverage.json
python -m scripts.literaturectl matrix --project my-phd --request-file program/literature-extraction.json
python -m scripts.literaturectl benchmark --project my-phd --request-file program/literature-benchmark.json
```

Use actual library IDs and evidence, not the illustrative IDs below. Build the
existing authorized workbench before these operations. Original-source removal,
revoked permissions, changed bytes or stale native reader receipts block reuse.

## Retrieval and original evidence

Example request shape, requiring real registered sourceA/sourceB:

```json
{
  "schema_version": "1.0",
  "question": "Does the protocol test cross-device generalization?",
  "paper_ids": ["sourceA", "sourceB"],
  "query_expansions": [
    {"query": "held-out devices unseen hardware transfer", "reason": "Alternative terms for the same protocol question"}
  ],
  "stances": {"sourceB": "contradicts"},
  "limit": 8
}
```

The coordinator derives allowed ranges from the current original-source
workbench, excluding Chinese translations and generated headings. The default
BM25 remains available; explicit alternate queries use RRF k=60. Each query
and source reports matches, returned blocks and omissions. Contrary/mixed
sources retain at least one block; this is a prompt to inspect their complete
relevant evidence, not proof that one block represents all counterevidence.
The original doctorial scope never changes from query expansion or ranking.

An optional dense_cache:{path,sha256} accepts already prepared vectors. Cache
schema binds schema_version=1.0, model:{id,revision}, dimension, exact
query:{text,sha256,vector}, sources:[{path,sha256,ranges?}] and complete
blocks:[{path,sha256,start_line,end_line,excerpt_sha256,vector}]. The input
digest, finite dimensions and complete block/source bindings must match.
This retrieval consumer performs CPU cosine similarity only; explicit
literature_semantic can generate these vectors on the cloud using fixed models.
Neither path enables an unmetered API. Missing or incorrect vectors are not
silently reported as semantic retrieval. Model identity and embedding quality
remain unverified inputs until actually evaluated.

Native scripts.paper_qa accepts an optional --retrieval-plan-file with the
same exact question/source-bound low-level retrieval specification. Its paid
--execute still uses the existing centrally metered reader-qa route. Every
answer statement now needs its own citation indices, and answer must consist
exactly of those mapped statements. Verbatim citation matching does not prove
that the cited text entails a statement. No automatic paid retry is added.

## Sentence navigation and coverage

Sentence IDs bind source version, original extracted quote, physical page and
line/character range. Index HTML provides sentence permalinks, highlights the
selected original quote and links to the source page. Explicit locate_pdf=true
uses existing cloud Poppler word positions; only a unique normalized word
sequence receives coordinates. PDF PageLabels metadata, when present, supplies
printed labels separately from physical page indices. Ambiguity, extraction
failure and missing labels remain explicit. Coordinates are navigation aids;
they do not establish that the sentence supports a research conclusion.

Coverage request has no extra schema_version field:

```json
{
  "question": "Does the tuning procedure exclude test devices?",
  "paper_ids": ["sourceA"],
  "dimensions": ["metadata", "abstract", "methods", "results", "appendix", "figures"]
}
```

The existing protected program/literature-progress.json holds attributed
reading answers. Coverage reports summarize those current records and exact
source locations; they do not create another read history or certify a human
read. Section detection only locates candidates. An answer attached to a
different question/step/version is not reusable evidence for the current step.
Every missing dimension receives a concrete reading or acquisition task.

## Structured comparison and numerical extraction

The program/literature-extraction.json shape:

```json
{
  "schema_version": "1.0",
  "question": "Which measurements use comparable populations and protocols?",
  "paper_ids": ["sourceA", "sourceB"],
  "fields": [
    {"id": "method", "type": "text", "card_field": "methods"},
    {"id": "accuracy", "type": "number", "quantity": "accuracy", "unit": "proportion"}
  ],
  "cells": []
}
```

Empty cells remain unknown. Text can reuse all current card entries, not just
the most favorable one. To populate a number, supply paper_id, field_id, text,
kind:author_claim, exact evidence anchors, numeric:{raw_value,raw_unit,quantity,
comparator?,uncertainty?}, source_context:{kind,population,conditions}. Use
actual original tokens; the displayed example does not assert a real result.
For table context also supply table_label,row_header,column_header,footnotes.
Only actual source-bound PDF assets can supply optional visual_asset
{path,sha256,pdf_page,bbox}; locating that region does not approve cell alignment.

Decimal transformations use the small reviewed unit conversion allowlist, not
arbitrary expressions. Original signs, inequalities, values, units and
intervals are retained. p<0.001 remains censored; p=0 remains a reported value
requiring a precision check. Unknown is never substituted with zero. Every
cell keeps semantic_verification=false and eligible_for_quantitative_synthesis=false.
The existing actual study protocol, independent checks and human authority are
still needed before using extracted literature data in Meta-analysis.

## Quality and cost evaluation

program/literature-benchmark.json requires schema_version=1.0,
annotation:{kind:synthetic_fixture|human_annotation,by}, and cases:[{id,request,
relevant:[{paper_id,path,sha256,start_line,end_line,quote,pdf_page?}]}]. Each
request uses the retrieval shape above. Empty relevant means an explicitly
labelled missing-evidence case, not exhaustive absence from the literature.

The evaluator compares base BM25 and candidate fusion on the same original
corpus, recording known-anchor recall and elapsed retrieval time. Optional
qa_report:{path,sha256} plus expected_abstain checks a recorded answer's exact
question, source versions, original ranges and quotations. Semantic support
remains not measured. numeric_cases may select the current canonical matrix
cell using id,matrix:{path,sha256},paper_id,field_id,expected_value,expected_unit;
the evaluator revalidates the full matrix before comparing decimals and units.

Optional cost_scope uses existing cost_run_ids and additional_cost_receipts.
It reads actual central usage/debit records, including selected failures and
cache information. Estimated, unreconciled or absent costs stay incomplete.
Total scope requires the existing independent owner reconciliation mechanism;
the benchmark never manufactures one. Precomputed index costs remain explicitly
unconfirmed, and no automated route promotion or scientific equivalence claim
is made. Run a real source-annotated evaluation before selecting a new retrieval
backend or paid embedding service. CI synthetic tests validate software only.

## Reviewed sources

Pinned references are recorded in integrations/upstreams.lock.json. Mechanisms
were independently expressed; no upstream runtime or application code was copied.
PaperQA2 supplied question-level retrieval ideas; paperai field extraction;
llm-for-zotero coverage; Beaver sentence navigation; OpenPaper cell evidence,
original-PDF numbers and evaluation; daily-paper-reader layered discovery and
fusion. PaperPilot/PaperLens are discovery references only. Their citation
labels, DOI-format checks, abstract-only novelty analyses and star counts never
replace this project's primary-source, scientific or budget checks.
