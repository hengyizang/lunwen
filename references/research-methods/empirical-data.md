# Empirical data and identification

Declare relevant variable definitions, units, missing codes and transformations. Check unit-time keys, treatment timing, joins, attrition and expected calendars as the design requires. Explain imbalance rather than deleting rows to force balance; preserve original data and reproducible cleaning.

For causal questions, state the estimand, assignment mechanism, assumptions and plausible rival explanations. Diagnostics and complete forms do not prove identification. Native estimators currently cover two-period DID, independent homoskedastic 2SLS and fixed-bandwidth sharp RDD with conventional HC1; those are implementation limits, not an exhaustive list of legitimate methods. Use another appropriate, checked tool for other designs. A first-stage threshold does not prove instrument validity; one pre-period cannot establish parallel trends.

Choose confirmatory specifications before observing their outcomes and record subsequent exploration. Preserve attempted specifications and adverse results; do not search for favorable significance. Power, precision, multiplicity and sensitivity checks should answer real design questions rather than fill a universal template.

Economic data need the actual variable scope, dates and vintage. FRED as-of snapshots differ from World Bank current retrieval snapshots. Respect known source access restrictions and existing credentials; ordinary authorized retrieval does not require a second owner signature. Preserve actual pagination and responses.

Bind reported estimates and figures to the calculations that produced them. Check units, independent sample counts and analysis phase. A software fixture or successful estimator call does not establish causality, novelty or journal quality. Use `docs/EMPIRICAL-DATA-WORKFLOW.md` as a technical adapter reference; current operating policy remains [AGENTS.md](../../AGENTS.md).
