# Cloud human review controls

The owner can complete G0–G5 control transitions on GitHub Actions. No local checkout or execution is required. These operations call the existing deterministic validators and never call a model, change spending authority, auto-submit, or certify scientific completion.

## Request a review

Create an issue in this repository from the owner's GitHub account. Its title must start with `[research-cloud]`. The body must contain exactly the marker and one JSON block; no extra prose. Replace the gate and operation with the current pending decision.

<!-- doctoral-research-os-cloud-job -->

```json
{
  "schema_version": "1.0",
  "action": "review_dossier",
  "operation": "ready",
  "project": "my-phd",
  "actor": "Hengyi Zang",
  "allow_paid": false,
  "gate": "G1"
}
```

The issue's Actions result returns `human-control-receipt.json`, an exact `review_sha256`, the current stage/gate/paper, blockers, file hashes and the implementation hashes. Inspect the actual evidence in the tracked-results snapshot and checkpoint, not just the digest. The dossier itself records no decision. Public artifacts must contain only checkpoint-safe evidence with appropriate distribution rights.

## Record the decision

After reviewing the materials, create a separate owner issue with the same selectors and actor. Use the returned digest as `expected_sha256` and explain the human decision in `note`.

<!-- doctoral-research-os-cloud-job -->

```json
{
  "schema_version": "1.0",
  "action": "ready",
  "project": "my-phd",
  "actor": "Hengyi Zang",
  "allow_paid": false,
  "gate": "G1",
  "expected_sha256": "REPLACE_WITH_THE_REVIEWED_DOSSIER_SHA256",
  "note": "Describe your review of the exact materials and any scientific limitations."
}
```

The placeholder above is deliberately invalid. The job refuses a missing or stale digest. A change to evidence, state, the active G5 paper, the reviewer, selectors or controller implementation requires a new review. Checkpoint packaging and routine continuation-status timestamps alone do not invalidate a review.

| Operation | Selectors | Prerequisite and effect |
|---|---|---|
| `ready` | `gate` | All original gate checks pass. Records the current ready hash and waits for approval. |
| `approve` | `gate` | Gate is awaiting approval, original checks still pass, and the ready hash matches. Records explicit named human approval and its cloud review/run identifiers. |
| `advance` | `gate` | Current approval and artifact hash match; gate checks are run again. Advances one stage, or one active G5 paper. |
| `reopen` | `gate` | Gate is awaiting approval. Returns it to work with a recorded revision reason. |
| `confirm_data_quality` | `dataset_id` | G3 is open for work. Validates the current acquired files/report, then writes a separate named confirmation. |
| `freeze_preregistration` | `paper_id` (`P01` etc. or `all`) | G3 is open; data confirmation, power and all frozen inputs validate; there are no registered experiment attempts. Every selected paper is prepared before any preregistration is written. |
| `confirm_reproduction` | `paper_id` | G4 is open. Current preregistration, baseline and clean-room reports, attempts, isolation and output hashes pass the original checks. |
| `screen_literature` | `receipt_id` | G1 is open. Exact successful raw/normalized provider evidence is present. Decision additionally requires `included_work_ids` (possibly empty) and explicit `exclusion_reasons`. Unknown work IDs are rejected. |
| `confirm_source_scope` | `source`, `scope` | A gate is open for work; supplied checkpoint-safe source exists. Scope is `full_text`, `abstract`, `excerpt` or `metadata`. This explicitly does not attest human reading or semantic verification. |

For every operation, first request `review_dossier` with `operation` and only that operation's selectors. Then request the operation with its selectors, `expected_sha256`, `note` and any decision fields. All require `allow_paid:false`. Actor text is a named human attribution; authorization comes from the authenticated owner-created issue, never from a model-authored name or boolean.

## Gate sequence and cloud continuation

Request fresh dossiers between `ready`, `approve` and `advance`: each step changes state and consumes a different review scope. To revise an awaiting-approval gate, review and use `reopen` first. Confirmations/freeze never grant G3 or G4; the full scientific gate still needs separate `ready` and `approve`. G5 remains paper-specific and cannot approve the whole portfolio in one action.

Owner jobs share the existing serialization group with scheduled research, restore the state branch and hash-verified checkpoint, and rehydrate only owner-authorized raw data before checking quality. Raw data stays out of Git and artifacts. Missing rights, files or checkpoints fail closed. Protected receipts stay unavailable to the model writer and the model-authored cloud-operations queue.

An approved gate waits for the separate owner `advance` operation. The next scheduled continuation rechecks the standing policy, prior gates, provider configuration, per-paper limits, remaining cumulative budget, reservations and failure/progress guards. Neither approval nor advance raises the CNY ceiling or starts a model call. A paused failed cycle still needs the existing inspected `resume` procedure.

Decisions are traceable through `state/cloud-human-decisions.jsonl`, original gate approval records, protected confirmation/preregistration files, output provenance and the Actions artifact/run ID. Never infer scientific completion from a successful control receipt.

## Software acceptance

`Cloud human review controls` in the required validation workflow runs real control functions and validators against an isolated synthetic project without provider credentials. It exercises G0 ready/approve/advance, an incomplete G1 remaining blocked, data confirmation, all-paper freeze and reproduction confirmation, using pinned statsmodels for the acceptance power calculation. The G3/G4 datasets and registry records are explicitly synthetic test inputs; they do not demonstrate real study validity or replace the separate real Docker executor acceptance.

Regression tests cover stale/replayed decisions, reviewer mismatch, active G5 paper changes, checkpoint digest stability, invalid or changed data/outputs, all-paper preparation failures, freezing after any attempt, owner-only requests, supplied-source limits and no paid-command dispatch. CI artifacts retain the scoped acceptance receipt and decision-log hash for 14 days.

Real project work remains dependent on configured gateway credentials/exact model prices, verified primary evidence, appropriate data rights and fresh human decisions. The October 7 target does not weaken these checks.
