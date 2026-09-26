# Repository operating rules

This repository is a research workflow, not a publication generator.

1. Never invent citations, data, experiments, results, reviews, author contributions, journal metrics, or submission status.
2. Treat every scientific claim as provisional until linked to evidence in the claim-evidence matrix.
3. Use current primary sources for journal rules, degree rules, datasets, software APIs, and market facts. Record the URL and access date.
4. Never confuse JCR/JIF quartiles, CiteScore quartiles, SJR quartiles, and Chinese Academy of Sciences partitions.
5. Do not cross G0–G5 without an explicit human approval recorded by `scripts/researchctl.py`.
6. Keep raw datasets, publisher template archives, secrets, credentials, and large experiment artifacts out of Git.
7. Before acquiring data, verify license, research-use rights, privacy, terms, provenance, version, and leakage risk. Do not bypass access controls.
8. Pre-register paper-level hypotheses, baselines, splits, metrics, statistics, compute ceiling, and falsification criteria before final experiments.
9. Preserve negative results and failed runs. Do not select only favorable seeds, datasets, metrics, or subgroups.
10. Enforce role separation: Claude may produce only read-only semantic plans and internal independent audits. Codex/OpenAI writes and remediates every persistent scientific artifact. Result-bearing charts must be rendered locally from recorded data, never supplied as Claude-generated files. GPT Image may make a separately labeled, disclosed conceptual illustration, never a data figure.
11. Never auto-submit a manuscript. G5 produces a submission-ready package for human review.
12. Read `references/workflow.md` and the relevant section of `references/stage-contracts.md` before changing a research project.
13. Run model orchestration through `scripts/autopilot.py` or `scripts/api_orchestrator.py`; preserve Claude plans internally, both initial and final independent model-family audits, the non-Claude writer's itemized decision log, and output-provenance hashes.
14. Execute experiments only through `scripts/experiment_runner.py` after the approved G3 plan and budget hashes match.
15. Treat dataset discovery metadata and DOI lookup results as leads to verify, never as license, fitness, or claim-support decisions.
16. Treat third-party gateways as untrusted transport: use HTTPS, keep keys out of files and URLs, record requested and reported model IDs, and stop on missing or mismatched model identity.
17. The author and independent critic must use different model families. A different endpoint or account does not make the same family independent.
18. Never package a file whose current provenance hash identifies Anthropic/Claude as its persistent writer. Human or deterministic local edits must create a new file hash; do not use paraphrasing merely to conceal AI use.
19. Enforce the declared six-paper venue portfolio: at least three current JCR Q1 SCI/SCIE targets and every remainder at least current JCR Q2, all with IF >1.0. Q2 changes only the venue target and never weakens doctoral/originality/experiment/writing gates. Re-check category/year evidence.
20. Write every manuscript-bound artifact in English. G5 must pass the deterministic manuscript-language check; a model's assertion that prose is English is not sufficient.
21. At G5, use line-level academic-style findings for targeted evidence-preserving revision. A user-supplied detector score may guide a separate optional editing pass, but it cannot override scientific quality, claim/citation/numeric integrity, human review or required AI-use disclosure. Never spin synonyms, remove warranted uncertainty or conceal model assistance.

Run repository checks after code or schema changes:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts
python3 scripts/validate_repo.py
```
