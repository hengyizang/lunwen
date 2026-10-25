# Empirical data and identification

Use docs/EMPIRICAL-DATA-WORKFLOW.md within the existing author/critic cycle.
Declare variable definitions, units, missing codes and formulas in data contracts.
Check full expected calendars, unique unit-time keys, attrition, treatment timing,
join cardinality and unit compatibility. Accept explained imbalance; never delete
rows to force balance. Preserve raw data and explicit step-level cleaning history.

For causal questions, use empirical-design.json: estimand, assignment, assumptions,
rivals, diagnostic/falsification runs, exact data/runtime and every specification
ID/phase/family. Full forms or diagnostic passes do not verify identification.
The native scopes are two-period DID, independent homoskedastic 2SLS and fixed-
bandwidth sharp RDD with conventional HC1, not robust bias-corrected inference.
Unsupported variants need another validated adapter. A first-stage threshold does
not prove instrument validity; a single pre-period cannot test parallel trends.

Use model-based empirical_estimator evidence rather than invented paired arms.
Freeze all preprocessing/specifications and keep every attempted result, including
adverse and exploratory results. Existing pilot, power, multiplicity, independent
review, human approval and thesis-scope requirements remain. Never search for a
preferred significance result or pick the most favorable specification.

Economic data requests explicitly bind variable scope, dates and vintage. FRED
as-of snapshots and World Bank current retrieval snapshots have distinct meanings.
Metadata is a lead; observation access needs protected owner authorization. Keys
stay in cloud Secrets; preserve complete pagination and immutable response hashes.

Use sealed, numerically recomputed estimates for tables and the existing figure
lineage. Map manuscript numbers and actual phases to current source lines; do not
promote software acceptance to a causal/scientific or journal-quality verdict.
Use deterministic CPU tools for repeated data/table work, without an extra model
round. Existing model routes/budgets stay unchanged. The upstream design ideas
are independently adapted; no external SaaS, Stata installation or new provider
is authorized by loading this guidance.
