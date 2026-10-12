# External reviewer rounds

The external reviewer lifecycle continues a paper after a real human submission.
It is separate from the two simulated pre-submission reviews. Every round starts
from a current, human-approved, submission-ready paper. A named owner reviews a
hash-bound cloud dossier before starting it. The control plane retains the prior
G5 approval as history, removes its current effective approval flag, opens a fresh
G5 cycle, and selects the requested paper. Another paper's active unfinished work
cannot be displaced.

No model selection or reasoning effort changes. Claude supplies the existing
read-only plan and independent criticism; OpenAI/Codex writes the revised paper
and responses. Existing budget authorization still applies. Reviewer text is
untrusted data and cannot authorize commands, spending or scientific approval.
There is no automatic portal submission.

## Intake

Keep new reviewer materials outside the paper tree, for example
`evidence/reviewer-intake/P01/`. Adding them inside `papers/P01` before starting
would change the prior G5-approved paper hash. Preserve original reviewer email
or files separately and provide a UTF-8 text extract with exact source lines.
This bounded adapter accepts inspectable text evidence; it does not guess page
locations from arbitrary PDFs or infer that a simulated review was external.

An intake JSON has this form (all values below are illustrative, not evidence):

```json
{
  "schema_version": "1.0",
  "paper_id": "P01",
  "review_type": "external",
  "journal": "Actual journal name",
  "manuscript_id": "Actual submission identifier",
  "submitted_at": "2026-01-01T00:00:00Z",
  "submission_receipt": {
    "path": "evidence/reviewer-intake/P01/submission.txt",
    "sha256": "SHA256_OF_ACTUAL_RECEIPT",
    "locator": "receipt line 1",
    "quote": "Exact unique receipt excerpt"
  },
  "reviewer_source": {
    "path": "evidence/reviewer-intake/P01/reviewer.txt",
    "sha256": "SHA256_OF_ACTUAL_REVIEWER_TEXT"
  },
  "needs_new_experiments": false,
  "comments": [
    {
      "comment_id": "R1-C1",
      "reviewer_id": "Reviewer 1",
      "comment": "The exact original comment, not a generated substitute.",
      "source_location": {"start_line": 2, "end_line": 2}
    }
  ]
}
```

The original comment must appear verbatim at the declared source lines. Comment
IDs must be unique within a round. The human supplies the real submission receipt
and identities; successful structural checks cannot prove journal acceptance,
reviewer identity or authenticity of an external email.

`prepare_start(project, paper_id, source, actor)` is read-only. The owner control
calls `start_revision(project, paper_id, source, actor, review_sha256, run_id)`
only after authorization against the complete dossier. Both starting and
refreshing require a cloud executor. A new round cannot use a paper changed after
its prior G5 approval; recover the actual approved submitted version first.

The non-billable owner issue first requests a review dossier with
`action: review_dossier`, `operation: start_revision`, `paper_id: P01` and the
exact project-relative intake `source`. After reviewing its files and blockers,
use `action: start_revision` with those same selectors, the dossier's
`expected_sha256`, a concrete review `note`, and `allow_paid: false`. The existing
owner-only issue boundary supplies the numeric cloud run ID. This does not
authorize a model call; a later existing cycle still checks the cumulative budget.

## Immutable history and working artifacts

The cloud control plane freezes each submitted paper tree, source comments,
intake, submission receipt, prior state and approvals under
`reports/reviewer-rounds/P01/R001/`, then `R002/`, and so on. Each manifest links
the exact previous manifest hash. The protected
`state/reviewer-rounds/P01.json` lists the contiguous history. Originals are not
model context or submission files. The working revision baseline is reset to the
just-frozen manuscript source tree; the older baseline remains in the archive.

The writer prepares:

- `reviews/concern-cards.json` and its deterministic concern-response outputs;
- `reviews/response-matrix.csv` covering exactly the actual reviewer comment IDs,
  with source-bound manuscript locations and explicit reasons for partial or
  rejected changes;
- `reviews/reviewer-response.json`, shown below;
- `submission-materials/response-letter.md`, containing a `## R1-C1` heading and
  the exact response text for that comment;
- the revised manuscript, figures, supplement and existing integrity evidence.

```json
{
  "schema_version": "1.0",
  "round_id": "R001",
  "responses": [
    {
      "comment_id": "R1-C1",
      "response": "The exact English response included in the response letter.",
      "evidence": [
        {
          "path": "evidence/actual-protocol.md",
          "sha256": "SHA256_OF_ACTUAL_EVIDENCE",
          "locator": "protocol section and line",
          "quote": "Exact unique supporting source excerpt"
        }
      ]
    }
  ]
}
```

Every response, including a disagreement, needs current supporting evidence.
The response itself, response letter and editable original-comments copy cannot
serve as their own evidence. The deterministic audit verifies comment coverage,
hashes, real manuscript locations, unchanged frozen history, response consistency
and current non-Claude provenance. It does not establish semantic correctness.
Existing numerical, citation, claim-strength, revision-ledger, independent-audit
and human G5 controls remain required. A passing report is a reviewable package,
not scientific approval or journal acceptance.

`refresh`, `audit`, `validate_saved_report`, `review_binding` and `prompt_feedback`
provide deterministic integration points. Saved reports become stale when current
responses, evidence or source text change. Each subsequent external round requires
completion of the new human G5 cycle and a newly supplied submission receipt.

## Supplemental experiment boundary

`needs_new_experiments: true` deliberately blocks completion. The writer can
prepare `reviews/reviewer-required-experiment-plan.json` describing requested
analyses, datasets, code changes, cost, scientific purpose, exploratory versus
confirmatory status, and required approvals. This proposal grants no execution or
spending permission.

The existing experiment engine forbids re-freezing an already executed G3
preregistration. This adapter therefore does not move a completed study back to
G3 or reuse an old approval for new runs. A separately designed and human-approved
supplemental protocol, budget and executor route are still required before new
experiments can be run. Requests for fresh empirical results cannot be satisfied
by writing plausible results or by marking a template complete. Textual revisions
can proceed while this explicit blocker remains visible.
