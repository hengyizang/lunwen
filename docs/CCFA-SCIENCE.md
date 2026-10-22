# CCFA scientific extensions

The 17-family adapter uses the existing model orchestrator, literature workbench,
scientific reasoning contracts, experiment runner and external reviewer rounds.
`scripts/ccfa_science.py` adds five bounded deterministic report operations. It
does not create another runner, grant API budgets, change model selection, start
experiments, impersonate external reviewers or approve G0–G5.

All report mutation runs on the cloud executor. No model or network request is
made by this module. The existing authorized OpenAI writer supplies semantic
inputs; Claude can critique them through existing protected read-only audits.
Quoted third-party instructions remain source data.

## Common call contract

Call `execute(project, operation, request)` with an operation in `continuity`,
`lineage`, `novelty_watch`, `exemplar`, `internal_review`. The strict request is:

```json
{
  "schema_version": "1.0",
  "id": "P01-method",
  "source": "program/ccfa-inputs/P01-method.json",
  "expected_source_sha256": "CURRENT_INPUT_SHA256",
  "expected_previous_sha256": null
}
```

The bounded input must have current non-Claude writer provenance and this shape:

```json
{
  "schema_version": "1.0",
  "operation": "continuity",
  "id": "P01-method",
  "doctoral_question": "The current exact overarching doctoral question",
  "paper_ids": ["P01"],
  "data": {}
}
```

The placeholders above describe the API, not usable research input. Empty or
placeholder scientific text is rejected. Input JSON rejects duplicate keys and
nonfinite numbers. Named output is fixed at
`reports/ccfa-science/<operation>/<id>.json`. Updating requires the exact current
report hash; earlier reports are retained under content-hash history. Repeated
unchanged requests reuse the verified-current report rather than generating a
new review/history entry. Changed dependencies, implementation or provenance
invalidate reuse. `current(project, operation, id)` replays all source hashes and
current origins; it does not certify semantic correctness.

Every operation binds the existing `program/core-thesis.json` when present.
Changing its nonempty doctoral question requires the existing human G1/G2
route; an input cannot overwrite that requirement. P01–P06 scopes stay explicit.
These reports are supporting artifacts, never authoritative replacements for
the project stage, canonical hypotheses, plan, claim matrix or reviewer ledger.

All ordinary file bindings are `{path, sha256}`. Evidence anchors reuse the
repository's `research_candidates.anchor_errors` contract:
`{path, sha256, locator, excerpt}` with an exact line locator such as `L4-L6`, or
`pdf_page` for a real PDF. Excerpts have the existing 25-word bound. Paths cannot
escape the project or traverse secrets, credentials, raw datasets, private or
control state. The sole raw-response exception verifies an exact existing
native literature receipt and never loads it as executable instructions.

## Continuity

`data` requires `goal_revision`, `objective`, `constraints[]`, `acceptance[]`,
`authoritative_inputs[]`, `route: {id, summary}`, `next_action`, `mode`
(`normal`, `focused`, `reconciling`), `open_items[]`, `artifacts[]`.

Each artifact has `{file: {path, sha256}, status, checks?}`. Status is `proposed`,
`executed` or `verified`. Verification requires a current native deterministic
passed report that names the artifact's exact hash, and all of that report's
declared dependencies are replayed. A model-written assertion cannot verify an
artifact. A changed artifact can be retained as executed pending a fresh check.
Previously verified artifacts cannot silently disappear.

An actual objective/acceptance change needs an increased revision and
`transition: {basis, reason, evidence[]}`. Goal changes allow `user_instruction`
or `intent_correction`; a route change also permits `new_evidence`,
`verified_failure` or `comparison`. Returning from focused/reconciling work to
normal requires `recovery_check`. Old unchanged transition rows cannot justify
a new change. These labels record a rationale; they never grant authority,
change human approvals or establish actual model recovery.

## Idea lineage

`data.candidates[]` has stable IDs, ordered `parents[]`, one `operator`
(`seed`, `refine`, `combine`, `transfer`, `invert`, `instrument`), `premise`,
`new_inference`, `inference_boundary`, `mechanism_change`, `component_necessity`,
`discriminator`, `conditions[]`, `status`, and located `evidence[]`.
Seeds have no parent; combine needs two distinct existing parents. A different
mechanism, discriminator or condition needs a new child ID. Prior branches are
retained, including `rejected` and `refuted` branches. Rejection does not justify
erasing its evidence or retrying the same unchanged configuration.

Statuses distinguish `exploratory`, `proposed`, `measured`, `rejected`, `refuted`.
A measured row requires `measurement: {receipt, run_id, configuration}`. It must
match exactly one existing successful `experiments/registry.jsonl` attempt, its
immutable run receipt, current approved plan hash and current output hashes.
`configuration` is a declared approved run input JSON with the same
`candidate_id`; this uses the existing plan schema rather than adding arbitrary
execution fields. A model cannot turn a proposed run into a measurement.

An optional `selected_candidate` plus `selection_reason` records a provisional
scientific choice. The output lists actual measured candidates separately.
It deliberately does not invent a best measured candidate across incomparable
metrics, protocols or budgets: that judgment requires the existing frozen
experiment/comparability audit and independent scientific review. Neither
lineage completeness nor a keyword combination establishes novelty.

## Claim-linked novelty watch

`data` contains `window: {from,to}` as past timezone-aware instants,
`claim_source` bound to the existing `program/novelty-claim-matrix.json`,
`coverage_receipts[]`, and `findings[]`. Each coverage item is
`{ledger: {path,sha256}, receipt_id}` against the actual
`evidence/literature-api-ledger.jsonl`. The named successful live-search receipt
must lie within the scan window. Its normalized and original response hashes
are verified; invented/unexecuted coverage is rejected. Actual query conditions
are retained, including limitations. The scan does not infer exhaustive
coverage or novelty from an empty response.

Each finding needs stable `id`, existing `claim_id`, current workbench `paper_id`,
`axes[]` (problem/mechanism/evidence/benchmark/dataset/claim/positioning),
`signal` (`RELAX`, `RESEARCH`, `FOLLOW-UP`), `implication`, `boundary`,
`claim_evidence[]` and `source_evidence[]`. Both sides must quote their exact
source versions; a claim anchor cannot quote a different matrix row. Deltas
distinguish new, changed, unchanged and not reobserved findings. Source scope is
retained; metadata does not become full-text analysis. Signals propose work,
not automatic paid scans, redesign, rewriting or recurring monitoring.

## Full-paper writing exemplars

`data` requires workbench `paper_id`, native `scope_record` for the supplied
full text, `article_type`, `moves`, `do_not_copy[]`, `selection_conditions[]` and
optional `venue: {name,year,evidence[]}`. The existing `source_scope.verify`
must confirm the exact supplied full source. Abstracts, metadata and empty
extraction cannot stand in for a full-paper card.

`moves` has seven required families: `story`, `abstract`, `introduction`,
`method`, `evidence`, `citations`, `reusable_techniques`. Each has one or more
`{pattern,purpose,transfer_conditions,evidence[]}` rows located in the original
source or its controlled native reader. Output patterns are interpretations,
not transferable scientific claims or permission to copy distinctive wording.
They are selected by declared study/venue conditions; no global/default style
library is silently changed. Supplied full text does not certify human reading.

## Internal review continuity

`data` requires exact `historical` and `current` manuscript bindings, `scope`,
`criteria[]`, separate `readiness_criteria[]`, `issues[]`, and `readiness[]`.
Criteria rows are `{id,criterion,scope}` and remain frozen for this report ID.
An actual new standard requires a separate labeled, noncomparable review ID.
This operation never creates an external decision/reviewer round; actual
reviewer comments continue through `reviewer_rounds.py`.

Issue rows carry `id`, `first_seen_version`, `status` (`unresolved`,
`partially_resolved`, `resolved`, `not_applicable`), `origin` (`inherited`,
`revision_regression`, `previously_undetected`, `newly_revealed_by_evidence`),
`applies_to` (`historical`, `current`, `both`), frozen `dimensions[]`, `severity`
(`blocker`, `major`, `minor`), `finding`, `evidence[]`, and `resolution`.
Finding IDs/definitions/first-seen versions cannot be silently changed or
deleted. Latent previously-undetected problems apply to both versions;
revision regressions apply to current. Every applicable manuscript version
needs located evidence; changed source bytes make old evidence stale.

Readiness rows are `{criterion_id,status,rationale,evidence[]}` for every
readiness criterion, with statuses `satisfied`, `needs_revision`, `blocked`,
`not_assessed`. The output separates categorical relative progress from current
readiness (`blocked`, `revise`, `not_assessed`, `ready_for_human_review`). It
does not use an overall score, admission probability, acceptance score or a
CCF tier as a substitute for the doctoral/JCR scientific standards. Semantic
resolution and scientific readiness still need independent/human review.

## Validation

`tests/test_ccfa_science.py` covers real native source/provenance replay,
versioned goal/routing changes, meaningful verification receipts, branch
lineage, native synthetic experiment receipts, claim-specific live-provider
fixtures, source mutation, full-text scope, exemplar coverage and frozen
review issue lifecycle. The tests run only through existing cloud CI. Their
synthetic mechanisms/results are test data, never real research evidence.
