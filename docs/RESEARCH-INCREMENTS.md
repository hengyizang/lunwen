# Eight cloud research increments

These additions extend the scientific workflow. They do not select models,
change reasoning effort, grant paid access, rent compute, train models, approve
G0–G5 or certify doctoral/Q1 quality. Claude remains a read-only planner/reviewer;
persistent science uses the existing OpenAI roles. Only the existing initial
writer and remediation passes are used.

## Entry points

New projects have program/research-increments.json. For an existing project,
request research_increments in program/cloud-operations.json to initialize and
refresh it. Top-level schema_version is 1.0; all eight arrays are required:
arguments, lineage, gaps, ingestion, lessons, dependencies, voices, editing.
Empty arrays honestly mean material has not been supplied.
required_at_submission must contain arguments and lineage; other groups may
also be required. Every row has a unique safe id within its group.

Run builders only in the authorized cloud executor:

    python -m scripts.research_improvementctl research-increments --project PROJECT
    python -m scripts.research_improvementctl increments-inventory --project PROJECT --paper P01
    python -m scripts.research_improvementctl increments-freeze --project PROJECT --kind lesson --record-id RULE_V1
    python -m scripts.research_improvementctl evidence-context --project PROJECT --task-id results

Equivalent bounded cloud operations are research_increments,
increments_inventory (paper_id, writing stage) and increments_freeze
(kind: argument/lesson, record_id). Context operations accept task_id.
There are no arbitrary shell commands or model calls in these builders.
reports/research-increments/** and existing protected state are executor-owned.
The writer cannot fabricate audits, freezes, adoption, receipts or history.

Automatic author cycles freeze existing argument plans before writing and
refresh audits after initial writing and remediation. Plans created together
with a draft become pre-write plans only on a subsequent author cycle.
A manual argument freeze is labelled review_checkpoint, never retroactively
pre-write. G5 and submission packaging require full current paragraph coverage
and typed lineage for the active paper, with a current protected audit.
Other configured groups are validated; stale dependencies block readiness.
Empty material never constitutes scientific completion.

## A. Paragraph plans and reverse outlines

increments_inventory returns actual source units: Word paragraphs including
tables, or TeX paragraph blocks in include traversal order. Units carry
unit_id, sha256, path, location, order, occurrence, text. These are source
coordinates, not guessed PDF pages. Inline/dynamic TeX includes, includeonly and
cycles need an explicitly supported export.

An arguments row has paper_id, paragraphs, precedence. Each paragraph has
paragraph_id, section, function, purpose, claim_ids, inference_boundary,
transition, units and optional evidence. units contains exact current unit_id/
text sha256 pairs from the inventory. All current units must be covered once;
one planned paragraph must be contiguous. Use function non_argument plus
exclusion_reason for headings/layout; nothing is silently dropped.

Functions: context, gap, question, method, result, interpretation, limitation,
transition, non_argument. Scientific functions link IDs in the existing
papers/Pxx/reviews/paper-facts.json. Gap/result/interpretation need located
evidence. Precedence entries {before, after} name actual paragraph IDs.
The audit produces a reverse outline and catches duplicates, missing units,
changed text, reversed dependencies and replacement of the frozen plan.
Bindings may be refreshed after edits; conceptual fields require another
pre-write freeze. Historical plans remain. Coverage does not establish validity.

## B. Typed evidence lineage

A lineage row has paper_id, nodes, fact_links. Nodes have id, kind, statement,
boundary, research_state, read_scope, evidence, parents. Kinds:
primary_finding, review_report, review_interpretation, project_inference,
project_observation. Secondary reports/interpretations/inferences also need
attribution_wording. A review without a primary parent must explicitly retain
primary_access: not_obtained. It must not be relabelled an original finding.
Inferences and interpretations cannot become executed observations.

States: hypothesis, planned, exploratory, confirmatory, failed, stopped, unknown.
Supplied scopes: metadata, abstract, excerpt, full_text. Metadata establishes
identity only. Unseen mechanisms/procedures/tables/figures require actual full
text and a current protected scope record. Such records never attest that a
human read the text or verified its scientific meaning.
Full-text nodes use scope_record: {path, sha256} from confirm_source_scope.

An evidence anchor is {path, sha256, kind: source_lines, quote, start_line,
end_line}, or {path, sha256, kind: pdf_page, quote, page} for an actual one-based
PDF page. The exact quote must occur once in that slice. No control record,
own report or increment specification can ground science.

fact_links entries {fact_id, node_id} must exactly cover every existing paper
fact ID. Observations need attempt_id, the actual matching succeeded registry/
receipt, integrity-checked outputs and current plan; evidence must come from
those outputs. Confirmatory observations additionally require the existing
current preregistered experiment evidence audit. Exit success alone does not
change exploratory analysis into confirmation.

## C. Scoped Gap cards

Each Gap links actual hypothesis_id, novelty_claim_id and closest_work_ids in
the existing registers/audits. It records types (knowledge, conceptual,
theoretical, empirical, methodological, population, practical, application,
interdisciplinary, temporal), status (candidate/unknown/refuted), scope
(supplied_materials/executed_queries), question, importance, precise_difference,
falsification_test, feasibility, failure_condition, missing_evidence,
attribution (author_acknowledged/reader_inferred), evidence, counterevidence,
counter_search_ids.

Executed queries must resolve to successful literature provider receipts whose
raw and normalized results still match. Coverage is returned results only,
never all work in the field. Refuted Gaps need counterevidence; a candidate with
counterevidence needs counterevidence_resolution. Mechanism/method/experiment
gaps require source_scope: full_text and scope_record. No status grants novelty;
existing scientific review and G1 requirements remain.

## D. Literature ingestion receipts

Each row has work_id, identifiers (doi/arxiv), title, explicit version,
source_url, optional related_work_ids, attachment, rights_manifest, scope_record.
Attachment and rights manifest are exact {path, sha256} bindings. Actual PDFs
require the existing owner-approved acquisition manifest and matching bytes/
size. Successful download is insufficient.

The builder parses the PDF, records encryption/page limits, text/image-only
status, and checks expected title plus identifier on the first two pages.
A match remains identity_match_candidate. Image-only files need OCR; mismatches
remain pending. Supplied full-text confirmation is distinct from reading and
semantic support. Same identity/version with different bytes is a conflict.
Duplicate identity and exact-content reuse are recorded without replacement.
Metadata-only receipts work without attachments or credentials.

This release adds receipts around existing authorized cloud acquisition.
It does not activate Zotero desktop automation, writes to a user's Zotero
library, a new scraping service or OCR/model billing. Optional transports
need later credentials, authorization and validation.

## E. Failure lessons and safe checker adoption

Each lesson has located lesson, failure, root_cause, proposed_check, limitations,
rollback_reason, baseline, rule, benchmark, optional targets (bound text).
Baseline/rule are literal checkers: {op: contains_any|contains_all|missing_all,
terms: [bounded strings]}. No arbitrary regex, executable code, model training
or automatic policy rewrite is allowed.

Benchmark is {path, sha256} pointing to JSON with cases. Each case has id,
group_id, split (development/validation/holdout), bound source, boolean
expected_flag and ground-truth rationale. Each split needs positive/negative
cases. Content and independence groups cannot cross splits, including renamed
files. Candidate, baseline, benchmark, actual case bytes and evaluator are frozen
before evaluation. Frozen IDs cannot be overwritten; revisions need new IDs.
This is a declared fixture split, not proof that a model never saw the material
or an estimate of real-world scientific quality.

Paired outcomes retain each case, baseline/candidate errors and regressions.
Any newly wrong case rejects the proposal; both validation and holdout must
strictly improve. Rejections and frozen versions remain in protected history.
Eligibility permits owner review only. Adoption/rollback uses the existing
authenticated cloud human controls: operation confirm_research_increment,
kind: lesson, exact record_id, decision: adopt_rule|rollback_rule, reviewed
dossier SHA and a substantive note. Adopted checkers are advisory only and
cannot approve gates. Changed specifications, cases or implementations
invalidate authorization.

## F. Dependencies and reuse

Each dependency row has nodes with id, kind (claim, experiment, result, figure,
text, term, shared_asset, failure), meaning, paper_ids, bound source, depends_on.
Results/failures additionally name a real registry attempt_id; results must
match exact integrity-checked outputs. Missing/changed files become stale;
staleness propagates through the acyclic graph.

Cross-paper nodes need reuse_disclosure and independence_status:
not_assessed/shared_evidence. Shared assets do not certify paper independence.
This extends current manuscript/experiment files without introducing a second
editor or book-management platform.

## G. Minimum edits and scoped author voice

Each voice has bound readable text sample, language, genre, owner and
authorized_use: style_reference_only. The owner authorizes its exact scope/
bytes/implementation through confirm_research_increment, kind: voice,
decision: authorize_sample. A name in model-authored JSON is not authorization
or proof of human authorship. A human dossier records no decision by itself.

Each editing row has paper_id, purpose (clarity/language/structure/
scientific_correction), language, genre, issue_ids, bound evidence, optional
voice_id. Voice must match language and genre. Existing writer prompts receive
a labelled bounded excerpt; embedded instructions are untrusted. Samples never
supply research evidence.

Clarity/language uses minimal edits; structure uses local edits; scientific
correction uses substantive edits and requires bound evidence. Repeated optional
style work with the same issue/evidence fingerprint receives a stop recommendation
at the next writer boundary. Reviewer corrections and scientific blockers remain
mandatory. H01–H26, AD01–AD08, revision integrity, numbers, citations, terms,
uncertainty and disclosure remain protected. No detector-score target, authorship
claim or fixed extra paid pass is introduced.

## H. Context reuse and concise handoffs

Context stages may define tasks keyed by safe ID and active_task. A task has
question, target (paper/chapter), items and optional dependencies. Selections
augment stage constraints, never remove mandatory contracts or current contrary/
mixed notebook evidence. Hashes bind task, chapter, plan, implementation, slices
and dependencies. Declared increment sources are also hashed even outside the
selected chapter slice. A compact protected context-summary avoids duplicating
the full manuscript in the packet. Per-task reports identify changed/removed inputs;
no model-cache hit is claimed. Independent initial/final reviews remain fresh.

reports/research-increments/handoff.json contains stage/gate/status, actual
approved gates, registry success/failure counts, blockers, persisted spend,
pending reservations and remaining authorized budget. Unreconciled reservations
remain charged; overage stays negative. Missing authorization is explicit.
Estimates are not invoices. No progress percentage, ETA or scientific completion
is invented.
