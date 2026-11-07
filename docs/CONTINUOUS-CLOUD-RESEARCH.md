# Continuous owner-approved cloud research

The owner can authorize round-the-clock **system availability**. This means
serialized, bounded GitHub Actions jobs that preserve their progress and request
the next healthy cycle. It is independent of an open ChatGPT page. It does not
mean a single runner lives forever, or that the researcher has 168 hours of human
review time each week. For cloud-only intake use `human_review_mode: on_request`,
`weekly_hours: null` and `system_execution_hours_per_day: 24`; record actual human
hours only when the researcher supplies them.

## Standing execution authority and topic decisions

The protected `state/continuation.json` records the named owner, the original
confirmation time and words, the exact intake SHA-256 and the actual G0 decision
artifact SHA-256. G0 may be a deterministic decision. This execution authority
cannot grant a spending tranche or supply a human topic decision. A changed
intake, missing prior decision or failed evidence check stops
dependent work. The serialized controller invokes `ready` and `advance` after
successful checks. It stops for the doctoral topic at G1 and each paper topic at
G2; it never invokes human `approve` or submission. Old non-topic stages waiting
for approval are rechecked and either completed automatically or reopened for
machine work with a recorded reason.
Actual human topic decisions use [cloud topic controls](CLOUD-HUMAN-CONTROLS.md).

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

The configured cumulative project total is the only model spending limit;
the default is CNY 300. There is no per-paper cap, paid opt-in, fixed increment
or separate billing approval. All attempts reserve and account their cost in
the same ledger. Verified actual fees are used when available; otherwise a
clearly labeled conservative upper estimate counts against the total. Pending
bounded reservations leave the remaining total usable. Model-bearing PaperQA2
and ToolUniverse paths need a calculable external cost or upper bound that can
enter that total. The reviewed ToolUniverse UniProt accession lookup is a
credential-free public HTTPS request with zero model calls; its receipt records
that limited cost basis and every attempt. Other SDK tools remain blocked until
their actual charges or conservative upper bounds can be counted.
See [the current cost policy](TOTAL-COST-POLICY.md).

A failed scientific or execution check remains visible for repair. A pending
provider bill is not an independent approval gate when its upper cost is already
accounted. After the controller repairs an actual fault, it can reset the failed
checkpoint and resume within the unchanged total. Configuration and gate waits
remain visible and are rechecked by the recovery schedule.

## Completion

The schedule stops only when every expected paper has `submission_ready` status,
its own recorded G5 machine decision and a SHA-256 matching the current checked paper
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

Use the title prefix `[research-cloud]`. `allow_paid` is an optional legacy field,
not a payment approval. The requested operation and remaining cumulative total
determine whether work can proceed. Never put a key in an issue, commit, artifact
or chat.
