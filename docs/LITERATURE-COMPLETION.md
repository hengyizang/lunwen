# Completing the literature-reading mechanisms

These operations extend the existing cloud workbench, not ten separately hosted
apps. Use the same sources, author/critic roles, cumulative CNY 500 authorization,
provenance and human gates. No local project execution or default route change.

## Operations

All use `python -m scripts.literaturectl request --project SLUG --request-file
program/operation.json` on the cloud runner, or the existing writer operation
queue. Each operation is one `{action,request_file}` object. Nonpaid owner
literature jobs reject `execute:true`; an authorized writer cycle may explicitly
execute a metered reading comparison/SDK answer. A boolean in a specification
never supplies budget authority.

| action | default request | purpose |
| --- | --- | --- |
| literature_semantic | program/literature-semantic.json | Actual pinned CPU embeddings and optional cross-encoder ranking |
| literature_pdf | program/literature-pdf.json | Original page overlays, annotated PDF copy and optional OCR aid |
| literature_zotero | program/literature-zotero.json | Read-only cloud Web API or hash-bound JSON export import |
| literature_zotero_register | explicit request_file and item_key, optional paper_id | Add a selected current imported record to the same searchable metadata library |
| literature_roles | program/literature-roles.json | Overlapping core/adjacent/counterevidence discovery categories |
| literature_comparison | program/literature-comparison.json | Same-corpus retrieval versus complete-text model comparison |
| literature_paperqa | program/literature-paperqa.json | Bounded upstream SDK vector-store bridge and centrally metered answer |

## Actual semantic retrieval and independent reranking

Example semantic specification:

```json
{"schema_version":"1.0","retrieval":{"schema_version":"1.0","question":"Which assumptions make the comparison fair?","paper_ids":["actual-source-id"],"limit":8},"rerank":true}
```

The cloud worker explicitly installs the existing fixed CPU extra and verifies
the ONNX/tokenizer assets pinned in integrations/literature-semantic.lock.json.
Embedding is multilingual MiniLM; the independent MS MARCO cross encoder is
English-oriented. Token windows are covered explicitly rather than silently
truncated. Scores do not prove semantic support, Chinese reranker quality or
scientific importance. Default lexical retrieval remains available.
The SDK bridge similarly provisions only its exact pinned package when an
explicit SDK task needs it. Missing Poppler/OCR tools and requested language data
are installed for the explicit PDF operation; ordinary searches do not install
these extras. The production workflows forward an optional ZOTERO_API_KEY Secret
to the cloud worker, never to model prompts or experiment containers.

Indexes bind every original block, source scope, model revision and code hash.
Unchanged corpus vectors, query vectors and complete results are reused. Changed
bytes, source rights or model identity invalidate reuse. Generated dense and
rerank receipts can feed the existing retrieval/Q&A path; raw originals and
selected contrary sources remain authoritative. CPU model execution makes no
paid inference API request; CI/runner time, storage and transfer are separate
resources and are not asserted to cost zero.

## PDF overlays and persistent annotations

```json
{"schema_version":"1.0","id":"protocol-evidence","paper_id":"actual-source-id","pages":[2,3],"annotate_pdf":true,"ocr":{"enabled":false,"language":"eng"}}
```

Optional sentence_ids narrows highlighting to exact current indexed sentences.
The HTML displays actual rendered PDF pages with SVG rectangle overlays and
links among original sentences, page locations and current table cells. The
downloaded annotated.pdf has actual native PDF Highlight annotations in a copy;
the original file is unchanged. Rotation normalization is performed only on a
temporary copy before positioning. Ambiguous repeated sentences are not guessed.
Table region locations still require visual review of row/column alignment.

Explicit OCR uses the cloud's Tesseract and preserves separate TSV/recognized
words alongside the original page. `eng`, `chi_sim` and `eng+chi_sim` are supported
when their installed language data exist. Missing text, unavailable language data
and recognition failure remain visible. OCR output is a reading aid; it does not
replace original evidence or enter native full-text support automatically.
Generated views/copies inherit source rights and are for authorized personal use.

The existing literature_matrix operation also exports matrix.md alongside JSON,
CSV and HTML, with cell anchors, original citations, unknowns and numeric context.

## Cloud Zotero bridge

```json
{"schema_version":"1.0","id":"my-library","mode":"web","library_type":"users","library_id":12345,"authenticated":true,"max_items":500}
```

Use an actual library ID. Public group/user reads do not require a key. For a
private library the owner supplies a dedicated read-only ZOTERO_API_KEY through
Actions Secrets; do not put it in requests, URLs or the repository. No key is
needed for `mode:export`, which uses `export:{path,sha256}` for an actual UTF-8
Zotero JSON export under evidence/ or literature/.

This bridge requests API v3 over HTTPS, follows explicit bounded pagination,
checks actual Total-Results and a consistent library version, and handles changed
and deleted item keys on subsequent reads. An inconsistent page version blocks
committing a partial index. No server writes, desktop application, paid model,
attachment download or access bypass occurs. Notes/annotation bodies are omitted
even from stored response projections. Original API response hashes are retained;
sanitized projections are not advertised as verbatim original response bytes.

Bibliography import is not full-text acquisition or permission. The existing
literature_zotero_register action takes the actual import request_file and
item_key, validates its receipt, then registers a versioned metadata-only source
in the shared workbench so library search can find it. It never approves a
scientific inclusion, downloads an attachment or maps a paper to the thesis.
The existing
discovery/acquisition/registration process must verify each selected actual
source before it can be cited or read. A missing key, actual user library or
private-library approval cannot be simulated by a passing fixture.

## Discovery classification

```json
{"schema_version":"1.0","leads":{"path":"program/topic-leads.json","sha256":"ACTUAL_CURRENT_HASH"}}
```

Current native API receipts and matching search-log records map direct,
adjacent and counterevidence query families to provisional categories. One paper
can occupy all three; unknown families stay unclassified. No paper is dropped,
and this classification makes no scientific inclusion/exclusion or novelty
decision. Full-text comparison determines actual relevance to the same thesis.

## Reading quality and total-cost comparison

Use literature_comparison with `schema_version,id,annotation,cases`. Each case
has `id,request,relevant,expected_abstain` and optional calibration/holdout
partition. `request` is the same registered-original retrieval specification;
`relevant` contains actual paper/line/page/quote anchors, optionally marked
contrary. Annotation is attributed as synthetic_fixture, primary_source_fixture
or human_annotation. Never label generated checks as independent human review.

The default prepares both contexts and a source-bound plan without model calls.
The full-text arm requires complete native page ranges or the existing protected
original-text scope. Oversize full text blocks explicitly: it is never silently
truncated or renamed a complete read. Both arms use the same question, corpus,
instruction, current reader-qa model and output ceiling. Explicit execute=true
uses only the existing central model runtime, exact-request cache and budget.
Identical contexts share one request. Failed responses, rejections, unknown
charges and source changes stop further work and remain recorded.

Outputs include actual token/cache/latency/charge receipts, anchor coverage,
contrary coverage, citation checks and a blinded independent-review proposal.
The existing protected review-packets mechanism owns actual reviewer inputs;
no new route can invent a human assessment or approve itself. Missing costs and
semantic judgments remain unknown. Source-disjoint calibration/holdout and
actual independent ratings are needed before any quality-equivalence claim.

## Validation scope

The completion workflow exercises real CPU model execution on the openly licensed
JOSS seaborn paper, exact source location probes, index/result reuse, complete
paired-plan construction and original-PDF overlays/annotations. Complex generated
PDF tests include multiple columns, repeated sentences, rotation and scanned
pages with actual OCR. These establish functioning mechanisms and report known
location metrics. No paid model answer comparison or independent human scientific
review is implied by this credential-free acceptance. Actual research-topic
quality, complex-source extraction accuracy and preferred model/backend remain
empirical questions for the authorized study and review process.
