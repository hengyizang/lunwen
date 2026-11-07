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

API and CLI ordinary cycles use one fresh independent critique after planner and
writer. Protected `state/review-receipts/.../observation.json` and
`observation-latest.json` bind actual source hashes, notebook cycle, prompt and
verified requested/reported identity. Their `gate_authority: false` records an
observation, never scientific clearance. Actual actionable problems may trigger
repair/re-review; legacy initial/final receipts remain historical compatibility.

Final submission uses the distinct domain/editorial/statistics views and frozen
three-family panel in [workflow.md](../references/workflow.md). The controller
rejects changed sources, exposed earlier opinions and same-family critics. It
preserves disagreement without votes or acceptance estimates. C editorial
coverage is not a gate. A integrity checks and B final source/template/export
bindings still apply; ordinary bookkeeping does not invalidate scientific sources.

Raw operation/request envelopes are withheld from independent critic snapshots,
including custom filenames and explicit context-plan selections. Their scientific
source files remain eligible evidence. CLI critics consume the filtered source
packet without file-exploration tools, preventing a later tool read from restoring
an excluded preferred verdict. A missing appendix/source remains a stated coverage
limit; a clean deterministic check never certifies novelty, inference or Q1 quality.
