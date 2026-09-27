# P0/P1 completion and acceptance boundary

Version 2.3 closes the requested implementation gaps without claiming that user-specific research, accounts or hardware have already been accepted. The machine-readable source of truth is `config/requirements-traceability.json`; run `python3 scripts/requirements_trace.py` to verify that every requirement still points to an existing implementation artifact.

## P0 — operational foundation

| Capability | Implemented evidence | Still requires |
|---|---|---|
| GitHub Actions | Python 3.10/3.12/3.13 matrix with declared figure/reader packages, Windows PowerShell parse, scheduled/manual live API and container jobs, optional installed-adapter smoke job | A pushed branch and successful GitHub run |
| D-drive-only setup | `install-d-drive.ps1`, `bootstrap-d-drive.sh`, path/caches/runtime checks and Docker location receipt | Run on the user's Windows/WSL2 machine; move existing WSL/Docker data if checks fail |
| Public literature APIs | Contact-aware headers, provider-specific bounded retries, paced live acceptance and raw/hash receipts | Real network execution; provider outages and rate limits remain possible |
| Docker isolation | Digest-pinned, no-network, read-only, dropped-capability probe | Real Docker daemon in WSL2; Linux CI does not prove WSL2 |
| PaperQA2 / ToolUniverse / ref-verify | Pinned package install checks, executable adapters, input/output/hash/error receipts and contract tests | Authorized corpus/request, any needed credentials and explicit paid-call approval |
| Chat-first Codex control | Project Skills plus zero-cost MCP `research_route` and `research_status` | Enable/reload project MCP in the Codex client |

## P1 — research quality and output layers

| Capability | Implemented evidence | Still requires |
|---|---|---|
| Scientific figures | 37 deterministic chart families; SVG/PDF and optional high-DPI PNG; claim/data/provenance binding | Real experiment tables and named visual review for each final figure |
| Research architecture | Typed nodes/edges; deterministic DAG/cycle layouts; editable IR/HTML plus SVG/PDF/PNG | Author validation of every relationship |
| Systematic review | Protocol binding, independent dual screening, adjudication, report/study grouping, risk of bias, PRISMA/report exports and completed-checklist validator | Human screening, full-text assessment, ROB judgments and signed checklist |
| Paper consistency | Fact locations, canonical claims, inference limits/status, five manuscript regions, theory→measurement chain, paragraph ledger, glossary/acronyms and symbols | Per-paper population and independent scientific review |
| Reviewer response | Mandatory concern-card coverage, full/short response, editor summary, hashes and G5 recomputation | Genuine or simulated reviewer comments and human-approved responses |
| Model routing | Task risk/quality tiers, exact CNY prices, 24-hour health filtering, budgets and exact-request cache | Configured gateway models and deliberate paid health probes |
| Zotero/Obsidian | Read-only Zotero Local API normalization; Obsidian links/tags/orphans; no-upload hashes | Local application/vault access authorized by the user |
| Skill manager | Hash inventory, security lint, MCP inventory, overlap hints and one-use-token install/backup/update/disable | User-selected roots and review of any third-party license |
| Word/LaTeX | Existing LaTeX path plus genuine Pandoc/python-docx Word build with source/output receipts | Venue template and named visual review; equations/citations may need manual correction |

## Non-negotiable integrity boundaries

- Claude/Anthropic may plan and critique but cannot be the current persistent author of manuscript text, captions, tables, figures, supplements or submission materials.
- GPT Image is supplementary conceptual illustration only; deterministic data figures remain primary and every AI illustration needs visual inspection and disclosure.
- Claim-forward writing is supported, but registered unfavorable/null results, material robustness failures and limitations cannot be deleted, weakened or demoted because of direction.
- Detector feedback may improve precise, natural language; the system does not certify human authorship or guarantee detector evasion.
- Lawful OA, institutional access and user-provided licensed exports are supported. The project does not automate Sci-Hub or bypass paywalls, login, CAPTCHA or access controls.
- No agent approves a human gate, guarantees Q1/Q2 acceptance, signs a checklist, selects authorship or submits to a journal.

## What “complete” means

P0/P1 implementation is complete when repository validation and tests pass. It does **not** mean six papers already exist. The six-paper outcome remains `workflow-ready`: at least three papers must target current JCR Q1 and the rest current JCR Q1/Q2, but novelty, data, experiments, manuscripts, venue evidence and human approvals must be produced for the user's actual topic one gate at a time.
