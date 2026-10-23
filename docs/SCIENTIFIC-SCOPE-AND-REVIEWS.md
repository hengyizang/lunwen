# Approved scope and current independent review

G1 human approval seals the declared doctoral question, core/extension scientific
relationship and declared paper count. G2 additionally seals the six-paper map,
thesis synthesis and each paper's scientific question, distinct contribution,
originality boundary and independence. These projections omit ordinary statuses,
working titles, new literature evidence and writing progress. A changed scientific
projection blocks subsequent model cycles, G3–G5 and packaging. Existing approvals
without protected seals are not silently migrated or treated as verified scope.

For a material change, prepare `program/scope-amendment.json` with exactly:

```json
{
  "schema_version": "1.0",
  "id": "scope-amendment-001",
  "gate": "G1",
  "reason": "Explain the actual new evidence and the requested scientific change.",
  "expected_seal_sha256": "current protected G1 or G2 seal hash",
  "proposed_projection": {"the exact candidate scientific projection": "use scientific_scope.projection"}
}
```

Candidate materials are proposals, not permission to continue research under a
different scope. The authenticated owner reviews the existing control dossier and
uses `approve_scope_amendment`. Core/question changes reopen G1; mapping-only
changes may reopen G2. The action preserves earlier approvals and evidence in
history, clears that gate's and later gates' current authorization, and requires
fresh scientific reviews and named human reapproval. It authorizes no experiments,
paid calls, automatic continuation or scientific completion. A subsequent change
to the human-reviewed candidate invalidates that amendment's CAS.

Both API and CLI orchestration seal actual initial/final independent critic
invocations under protected `state/review-receipts/`. Each phase records the
exact audit hash, stage/paper/run/phase, current scientific-source inventory,
prompt hash, actual requested/reported model, family and fresh completion status.
The controller rejects source changes during a critique, cached criticism,
unverified model identity and same-family author/critic combinations. A final
receipt requires its matching initial phase and the actual author dispositions.

At G5 the same native H01–H26, AD01–AD08 and CFH01–CFH38 records are checked again
at the gate and packaging. Their presence is record coverage, not semantic
clearance. Scientific sources changing after the last critique require a real
fresh critique; editing a score, log or receipt cannot substitute for one.
Checkpoint logs, cost diagnostics, approval status and the receipt itself do not
invalidate a review merely because bookkeeping advanced.

Raw operation/request envelopes are withheld from independent critic snapshots,
including custom filenames and explicit context-plan selections. Their scientific
source files remain eligible evidence. CLI critics consume the filtered source
packet without file-exploration tools, preventing a later tool read from restoring
an excluded preferred verdict. A missing appendix/source remains a stated coverage
limit; a clean deterministic check never certifies novelty, inference or Q1 quality.
