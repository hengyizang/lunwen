# GPT-5.6 Luna auxiliary replacement

The comparison is closed. See the [scoped results and selection](luna-replacement-results-20261019.md):
Luna passed all three executed cases on each CheapAI route; the Luna screening
case was not sent because billing metadata was rate-limited. CodeKey Luna was
quarantined after one HTTP502. The current workflow only inspects the closed
ledger and receives no model keys.

The owner requested an available replacement for GPT-6 Luna on 2026-10-19.
GPT-5.6 Luna is the first candidate; DeepSeek 4.1 Flash is a read-only auxiliary
comparator and GPT-6.1 Sol high is the reference route. Core scientific writing,
experiment design and independent reviews retain their existing roles.

GPT-5.6 Luna is described as a cost-sensitive nano-tier model in the
[official model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
Its standard short-context prices per million tokens are USD0.20 input,
USD0.02 cached input, USD0.25 cache write and USD1.20 output. Long contexts use
the documented input/output multipliers. The owner's relay conversion and
group multiplier apply; this is not a market exchange rate.

The CheapAI public price table charges GPT-5.6 Luna cache reads at the full
input rate, USD0.20 before the group multiplier. Its one-hour writes are
USD0.40. The test quotes account for this difference rather than assuming
official cache savings. Independent gateway debits determine settled cost.

## Bounded cloud validation

The supplement uses the existing GitHub Actions Secrets and the original
append-only CNY30 test ledger. It reserves at most CNY1 more within that same
authorization. The immutable original 34 requests and their CNY0.11246048
settled debit are preserved. It does not create another CNY30 allowance.

The plan compares five routes on four original synthetic fixtures each:
evidence fact preservation, engineering leakage diagnostics, source-bound
metadata extraction, and ambiguous screening. Luna requests use medium;
Sol and DeepSeek use high. Each route/case has a distinct durable request ID.
Billable POSTs have no retries or automatic fallback. Unknown billing keeps
the reservation and blocks the affected route. The workflow must pass offline
repository checks before it can access the generation step.

Correct JSON alone is insufficient: numeric facts, source identifiers,
missing fields, unknown eligibility and embedded untrusted instructions are
checked. All outputs are software acceptance diagnostics, never scientific
evidence. A small fixed suite cannot demonstrate equivalence over all future
research tasks, provider authenticity, or doctoral/Q1 scientific readiness.

Production routing is not activated by this supplement. Metadata helpers
must still be checked against their supplied sources; screening suggestions
cannot make final inclusion/exclusion decisions. Scripts remain the first
choice for deterministic extraction, normalization, deduplication, formatting,
number comparison and integrity checks. Other task types and low effort need
their own acceptance evidence. The initial four-family production integration
is outside this change; DeepSeek is not mislabeled as an OpenAI provider.

Results are recorded in the same cloud ledger and the dated user report.
After the comparison the workflow returns to non-generating inspection mode.
