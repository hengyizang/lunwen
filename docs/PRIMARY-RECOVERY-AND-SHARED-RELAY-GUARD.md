# Primary experiment recovery and shared relay spending

Current financial authority is [TOTAL-COST-POLICY.md](TOTAL-COST-POLICY.md).
The current research path uses cumulative project cost accounting only; legacy
shared-relay holds and owner reconciliation operations below remain historical
records, not extra payment gates. Scientific evidence and execution leases remain.

The normal research queue uses machine recovery decisions. It never calls a model to select a retry, grants a budget, approves scientific claims, or erases a failed attempt. The explicit owner cloud operations below remain readable for legacy decisions; they are not routine research approval gates.

On Windows, the runner creates each experiment suspended, assigns it to its
process job, then resumes its initial thread. This closes the startup interval
in which a fast process could exit or create descendants before job assignment.
The implementation follows Microsoft's [suspended-thread guidance](https://learn.microsoft.com/en-us/windows/win32/procthread/suspending-thread-execution)
and [thread enumeration API](https://learn.microsoft.com/en-us/windows/win32/procthread/thread-walking),
accessed 2026-10-31.

## Bounded automatic launch recovery

`primary_recovery.automatic_retry` permits at most one unchanged retry per run,
and only when the actual executor records a failed OS process launch with
`process_started: false` and `ENOENT` or `EACCES`. The executable must now be
available, the complete original process-output logs must be empty, no result
or earlier output snapshot may exist, frozen inputs and G3 plan/budget seals
must match, and the extra estimate must fit the original cumulative compute
ceiling. The failed attempt remains charged conservatively. The machine record
binds the original receipt, logs, plan and budget, identifies the control plane,
and explicitly records that no human confirmation occurred.

A running/completed execution lease or unresolved billing reservation blocks
automatic recovery. Nonzero exits, partial outputs and timeouts never authorize
an unchanged automatic retry; the limited diagnostic route below can withdraw
a failed free-compute protocol. Changed inputs and missing evidence remain blockers.
Neither error-message keywords nor a model's failure-category label can grant
a retry. A second failed attempt cannot enter an automatic retry loop. The
queue records the diagnostic under `state/primary-recovery/diagnostics/` and
does not request a scientific approval to override it.

## Bounded failure diagnosis and protocol withdrawal

The next scheduled controller can revisit its own experiment-inspection report.
It does not treat that report as a request for human scientific review.
`diagnosis_context` permits the existing metered writer and current independent
independent critic cycle to inspect complete source-bound failure logs only
when all recorded attempts failed, frozen inputs are unchanged, compute is
zero-cost, no reservation is unresolved, and the approved thesis/paper topics
still match. Oversized, non-UTF-8 or credential-bearing logs remain blocked.
Successful outcomes, including negative scientific results, cannot enter this
automatic withdrawal path.

The writer may propose the exact `program/primary-recovery.json` packet. A
controller withdraws the failed protocol only after current same-cycle initial
and final independent receipts pass on that proposal and the unchanged evidence.
The record identifies a machine decision, archives the original protocol and
all failed attempts, retains cumulative costs, and returns to G3. There is at
most one automatic withdrawal. The new design must use new run/output identities,
stay within the approved topics and original budget, and disclose observed prior
results and exploratory analysis. Passing the withdrawal proposal does not pass
G4 or establish a scientific finding. Paid compute without independent actual
billing evidence remains blocked.

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

Legacy owner decisions use the same plan/budget hashes with `operation: retire_primary_plan`, a unique `version: v001`, `prior_outcomes_seen: true`, and `new_analysis_phase: exploratory` or `prospective_followup`, plus the material reason. This retires the current execution authority and returns to G3 for a new design and fresh automated evidence/quality checks. It does not authorize the new experiments. The automatic withdrawal route above is narrower and permits only the explicitly observed exploratory phase.

The controller seals the prior plan, budget, registry, state, frozen public input files, and original attempt receipts. Private/raw inputs are hash recorded without copying them to public history. Original run receipts and output paths remain protected. The amended plan must use new run IDs and output paths, retain honest analysis phases, and include all historical attempt costs within the unchanged compute ceiling. G1/G2 thesis scope remains binding. Changing that scope uses the separate human scope-amendment route.

## Shared relay guard

Production and current comparison jobs acquire a SHA compare-and-swap reservation on `cloud-state/relay-guard` before taking the before-call meter snapshot. One reservation permits one POST; its credential fingerprint is shared across projects, tests and provider groups that use the same key. Keys themselves are never persisted. Independent debit evidence is bound to the retained before meter before release; missing, excessive or ambiguous fees retain the lock without expiry.

The guard imports unknown fees from the original relay-acceptance, full comparison, clarified comparison and native Argon probe ledgers. Catalog and billing GET requests cannot clear an imported hold. Readiness reports distinguish configured credentials from actual inference eligibility. Closed legacy probe transports have no standalone authority to send another POST.

`reconcile_relay_guard` accepts a supplied JSON with the exact `provider` and `credential_sha256` and one of:

- `kind: settled_legacy`, with exact `hold_ids`: each original branch, file, call ID, provider and reservation must still match a unique independently settled source entry. Deleted, duplicated, relabeled or merely marked-settled entries cannot release a fee. Native historical counter receipts and complete original CheapAI whole-key debit matches are validated in their original formats. The reviewed dossier binds the current source blob, exact entry digest and debit proof.
- `kind: settled_active`, with exact `ticket_id`: the current independent debit must match an existing settlement/reconciliation event in the original project's budget ledger; reconcile that original budget first.
- `kind: settled_trial`, with exact `ticket_id`: first reconcile the call in its original fixed comparison ledger. Its provider, model, run ID, reservation and before meter must match the retained shared ticket. A fresh independent billing read must agree with that ledger's already-accounted debit. Clarified comparisons retain their original immutable parent blob and frozen task/quote contract, so a later legitimate accounting change to the current parent does not erase their recovery route. The source ledger and proof are bound into the dossier; releasing the shared ticket never reopens the trial, changes its budget or sends a generation request.
- `kind: new_credential`, with `previous_credential_sha256` and the exact owner attestation `Different newly issued credential; prior charges remain held on the original credential.` The current key must have a distinct fingerprint and the old key's unresolved reservation must remain recorded. This does not release or reset the old key's fees.

These decisions require the normal hash-bound owner review; they never increase project or trial spending authority. No model call or paid provider test is needed to validate the controls themselves. Engineering fixtures do not establish research validity or publication merit.
