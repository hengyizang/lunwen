# Evidence-bound research frontier preparation

`research_frontier` prepares a bounded next-work list from the existing notebook,
native question-scoped reading coverage and actual literature API receipts.
It performs no search, download, extraction, model call or experiment. Use the
existing cloud literature operation queue; the operation is
`{"action":"research_frontier","request_file":"program/research-frontier.json"}`.
The same request is accepted by the nonpaid cloud literature control.

First prepare current `literature_coverage` reports for the actual notebook
questions and native registered source IDs. A source located in the workbench
is not automatically read, semantically verified, or scientifically included.
The frontier consumes those reports without creating another reading history.

## Request

The following IDs and hashes illustrate the format; replace them with current
native records and actual SHA-256 values before execution.

```json
{
  "schema_version": "1.0",
  "kind": "research_frontier",
  "id": "mechanism-followup",
  "questions": [
    {
      "question_id": "Q1",
      "paper_ids": ["source-a", "source-b"],
      "dimensions": ["methods", "results", "appendix"],
      "hypothesis_ids": ["H1"],
      "coverage": {
        "path": "reports/literature-reading/coverage-ACTUAL-QUESTION-AND-SCOPE.json",
        "sha256": "ACTUAL_CURRENT_SHA256"
      }
    }
  ],
  "query_rounds": [
    {
      "id": "round-one",
      "question_id": "Q1",
      "dimension": "results",
      "receipt_ids": ["ACTUAL_NATIVE_LEDGER_RECEIPT_ID"],
      "evidence_ids": ["E1"]
    }
  ],
  "proposed_queries": [
    {
      "question_id": "Q1",
      "dimension": "results",
      "query": "explicit bounded counterevidence query",
      "reason": "Locate a comparable adverse result before choosing a mechanism"
    }
  ],
  "relations": [
    {
      "id": "compare-evidence-and-decision",
      "kind": "contradicts",
      "from": {"question_id": "Q1", "kind": "evidence", "id": "E1"},
      "to": {"question_id": "Q1", "kind": "decision", "id": "D1"},
      "reason": "The cited adverse observation challenges the current decision",
      "applicability": "Only under the source's actual population and protocol"
    }
  ],
  "max_actions": 20
}
```

`questions` selects one to twenty existing `program/research-notebook.json`
questions, each with one to thirty current library IDs. Its question text,
source versions, ordered paper IDs, ordered dimensions and current native
reasoning/progress bindings must match the selected coverage report. Supported
dimensions are `metadata`, `abstract`, `methods`, `results`, `appendix`,
`figures`. Optional hypothesis links must exist in the native
`program/hypothesis-register.json` `hypothesis_id` records.

Up to forty query rounds and forty proposed queries are supported. Proposed
queries may include a `gap_id` from the current deterministic worklist. An
unknown gap, hypothesis, question, source, receipt or evidence ID blocks the
request. Unknown fields, including `execute`, are rejected.

## Coverage and next work

For each selected source and dimension, the report retains the actual native
coverage locations and attributed answers. Missing evidence produces an action
to read the original, locate an unavailable dimension, or acquire lawful full
text for a metadata-only source. Explicit notebook gaps become bounded discovery
tasks. Existing contrary/mixed observations generate comparison tasks before
ordinary reading tasks and remain visible in every factual question summary.

Each action has a stable gap ID, actual question ID, dimension, optional native
hypothesis IDs and the existing source ID/binding to reuse. `max_actions` bounds
the actionable list to one through forty rows; `deferred_action_count` makes
omitted actions visible. The complete question gap inventories remain in the
report. Neither a located heading nor a missing section proves a scientific
gap. Acquisition tasks do not confer access rights or authorize a download.

## Executed-query yield and cached attempts

The report reads the existing `evidence/literature-api-ledger.jsonl`. Successful
receipts are checked by `literature_intelligence._receipt_works`, including raw
response hashes, normalized result hashes and actual result counts. Failed
attempts, their errors and any available bound raw response remain visible.
Missing ledgers mean no observed attempts, not an executed zero-result search.

Canonical papers use the existing DOI/arXiv/title-and-author identity rules.
The raw normalized observation count and canonical count are separate. A
round's new-paper count compares its canonical sources against earlier native
ledger receipts. Reusing a receipt in another round never creates a new paper.
The bounded preparation accepts at most 2,000 normalized observations in the
current native ledger and blocks a larger scope explicitly.

Evidence-dimension counts require existing notebook evidence IDs and a current
native answer for the selected dimension backed by the same original source
version. Mere dimension labels or a search hit never create read evidence.
The count is first-attributed coverage within the selected rounds. Association
of an existing answer with a particular query round is declared and awaits
semantic review; these counts do not measure causal reading progress or confirm
that the query discovered that evidence. `source_matched_dimension_evidence_ids`
means the native answer and notebook observation use the same file/version;
free-text notebook locator overlap remains unverified.

Advice distinguishes bounded reading of new sources, rewording/expanding a
low-yield query, resolving an actual failure, and stopping repeated use of the
same cached round. A proposal displays all matching prior query attempt IDs,
including failures, so the next actor can inspect/reuse them. Query text
matching alone does not prove identical provider filters or cache eligibility;
the existing discovery executor remains responsible for actual cache policy.
Low yield and duplicate receipts never establish scientific saturation,
novelty, exhaustive absence, completeness or a gate decision.

## Notebook relations and independent model context

`complements`, `contradicts` and `supersedes` are optional overlay declarations
between existing evidence/decision IDs. Each requires a reason and applicability
and binds the exact original record hash. Decision endpoints retain links to
their existing source-backed evidence. Originals are neither edited nor removed;
even `supersedes` remains `declared_pending_semantic_review` and has no automatic
truth, priority or approval effect. The native notebook is the authority.

`refresh(project, request_file)` runs only on the authorized cloud runner and
writes `reports/research-frontier/<id>-<content-sha256>.json` with deterministic
output provenance. The envelope includes the current request hash, all native
input/source/receipt hashes, absent optional-input markers, and helper module
hashes. An unchanged refresh returns `changed:false` without rewriting files;
new inputs create a new immutable report. Tampering or missing executor
provenance blocks reuse.

Explicitly bind that one report in the existing `research_toolkit` packet.
`model_context(project, report_relative, role)` recomputes and validates the
current preparation without writing any file. Writers/planners/remediators may
see proposals and declarative relations. Independent critics receive current
coverage locations/status/attributed evidence, contrary IDs and executed-query
facts. Proposed queries, relation reasons, worklists, notebook decision rationale,
native next-action advice and query continuation advice are omitted.

Every role receives a deterministic bounded projection after full validation:
at most forty source/dimension observations, twenty executed-round summaries and
ten source bindings. Question, unknown, contrary, attempt and omitted-row counts
remain explicit. Scientific observation prose and original quotes stay in the
immutable report; existing stage sources load separately. Writer/planner/remediator
action groups each contain at most `max_actions` rows. Text longer than 240
characters is omitted whole, with its length and original record locator retained.
JSON pointers resolve within `report_path` and `report_sha256`; no evidence is
shortened or edited to fit the context. A concise context never means all sources
were read or all history was supplied.

## Validation scope

`tests/test_research_frontier.py` exercises native coverage and append-only
reading progress, actual normalization of supplied synthetic provider responses,
canonical deduplication, failed/cached receipts, source/request/module changes,
immutable reuse, declarative relations and read-only critic isolation. These are
software fixtures intended for the existing cloud CI. They supply no independent
scientific review, saturation judgment or actual topic evidence. No default
model, paid route, budget, G0–G5 approval or G3 execution boundary changes.
