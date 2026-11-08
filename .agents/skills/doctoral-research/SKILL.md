---
name: doctoral-research
description: Orchestrate or independently audit a doctoral research program with human G1/G2 topic decisions and evidence-bound automated stage checks. Use when starting, continuing, checking or retargeting research; never guarantee publication or invent authority.
---

# Doctoral Research

Locate the repository root, then read `references/workflow.md`, `references/research-integrity.md`, and only the current section of `references/stage-contracts.md`.

Interpret the request as one of:

- `start <slug>`: initialize through the API-first `scripts/start.sh` path and prepare G0;
- `continue <slug>`: inspect `researchctl.py status`, run the current stage through `scripts/api_orchestrator.py cycle`, and advance after its recorded checks; request human decisions only for G1/G2 topics;
- `topic <slug>`: attack topic novelty, feasibility and doctoral architecture;
- `experiment <slug> <design|run>`: design or audit reproducible experiments;
- `review <slug> [paper]`: audit code, statistics, claims and reproducibility;
- `citations <slug> <paper>`: run reference identity checks, DOI-bound abstract claim verification and route deeper claims to full-text evidence;
- `journal <slug>`: produce an official-evidence-backed challenge/target/safety shortlist from the authorized JCR registry;
- `retarget <slug> <paper> <venue>`: verify official requirements and template adaptation;
- `package <slug> <paper>`: build a deterministic ZIP for human inspection and manual upload;
- `audit <slug>`: run a cross-stage integrity check.
- `figures <slug> <paper>`: choose evidence-matched SCI data charts, research diagrams, or explicitly identified conceptual illustration;
- `systematic-review <slug>`: run hash-bound screening and PRISMA-style accounting;
- `paper-audit <slug> <paper>`: verify facts, measurement, alignment, paragraphs and terms;
- `library-import <slug>`: index explicitly selected Zotero/Obsidian/PDF files;
- `api-tasks <slug>`: preflight a bounded auxiliary API task before any paid execution;
- `skill-catalog`: inventory project/global Skills without changing them.

For a natural chat request, use the project MCP server in `.mcp.json` to call `research_route` or `research_status` first. These tools are deliberately zero-cost and cannot approve gates, start paid calls or submit. Then read the routed Skill and continue through the existing state machine.

Use deterministic scripts for state, discovery, manifests, downloads, approved experiments, citations and archives. Default to the external API worker so this Codex conversation remains a thin manager; do not invoke `autopilot.py`, Claude Code or Codex CLI unless the user explicitly requests CLI mode. Claude is restricted to read-only semantic planning and internal independent audits. GPT/OpenAI independently writes and remediates every persistent text artifact and plotting specification; `scripts/publication_figures.py` renders final charts from recorded data. Use the current three-call ordinary cycle; actual actionable findings alone trigger repair and re-review. Final submission uses three mutually blind, different-family source views frozen before synthesis, as defined in workflow.md. Per-stage observations have no gate authority. Preserve existing project cumulative totals, model assignments, reasoning efforts and exact-request cache. Never edit gate approvals by hand or impersonate a G1/G2 topic decision. The controller records G0/G3/G4/G5 decisions after current automated checks pass.

Retain the G2 six-paper architecture and each actual human topic choice, then
finish the active paper's G3–G5 before the next enters G3. Use the current phase,
A/B/C checks and scientific/submission split in `references/stage-contracts.md`.
C editorial observations do not create gates. Preserve actual rights, source
hashes, frozen confirmatory inputs, original adverse results and provenance.
B final checks are reused only for the unchanged bound snapshot; no added human
G3/G4/G5 decision, ranking floor or journal AI-policy gate.

For new bounded capabilities, read the matching Skill under `skills/figures`, `skills/systematic-review`, `skills/paper-audit`, `skills/library-import`, `skills/api-tasks` or `skills/skill-catalog`. Their outputs are complements to the existing state machine, never alternative approvals. A user-triggered ChatGPT-web task may yield a manually imported, hash-bound artifact; do not treat a consumer browser session as an unattended API or a source of experimental truth.

At G5 use claim-forward, non-defensive writing without selective reporting.
Headline the preregistered primary finding and strongest supported contribution;
do not promote every secondary or null result into the conclusion. Keep every
registered result locatable in the manuscript or supplement, and never move,
weaken or omit an experiment because of its direction. Use predeclared role,
relevance and statistical adequacy to decide placement. State every material
limitation once and calmly; remove only generic or repeated defensive caveats.

Keep existing six-paper Q1/Q2 ambitions as planning observations. Use actual venue fit and preserve unknown lawful ranking evidence; never fabricate rankings or replace scientific assessment with journal metrics. Use `scripts/open_fulltext.py` for lawful OA candidates. When the user supplies a SciencePro export, ingest it through `scripts/sciencepro_import.py` and treat it as advisory until independently verified.

When acting as the independent critic:

1. Do not read the author’s desired verdict.
2. Inspect runnable code, configs, datasets and raw result tables where available.
3. Recompute critical values and test leakage, seed sensitivity and alternative explanations.
4. Check each material claim against the claim-evidence matrix.
5. Report blockers, major and minor findings, residual uncertainty and a verdict.
6. Preserve findings under `projects/<slug>/reviews/independent/`.

Before packaging, require current output-provenance hashes and reject any file whose current writer family is Anthropic/Claude. Measured figures remain deterministic; GPT Image may supply only explicitly labeled conceptual illustrations with actual source receipts, recorded visual observations and known access/reuse restrictions. Public AI-use statements remain optional and author-editable; truthful internal provenance stays protected.

Never invent missing data, citations or results. Packaging is local-only: never request portal credentials, upload files or auto-submit.

On Windows/WSL, keep the repository, virtual environment, caches, adapter corpora and Docker data under `D:\ad\lunwen` (`/mnt/d/ad/lunwen`). Use `scripts/install-d-drive.ps1`; stop if WSL or Docker data still resolve to C: instead of silently consuming it.
