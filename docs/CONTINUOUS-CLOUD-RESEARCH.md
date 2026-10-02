# Continuous owner-approved cloud research

The owner can authorize round-the-clock **system availability**. This means
serialized, bounded GitHub Actions jobs that preserve their progress and request
the next healthy cycle. It is independent of an open ChatGPT page. It does not
mean a single runner lives forever, or that the researcher has 168 hours of human
review time each week. For cloud-only intake use `human_review_mode: on_request`,
`weekly_hours: null` and `system_execution_hours_per_day: 24`; record actual human
hours only when the researcher supplies them.

## Standing confirmation and scientific gates

The protected `state/continuation.json` records the named owner, the original
confirmation time and words, the exact intake SHA-256 and the actual G0 approval
artifact SHA-256. It cannot grant a spending tranche or approve G1–G5. A changed
intake, a missing prior approval, a complete current-stage dossier or a stage
awaiting human approval stops model work. Present that dossier to the owner and
use the separate human control plane to record their decision. Automatic continuation never invokes `ready`, `approve`, `advance` or submission.
Explicit owner decisions are recorded through [cloud human controls](CLOUD-HUMAN-CONTROLS.md).

One allowed cycle uses Claude for read-only planning and independent criticism,
and the configured OpenAI model for persistent authorship. All existing evidence,
provenance, experiment and scientific-quality checks still apply. The October 7
target does not lower them or guarantee that every paper will be ready by then.

## Continuation and recovery

`.github/workflows/research-continuation.yml` runs on `main`, only in the owner's
repository. Its lock is shared with manually requested owner jobs, preventing
concurrent reads, spending and pushes of project state. Each successful bounded
cycle pushes its checkpoint before requesting the next identical workflow. A
15-minute schedule provides recovery wakeups; it is not the normal delay between
healthy cycles. A missing or disabled policy allows no model call.

GitHub schedules can be delayed or dropped. Its concurrency group also has one
running job and one pending job by default; a later wakeup can replace an older
pending job. Check a manually requested job's actual run and ledger receipt
before claiming that its command took effect. Recovery retries do not grant
another CNY 300 tranche. See GitHub's primary documentation on
[schedule events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
[concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency)
and [workflow token triggers](https://docs.github.com/en/actions/concepts/security/github_token).

Each wakeup resolves the shared or separate gateway key/address pairs, validates
HTTPS roots, protocol and token-limit field, distinct exact writer/critic model
IDs and verified positive CNY prices. It does
not test credentials by making paid requests. Invalid or missing configuration
produces a successful waiting receipt. An unchanged idle decision does not create
another state commit. Each run retains redacted logs and tracked results.

The manual workflow offers `check` (default; no model call) and `start` (immediate
current-stage continuation within existing authority). Scheduled and healthy
followup jobs explicitly select continuation. See [gateway startup](GATEWAY-STARTUP.md).

## Spending and pauses

The confirmed first tranche is cumulative CNY 300. Calls inside the unused
approved amount need no separate approval. At 300, 600, 900 and subsequent
boundaries, obtain the next explicit CNY 300 increment. Per-paper warning and
hard limits remain 45 and 60 CNY. Call reservations and settlement use the same
ledger as manual cycles. Missing authority, a hard limit or an unresolved charge
blocks a new paid call. PaperQA2 and ToolUniverse actions whose external charges
cannot be counted in this ledger remain paused.

A failed cycle pauses further automatic model work until its cause and any
unresolved provider bill are inspected. After the owner-authorized control plane
repairs the fault, it can reset the protected failed-cycle checkpoint and resume.
The controller does not blindly retry a failed paid request. Configuration and
gate waits remain visible and are rechecked by the recovery schedule.

## Completion

The schedule stops only when every expected paper has `submission_ready` status,
its own named human G5 approval and a SHA-256 matching the current approved paper
files. A status label alone is insufficient. On completion the workflow disables
its own future schedule. Publisher submission remains a separate human action.

An owner may request an immediate recheck using only this issue body:

````markdown
<!-- doctoral-research-os-cloud-job -->

```json
{
  "schema_version": "1.0",
  "action": "continuation",
  "project": "my-phd",
  "actor": "Hengyi Zang",
  "allow_paid": true
}
```
````

Use the title prefix `[research-cloud]`. `allow_paid: true` marks a potentially
billable cycle; the bound policy and cumulative ledger determine whether a call
is actually authorized. Never put a key in an issue, commit, artifact or chat.
