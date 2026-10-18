# Scoped relay acceptance, 2026-10-19

The owner authorized at most CNY30 for actual API testing, using ten separately
grouped relay keys. This is software acceptance using original synthetic
fixtures, not a scientific experiment, paper result or G0-G5 approval.
Production model selection, research budgets and family-separated audits remain
unchanged. All execution and checks occur on GitHub cloud runners.

The named trial branch has a push-only workflow. Offline repository checks must
pass before an isolated runner generates a one-time RSA3072 public key. The
private key remains in the runner process. A local administrative encryption
step seals credentials with AES256-GCM, wrapping the AES key with RSA-OAEP-SHA256.
The authenticated context includes trial, run, attempt, commit and random nonce.
Only ciphertext is handed over in the trial PR description; no credentials are
committed. Salted key bindings prevent accepting unrelated keys. The encrypted
description block is removed after consumption. Credentials are never put in
URLs or handed to an additional service. HTTP redirects are refused.

The separate cloud-state branch retains a durable CNY30 authorization and a
write-before-transport reservation for each route/model/fixture. Reruns share
this allowance and skip attempted IDs. No inference retries, paid warmups,
cross-site fallback, built-in tools, recharge or production activation occur.
Unknown billing holds its reservation and stops the trial. Conservative ceilings
include the most expensive context/cache-write rates and a sevenfold safety
margin for unresolved gateway denomination. Reservations are never automatically
released during this authorization, even when usage is complete. The margin
is not actual spend and does not change the owner's price formula.

Quotes use each official input/output/cache item times the screenshot group
coefficient. Foreign USD numeric prices are interpreted as CNY per the owner's
instruction; domestic prices are CNY. Google reserves non-promotional prices;
DeepSeek reserves peak rates. Complete usage is required and cache tokens are
disjoint. Reasoning output is charged once. Official references are recorded in
the receipt; relay billing and actual invoices still require reconciliation.
A malicious or misconfigured relay cannot be made trustworthy by a client-side
ledger; no claim of audited real CNY charges is made without billing evidence.

Two common fixtures test evidence preservation, post-hoc reasoning, source
traceability, leakage diagnosis and a safe evaluation order. One fresh call per
route/model/fixture is saved for offline comparison; routes receive identical
fixture hashes. Exact advertised IDs and returned IDs are checked. Date-pinned
or mismatched identities stop for review instead of being silently substituted.
The automatic rubric checks fixture facts; it is not proof of model authenticity,
doctoral research quality, long-term uptime, tool compatibility or publishability.
Missing/failed/incomplete outputs remain visible and are not graded as successes.

No cache benefit is assumed. Only naturally reported cache use is accounted for;
explicit cache storage or extra cache warmup calls are not requested. Streaming,
tool calling, multimodal quality and long-context research remain unverified by
these short fixtures. Claude output is retained only as internal acceptance
diagnostics, never persistent scientific writing.
