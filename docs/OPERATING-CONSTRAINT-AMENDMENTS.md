# Owner changes to the operating budget and target date

An explicit owner request may replace the cumulative model API ceiling and
submission-ready target date with exact values. For example, CNY300 to CNY500
means a new total ceiling of CNY500, not another CNY500 allowance. The ordinary
`authorize_budget` action still adds exactly CNY300 to the current authorized
ceiling; after an exact amendment to CNY500, its next valid value is CNY800.
The first tranche and all earlier authorization records remain historical facts.

Use `amend_operating_constraints` only while the existing project is at G1,
open for work, with G0 as its only approved gate and no experiment attempts.
It is a non-billable owner control, not a scientific approval or research start.
It updates `intake/constraints.json`, records the precise owner amendment, keeps
the original G0 approval, and rebinds the standing continuation policy to the
amended intake and explicit narrow G0 amendment record. The six-paper doctoral
scope, scientific gates, per-paper limits, failed attempts, provider holds and
all recorded spending remain in force. Automatic research remains in its
existing enabled/disabled state. A target date is a planning input, not proof
that the research can finish by that date.

First request a [cloud human-control dossier](CLOUD-HUMAN-CONTROLS.md) with:

```json
{
  "schema_version": "1.0",
  "action": "review_dossier",
  "operation": "amend_operating_constraints",
  "project": "my-phd",
  "actor": "Hengyi Zang",
  "allow_paid": false,
  "new_ceiling_cny": 500,
  "target_submission_ready_date": "2026-10-26"
}
```

After inspecting the dossier, use a separate owner issue with
`action: "amend_operating_constraints"`, the same two selectors, its actual
`expected_sha256` and a `note` documenting the owner's explicit instruction.
Use the required issue marker and title prefix from the human-control guide.
The current conversation's explicit decision can authorize those exact values;
the controller still requires the reviewed, current source digest. Never edit
the protected ledger or approval records by hand, replace a hash just to pass a
check, or infer an approval for another gate. Changed inputs require a new dossier.

A lower ceiling must cover all recorded spending plus pending reservations.
Budget changes do not reconcile uncertain charges. A successful configuration
check does not establish live provider access, model quality, scientific
completion, or eligibility for journal submission.
