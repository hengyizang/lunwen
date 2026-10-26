# Seven concrete research task scenarios

These entry points reuse current cloud execution, datasets, literature workbench,
screening ledger, figure briefs, author/critic roles and spending authority. No
new model, API key, paid service, autonomous human approval or research stage is
introduced. The same methods are loaded in the existing API and CLI author
cycle through config/research-methods.json. Source documents remain data, not
instructions. All scientific interpretations remain pending their normal review.

## Run one controlled task

Write one operation under program/, then on the authorized cloud runner use:

```sh
python -m scripts.literaturectl request --project my-phd --request-file program/task-operation.json
```

The existing owner cloud `action:literature` accepts the same request with
allow_paid:false. The normal writer can queue these actions in
program/cloud-operations.json at its actual stage. Neither route authorizes
acquisition, analysis or gates. Generated reports are executor-owned.

| action | input | output |
| --- | --- | --- |
| data_row_prepare | dataset_id, optional key_columns | Complete pending row declaration with current original hashes |
| data_row_provenance | request_file, default program/data-row-provenance.json | reports/data-row-provenance/DATASET/rows.json and rows.csv |
| literature_source_trace | request_file, default program/source-trace.json | reports/literature-source-tasks/source_trace/ID/ |
| literature_screening_advice | request_file, default program/screening-advice.json | reports/literature-source-tasks/screening_advice/ID/ |
| literature_search_strategy | request_file, default program/literature-search-strategy.json | reports/literature-search-strategy/ |
| literature_synthesis | request_file, default program/literature-synthesis.json | reports/literature-synthesis/latest.json and index.html |
| diagram_mermaid | request_file, default program/diagram-mermaid.json | reports/diagram-mermaid/ID/diagram.mmd, report.json, index.html |

## 1. Public data and row-level provenance

Use an existing registered, owner-authorized original CSV and data contract.
The controller checks the original hash, exact manifest/registry/dictionary and
current permission before reading it. data_row_prepare returns all row numbers
and row hashes so the writer does not invent them. Copy this declaration into
the request and add actual sources and unresolved issues; do not alter the CSV.

Declaration shape:

```text
schema_version: 1.0
dataset_id
input: {path, sha256}
key_columns: [actual column names]
records: [
  {row_number, row_sha256, status: pending|located|disputed,
   sources: [{url, published_at, collected_at, fields,
              material: null|{kind:dataset_row}|{kind:literature,paper_id,anchor}}],
   issues: [{field, state, reason}]}
]
```

published_at may be an actual ISO date/time or null; collected_at is an actual
timezone-aware collection time or null. Publication time cannot be inferred from
collection/access time. Issue states distinguish unexplained_missing,
not_published, not_accessible, not_applicable, ambiguous and conflict. Every
original row must remain, including repeated keys and contradictory sources.
Unknown values are never changed to zero. Physical CSV line ranges also handle
quoted multiline fields. Sidecars export row/key digests and source metadata,
not raw row values or source quotations. Digests are not anonymization.

located means an actual bound original row or literature passage was located;
it does not verify a source URL or scientific meaning. Fields without a declared
row source are reported explicitly. A changed original/dictionary/permission
or altered report fails validation. Licensed owner-supplied files use the same
manifest and authorization route; access challenges are never bypassed.

## 2. Trace a remembered statement

Source-trace input has schema_version, id, memory_statement, search_leads and
candidates. A lead has query, provider, status:planned|executed and receipt_id
only for an actual executed search. Candidates name registered paper_id,
state:candidate|excluded, reason, evidence, premises, scope and
inference_boundary. Optional cites_candidate_ids retain a secondary citation
chain as leads; they do not establish historical originality. Premises/scope
items use {text,evidence} with original source anchors.

Optional identity_evidence:{receipt_id,study_id} matches actual normalized
metadata, retaining title, publication year, DOI and authors where available.
Metadata matching, original-text location and semantic support have separate
states. No one boolean means verified. A candidate cannot disappear from an
existing trace; keep excluded candidates with a reason. Changed requests archive
the prior report. Current source hashes and actual search receipts are checked
again; absence of earlier literature is never inferred from a bounded search.

## 3. Criterion-level screening advice

Bind screening:{path,sha256} under evidence/systematic/, the current protocol
and exact existing criteria. Input also contains id, criteria:[{id,text}],
study_papers:[{study_id,paper_id}], advice and optional duplicate_leads. Advice
has study_id, stage:title_abstract|full_text, criterion_id,
suggestion:include|exclude|review, reason, missing_information and evidence.

The report preserves every formal study x stage x criterion; omitted suggestions
remain review. A suggestion is never a formal include/exclude decision. Exact
original evidence supports suggestions, and unavailable/partial full text cannot
be treated as a completed full-text assessment. Suspected duplicate reports
remain leads pending their existing study-group review. The tool never edits
the screening ledger, changes criteria or creates named human reviews. Existing
independent screening, adjudication and bias-assessment rules still apply.

## 4. Actual analysis status

Continue using docs/EMPIRICAL-DATA-WORKFLOW.md and the approved experiment
runner. The new task prompts explicitly require the research question,
dictionary, prespecified missingness/outlier rules, estimand, diagnostics,
result template and independent numerical check. A script is proposed until it
has an actual sealed run. Repeated trials, null findings and failures remain.
Only reviewed method variants are native; no generic prompt makes an unsupported
analysis executable or a model explanation numerically verified.

## 5. Source-bound synthesis and a three-level outline

First refresh the existing canonical literature matrix. Synthesis input:

```text
schema_version: 1.0
question: exact matrix question
matrix: {path:reports/literature-matrix/matrix.json, sha256}
judgments: [{id, statement, relation:agreement|conflict|conditional|insufficient,
  axes:[construct|population|data|method|identification|measurement|statistics|protocol|scope],
  supports:[{paper_id,field_id}], contradicts:[{paper_id,field_id}],
  assessment:{design,bias,comparability,uncertainty},
  inference_boundary, missing_evidence:[]}]
outline: [{title,purpose,judgment_ids,sections:[
  {title,purpose,judgment_ids,sections:[{title,purpose,judgment_ids}]}]}]
```

Each assessment is {status:unknown|interpretation,text,cells:[{paper_id,field_id}]}.
Interpretations need actual located evidence; unknown assessments stay unknown.
Conflict retains both sides. Every registered judgment appears in the outline,
all original matrix cells remain available, and unaddressed/unknown cells are
listed. Different source identities do not prove independent studies. Strength
is not determined by citation counts, paper counts or model confidence.
Use this worksheet for related work, a research dossier or protocol; it does
not fulfill the six-paper portfolio with an extra narrative review.

## 6. Editable Mermaid from the existing research diagram

Input schema_version=1.0, id, source:{path,sha256} and story_ref:{path,sha256}.
The source must be a current non-Claude-authored typed research-diagram IR; the
story_ref must be its current figure_story report. Every node and arrow replays
the existing original-method/manuscript/result evidence, topology and phase.

No new causal edge is inferred. Association stays an undirected dotted line;
planned/method/observed labels remain visible on nodes and relations. The
original caption stays in the report and preview. The editable .mmd is a draft
export, not an approved final figure. Existing source/visual/scientific review
and registration remain required. The native SVG/PDF/PNG and other editable
formats remain available. Mermaid syntax follows the official
[flowchart specification](https://mermaid.js.org/syntax/flowchart.html).

Cloud acceptance installs Mermaid 12.2.0 only in a temporary test directory and
uses actual Chromium to parse/render ordinary and injection-shaped labels.
Production export performs no npm installation or network rendering request.

## 7. Bilingual search plans and trial logs

Search-strategy input has schema_version, version, change_reason,
doctoral_question, question, concepts, tiers, platforms, exclusions and trials.
Concepts have id, zh, en, aliases, disciplinary_sense and optional original
evidence. tiers are broad, medium and strict, each with concept_ids and reason;
their concept sets must be nested within the same doctoral question.

ArXiv receives a bounded native Boolean query. Other supported native sources
receive labelled plain-text variants when Boolean semantics are not supported.
WoS/CNKI receive syntax-unverified manual drafts, never a fabricated successful
API execution. Exclusions {term,reason,scope_category} remain unapplied proposals,
limited to explicit population/study/document/language scope. No unfavorable
finding is automatically filtered and the active discovery plan stays unchanged.

Trials bind id, query_id, receipt_id, reason and optional formal screening
binding. Platform totals come only from actual raw provider responses. Returned,
normalized, deduplicated and screened units are identified separately; unknown
totals remain null. Imported exports have import time rather than an invented
platform search time. Input versions and reasons are retained, source/plan
bindings are rechecked, and changed or missing history blocks validation.

## Validation boundary

These are source/integrity and task-organization checks. They do not prove
semantic correctness, historical originality, causal assumptions, complete
literature coverage, scientific completion or journal acceptance. No paid model
test, model routing change or production project mutation is part of this upgrade.
