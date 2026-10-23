# Primary experiment recovery and shared relay spending

All operations below run in the owner cloud issue workflow. They never call a model, grant a budget, approve scientific claims, or erase a failed attempt. First obtain `review_dossier` for the exact operation and `source`, inspect the returned artifact, then submit that operation with its `expected_sha256` and a substantive owner `note`. Changed project inputs or implementation invalidate that dossier.

## Unchanged infrastructure retry

Prepare a checkpoint-safe JSON under `program/`:

```json
{
  "schema_version": "1.0",
  "operation": "approve_primary_retry",
  "plan_sha256": "<current experiments/plan.json SHA-256>",
  "budget_sha256": "<current experiments/budget.json SHA-256>",
  "failed_attempt_id": "<latest failed executor attempt>",
  "failure_category": "infrastructure",
  "reason": "<inspected technical failure and reason the unchanged execution is appropriate>"
}
```

`approve_primary_retry` permits only the next named attempt of the exact frozen plan. The original receipt and any partial outputs are retained and checked; another failure requires another exact review. A completed run cannot be rerun for a preferred result. Failed attempts continue consuming the original compute allowance. Statistical evidence, dependent runs, and figures select the single successful receipt only after all preceding failures have explicit recovery approvals.

## Amended primary protocol

Use the same plan/budget hashes with `operation: retire_primary_plan`, a unique `version: v001`, `prior_outcomes_seen: true`, and `new_analysis_phase: exploratory` or `prospective_followup`, plus the material reason. This retires the current execution authority and returns to G3 for a new design and fresh human approval. It does not authorize the new experiments.

The controller seals the prior plan, budget, registry, state, frozen public input files, and original attempt receipts. Private/raw inputs are hash recorded without copying them to public history. Original run receipts and output paths remain protected. The amended plan must use new run IDs and output paths, retain honest analysis phases, and include all historical attempt costs within the unchanged compute ceiling. G1/G2 thesis scope remains binding. Changing that scope uses the separate human scope-amendment route.

## Shared relay guard

Production and current comparison jobs acquire a SHA compare-and-swap reservation on `cloud-state/relay-guard` before taking the before-call meter snapshot. One reservation permits one POST; its credential fingerprint is shared across projects, tests and provider groups that use the same key. Keys themselves are never persisted. Independent debit evidence is bound to the retained before meter before release; missing, excessive or ambiguous fees retain the lock without expiry.

The guard imports unknown fees from the original relay-acceptance, full comparison, clarified comparison and native Argon probe ledgers. Catalog and billing GET requests cannot clear an imported hold. Readiness reports distinguish configured credentials from actual inference eligibility. Closed legacy probe transports have no standalone authority to send another POST.

`reconcile_relay_guard` accepts a supplied JSON with the exact `provider` and `credential_sha256` and one of:

- `kind: settled_legacy`, with exact `hold_ids`: each original branch, file, call ID, provider and reservation must still match a unique independently settled source entry. Deleted, duplicated, relabeled or merely marked-settled entries cannot release a fee. Native historical counter receipts and complete original CheapAI whole-key debit matches are validated in their original formats. The reviewed dossier binds the current source blob, exact entry digest and debit proof.
- `kind: settled_active`, with exact `ticket_id`: the current independent debit must match an existing settlement/reconciliation event in the original project's budget ledger; reconcile that original budget first.
- `kind: settled_trial`, with exact `ticket_id`: first reconcile the call in its original fixed comparison ledger. Its provider, model, run ID, reservation and before meter must match the retained shared ticket. A fresh independent billing read must agree with that ledger's already-accounted debit. The source ledger and proof are bound into the dossier; releasing the shared ticket never reopens the trial, changes its budget or sends a generation request.
- `kind: new_credential`, with `previous_credential_sha256` and the exact owner attestation `Different newly issued credential; prior charges remain held on the original credential.` The current key must have a distinct fingerprint and the old key's unresolved reservation must remain recorded. This does not release or reset the old key's fees.

These decisions require the normal hash-bound owner review; they never increase project or trial spending authority. No model call or paid provider test is needed to validate the controls themselves. Engineering fixtures do not establish research validity or publication merit.
