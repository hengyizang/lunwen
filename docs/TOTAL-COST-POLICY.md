# Total cost policy

The owner's instruction of 2026-11-01 replaces earlier payment approval rules.
Financial controls have two purposes only: calculate costs and enforce the
configured cumulative project total. Existing scientific evidence, data rights,
model identity, independent audits, G1/G2 topic decisions and external submission
requirements continue to apply.

Model/API work uses the existing CNY project total. Compute uses the existing
project compute/cash totals in USD. Do not mix currencies without an explicit
conversion basis, reset spending or silently increase any configured total.
Paper, route and attempt costs remain useful statistics, not separate limits.
The default model project total remains CNY 300; a configured total may be changed
to an explicit amount without requiring CNY 300 increments.

Every request reserves its calculated upper cost against the remaining total.
Actual verified charges replace the estimate when available. If billing or
usage is unavailable, retain or charge the conservative upper estimate and label
it as estimated, never as an actual provider fee. A bounded pending reservation
consumes money but does not independently stop further work that fits the total.
An interrupted experiment retains its execution lease to prevent duplicate
execution and double accounting.

Remove additional financial approval steps: per-paper hard caps, per-call
permission flags, separate paid-start switches, mandatory manual reconciliation,
fixed tranche increments and independent paid-repair quotas. Tests, repairs,
analysis and ordinary model requests use the same total accounting. Legacy
`allow_paid` and paper-budget fields may remain readable for compatibility but
do not grant or deny otherwise valid work.

A read-only command still makes no model call merely because it can. A service
without a calculable rate or upper cost needs an accounting adapter before it
can spend under a total ceiling. This is a missing cost calculation, not a
separate human payment approval. Historical trial receipts remain historical
evidence; the current ordinary research path uses this policy.
