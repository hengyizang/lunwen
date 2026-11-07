# Cloud topic decisions and compatible controls

Only the doctoral topic at G1 and each paper topic at G2 require a human research
selection. G0, G3, G4 and each paper's G5 use evidence-bound machine decisions.
The controller records the actual decision kind and never invents a human
signature. Existing spending authority, data rights, independent model audits,
frozen protocols, hashes and scientific checks remain required.

## Review and select a topic

The serialized continuation marks a passing topic stage ready. It then stops
for the actual topic decision. A read-only dossier exposes the exact current
materials and implementation hash; obtaining it records no selection.

For cloud controls, use an issue created by the repository owner's GitHub
account, with title prefix `[research-cloud]` and exactly the marker and JSON
block below. G1 selects the doctoral topic; omit `paper_id` for G1. G2 requires
one exact `paper_id` per decision.

````markdown
<!-- doctoral-research-os-cloud-job -->

```json
{
  "schema_version": "1.0",
  "action": "review_dossier",
  "operation": "approve",
  "project": "my-phd",
  "actor": "Hengyi Zang",
  "allow_paid": false,
  "gate": "G2",
  "paper_id": "P01"
}
```
````

Inspect the actual topic and evidence in the dossier and tracked-results
snapshot. Then record that decision with `action: "approve"`, the same gate and
paper selectors, its exact `expected_sha256`, and a `note` explaining the topic
selection. The placeholder below is deliberately invalid.

````markdown
<!-- doctoral-research-os-cloud-job -->

```json
{
  "schema_version": "1.0",
  "action": "approve",
  "project": "my-phd",
  "actor": "Hengyi Zang",
  "allow_paid": false,
  "gate": "G2",
  "paper_id": "P01",
  "expected_sha256": "REPLACE_WITH_THE_REVIEWED_DOSSIER_SHA256",
  "note": "Explain selection of this exact paper topic and its doctoral contribution."
}
```
````

Every G2 paper needs its own decision on the same current artifact snapshot.
Selecting P01 does not select P02. Each decision changes protected state, so
obtain a fresh dossier for the next decision. Changed topics or mappings require
fresh affected G1/G2 decisions. Old portfolio-level G2 approvals cannot be
silently converted into individual selections.

## Automatic stage work

A scheduled job may call `ready` and `advance` after rechecking the current
stage. It never supplies the human `approve`. G0/G3/G4/G5 decisions identify the
deterministic controller; G3 still binds plan, budget and every preregistration
hash, and G5 still binds each paper's complete current artifact hash.

The normal path performs controlled literature screening in the existing writer
call, source-range registration from actual acquisition evidence, data-quality
checks, preregistration, reproduction or study checks, revision records and
final Word/PDF/figure visual checks. Machine records identify their source and
retain unknowns. Missing files, rights, current audits, registered runs or
supported adapters remain blockers. Automated records are not human reviews or
proof of scientific validity. See [source-bound acquisition](AUTOMATED-DATA-RIGHTS.md).

Old non-topic `awaiting_approval` states are rechecked automatically. Passing
checks produce the machine decision; failed checks reopen that stage for machine
work with a recorded reason. A changed approved topic is never reopened or
selected automatically.

## Compatible manual operations and external authority

The old `ready`, `advance`, `reopen`, data-quality, preregistration, reproduction,
source-scope and screening commands remain available for compatible explicit
control operations. They are not additional mandatory human review steps in the
normal topic-only workflow. An explicitly used legacy human operation continues
to require its authenticated owner issue and fresh hash-bound dossier; a model
cannot manufacture that identity or a human annotation.

Budget authorization and unknown-charge reconciliation are spending controls,
not scientific review. A machine decision never raises the cumulative allowance,
licenses restricted material or authorizes access that the source does not grant.
Actual author/co-author, ethics, institutional and publisher obligations still
apply. No workflow logs into a publisher portal or submits a manuscript.

Human topic decisions remain traceable through `state/cloud-human-decisions.jsonl`,
per-paper topic records and scope seals. Machine decisions retain their own
provenance and history. The historical [2026-10-02 acceptance receipt](acceptance/cloud-human-controls-2026-10-02.json)
records the earlier software-control tests, not validation of the new policy or
a real completed research project. Current synthetic tests exercise control
behavior without provider credentials or scientific conclusions.
