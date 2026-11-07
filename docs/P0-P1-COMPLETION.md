# P0/P1 completion and acceptance boundary

Version 2.3 closes the requested implementation gaps without claiming that user-specific research, accounts or hardware have already been accepted. The machine-readable source of truth is `config/requirements-traceability.json`; run `python3 scripts/requirements_trace.py` to verify that every requirement still points to an existing implementation artifact.

The owner's later [156-item eight-aspect checklist](acceptance/eight-aspects-2026-11-07.csv)
separately records software verification, unmet numerical and architecture targets,
missing real research and unavailable historical evidence. This P0/P1 capability
table does not declare that broader checklist fully satisfied.

## P0 — operational foundation

| Capability | Implemented evidence | Still requires |
|---|---|---|
| GitHub Actions | Python 3.10/3.12/3.13 matrix with declared figure/reader packages, Windows PowerShell parse, scheduled/manual live API and container jobs, optional installed-adapter smoke job | Check the exact current commit's run; earlier successful runs do not validate changed code |
| Optional D-drive setup | `install-d-drive.ps1`, `bootstrap-d-drive.sh`, path/caches/runtime checks and Docker location receipt | Legacy Windows/WSL2 option; cloud-only research does not require it |
| Public literature APIs | Contact-aware headers, provider-specific bounded retries, paced live acceptance and raw/hash receipts | Real network execution; provider outages and rate limits remain possible |
| Docker isolation | Digest-pinned, no-network, read-only, dropped-capability executor with cross-runner checkpoint/export acceptance | Actual declared research inputs and frozen plans; Linux CI does not prove optional WSL2 installation |
| PaperQA2 / ToolUniverse / ref-verify | Pinned package checks and input/output/error receipts; controlled PaperQA2 retrieval and reviewed credential-free ToolUniverse UniProt lookup | Authorized corpus/request and source rights; model-bearing paths must use the existing cumulative-cost controls; arbitrary unmetered SDK tools remain blocked |
| Chat-first Codex control | Project Skills plus zero-cost MCP `research_context`, `research_projects`, `research_route` and `research_status` | Enable/reload project MCP in the Codex client |

## P1 — research quality and output layers

| Capability | Implemented evidence | Still requires |
|---|---|---|
| Scientific figures | 37 deterministic chart families; SVG/PDF and optional high-DPI PNG; claim/data/provenance binding | Real experiment tables, actual source provenance and inspection of final rendered figures |
| Research architecture | Typed nodes/edges; deterministic DAG/cycle layouts; editable IR/HTML plus SVG/PDF/PNG | Author validation of every relationship |
| Systematic review | Protocol binding, independent dual screening, adjudication, report/study grouping, risk of bias, PRISMA/report exports and completed-checklist validator | Human screening, full-text assessment, ROB judgments and signed checklist |
| Paper consistency | Fact locations, canonical claims, inference limits/status, five manuscript regions, theory→measurement chain, paragraph ledger, glossary/acronyms and symbols | Per-paper population and independent scientific review |
| Reviewer response | Source-bound real comments and response preparation; concern cards and editor summaries remain C observations | Preserve genuine comments when a real review exists; simulated feedback does not replace them or add human stage signatures |
| Model routing | Task risk/quality tiers, exact CNY prices, 24-hour health filtering, cumulative project totals and exact-request cache | Configured gateway identities/prices; unchanged model routes and all failed-attempt costs |
| Zotero/Obsidian | Read-only Zotero Local API normalization; Obsidian links/tags/orphans; no-upload hashes | Local application/vault access authorized by the user |
| Skill manager | Hash inventory, security lint, MCP inventory, overlap hints and one-use-token install/backup/update/disable | User-selected roots and review of any third-party license |
| Word/LaTeX | Existing LaTeX path plus genuine Pandoc/python-docx Word build with source/output receipts | Venue template and actual successful final render/export; equations/citations may need correction |

## Non-negotiable integrity boundaries

- Claude/Anthropic may plan and critique but cannot be the current persistent author of manuscript text, captions, tables, figures, supplements or submission materials.
- GPT Image is supplementary conceptual illustration only; deterministic data figures remain primary and every AI illustration needs visual inspection and disclosure.
- Claim-forward writing is supported, but registered unfavorable/null results, material robustness failures and limitations cannot be deleted, weakened or demoted because of direction.
- Detector feedback may improve precise, natural language; the system does not certify human authorship or guarantee detector evasion.
- Lawful OA, institutional access and user-provided licensed exports are supported. The project does not automate Sci-Hub or bypass paywalls, login, CAPTCHA or access controls.
- G1 doctoral and G2 paper topics require actual owner decisions. Other stage decisions are recorded automated checks, never invented human signatures. No agent guarantees Q1/Q2 acceptance, invents author obligations or submits to a journal.

## What “complete” means

P0/P1 implementation is complete when repository validation and tests pass. It does **not** mean six papers already exist. The six-paper outcome remains `workflow-ready`: existing Q1/Q2 ambitions are planning observations, while novelty, data, experiments, manuscripts, venue-fit evidence and actual G1/G2 topic decisions must be produced for the user's actual topic one gate at a time.
