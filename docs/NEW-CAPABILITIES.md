# Incremental research capabilities

These tools complement G0–G5. None approves a gate, writes fictitious evidence, automates submission, or makes a Q1/Q2 publication promise. Under the strict storage policy, run them from `/mnt/d/ad/lunwen`; caches and runtimes also remain under `D:\ad\lunwen`. Most commands are local and cost no model tokens.

## Scientific figures and diagrams

Install `bash scripts/bootstrap-wsl.sh --with-figures` first. Profile the exact data before choosing a plot. A hand-written figure spec must first have an explicit, truthful non-Claude authorship attestation; specs already written through the GPT/Codex provenance pipeline are recorded there:

```bash
python3 scripts/figure_profile.py projects/my-phd/results/metrics.csv
python3 scripts/output_provenance.py attest --project my-phd --path papers/P01/figures/performance.spec.json --actor 'Hengyi Zang' --note 'I reviewed and authored this chart design'
python3 scripts/publication_figures.py render --project my-phd --spec papers/P01/figures/performance.spec.json --record --run P01-main-seed-1 --language-checked-by 'Hengyi Zang'
```

The renderer now supports 37 data-chart families: the previous 29 plus Bland–Altman, Kaplan–Meier with at-risk counts, SHAP summaries, nomograms, decision curves, weighted networks, chord views and precomputed geospatial maps. `schemas/publication-figure-spec.schema.json` defines exact fields. ROC/PR/calibration/survival/PCA/Q–Q/SHAP/decision-curve coordinates, risk counts, intervals and graph weights must already come from registered analyses; the renderer never fits them. Violin, raincloud and box plots use raw observations. Review SVG/PDF/PNG for clipping, crowded labels, grayscale legibility and accessibility. `source_data_export: true` copies source tables only when redistribution is authorized.

For architecture, method, mechanism, workflow, sequence, lifecycle or dataflow diagrams, prepare an author-reviewed JSON IR following `schemas/research-diagram.schema.json`:

```bash
python3 scripts/research_diagrams.py --project my-phd --spec papers/P01/figures/method.json --record --language-checked-by 'Hengyi Zang'
```

One IR produces editable JSON and HTML plus SVG/PDF/PNG. Nodes and edges have explicit scientific types. For a complex architecture, assign every node an integer `layer` (left-to-right 0–7) and optional `rank` (top-to-bottom 0–7); duplicate positions fail. Without coordinates, acyclic graphs use deterministic layered placement and mechanism cycles use circular placement. Review each arrow's scientific meaning and final layout. More complicated topology can use specialized local Python/SVG code, but still needs claim and figure-provenance checks.
For `--record`, similarly attest a manually created diagram JSON before rendering; the flag does not invent authorship of its source IR.

GPT Image is optional only for a conceptual illustration, never a chart of observations or model performance. To preview an API request without spending money, run:

```bash
python3 scripts/concept_illustrations.py --project my-phd --paper P01 --stem overview --prompt-file projects/my-phd/data/private/overview-prompt.txt --source gpt-image-api --model 'your-supported-gpt-image-model'
```

An explicit `--execute` sends the paid Image API request if `OPENAI_API_KEY` is set. Alternatively, create/download a PNG yourself in ChatGPT web and import it with `--source chatgpt-web --model 'user-reported-or-unverified' --source-file /mnt/d/Research/overview.png`. Both paths create an *unregistered* image with model/prompt/output receipts. Check the visual content and rights before running:

```bash
python3 scripts/figure_provenance.py approve-illustration --project my-phd --paper P01 --figure papers/P01/figures/overview.png --receipt papers/P01/figures/overview.image-source.json --checked-by 'Hengyi Zang' --disclosure-location 'AI-use statement, Methods'
```

The source's model ID is user-reported for a web import, not independently attested. Unsupported API models, missing authorization and model-access restrictions fail; no automatic fallback. Do not use the web session as an unattended API or bypass login/CAPTCHA. Browser access, where available in ChatGPT Work/desktop, is a user-directed step; Codex CLI does not inherit the ChatGPT web browser profile.

## Search, review and local source library

Execute lawful literature searches using the existing `literature_evidence.py`. Then seed a study-level ledger from their exact successful receipt IDs:

```bash
python3 scripts/systematic_review.py seed --project my-phd --receipt receipt-1 --receipt receipt-2 --mode standard --criteria 'Predetermined population, design and outcome criteria' --actor 'Hengyi Zang'
python3 scripts/systematic_review.py report --project my-phd
```

Quick needs at least one receipt, Standard two, Deep/Audit three. Deep/Audit additionally requires a registered or named-author-approved protocol passed with `--protocol`. Fill `evidence/systematic/screening.json` with named title/abstract and full-text decisions, individual exclusion reasons, explicit `not_retrieved` outcomes and exact included-report evidence locations. Deep/Audit needs two independent reviewers per stage, a third adjudicator on conflict, `report_id`/`study_group_id`, method/population/outcome/limitation comparison and domain-level risk of bias from a named tool with two assessors. The report exports report and unique-study counts, a PRISMA-style flow, protocol/search receipts, included JSON/BibTeX/RIS, comparison and risk-of-bias CSVs, escaped HTML, checklist template and hash manifest. Complete and sign all PRISMA 2020/PRISMA-S rows, then run `systematic_review.py validate --completed-checklist <json>`. No pending decision is silently counted as included and the export never self-certifies compliance.

Read-only local folders, Zotero and Obsidian:

```bash
python3 scripts/local_library.py --project my-phd --kind obsidian --source '/mnt/d/ad/lunwen/vault' --actor 'Hengyi Zang'
python3 scripts/local_library.py --project my-phd --kind zotero-local --actor 'Hengyi Zang' --output evidence/local-library/zotero.json
```

The folder index and research-wiki map keep paths and SHA-256 without copying or uploading PDFs. Obsidian mode adds links, tags, missing links and orphans. Zotero mode reads the loopback Local API without a cloud key and does not mutate the library. A discovered DOI is a lead, not evidence or a license.

For a locally held PDF whose use is authorized, install `pip install '.[reader]'` and read the pages without an API call:

```bash
python3 scripts/paper_reader.py --project my-phd --pdf '/mnt/d/Research/Papers/article.pdf' --output evidence/readers/article.md
```

The output contains extracted text by 1-based PDF page, a file hash and a `*.reader.json` receipt. Add `--include-page-images` if `pdftoppm` is installed; add `--translate` only when you deliberately authorize a paid GPT translation of the PDF text to Chinese and the PDF can be sent to that provider. The translation is a personal reading aid, not a verified quotation or a redistribution of the PDF. An unextractable page stops for visual/OCR review.

For a research group meeting, prepare a reviewed JSON plan with `schema_version: "1.0"`, project-relative `source_pdf`, its `source_sha256` and 2–40 slides, each with `title`, `body`, `speaker_notes` and a real 1-based `source_page`. Optional `image` requires `image_sha256`. Then run:

```bash
python3 scripts/paper_to_ppt.py --project my-phd --spec evidence/readers/meeting-plan.json --output evidence/readers/meeting.pptx
```

The editable PPTX keeps source-page footers, speaker notes and a source/plan/deck hash receipt. The renderer does not interpret the article or write slide copy. Open it for visual and scientific QA before sharing; quoted figures need their own reuse rights.

## Paper audit and response letters

Record `reviews/paper-facts.json` following `schemas/paper-facts.schema.json`. It links exact facts to file hashes and page/row positions, canonical claims, allowed/actual inference strength, result status, construct–measurement–analysis chains, claim anchors in five real manuscript regions, paragraph functions, glossary/acronyms and mathematical symbols. A ledger must contain actual facts, claims and argument entries; an empty measurement array needs an explicit `measurement_not_applicable_reason`. Run:

```bash
python3 scripts/manuscript_audit.py --project my-phd --paper P01 --manuscript papers/P01/manuscript/main.tex --spec papers/P01/reviews/paper-facts.json --output papers/P01/reviews/manuscript-audit.json
```

The audit reports missing/stale section anchors, excessive claim strength, undefined symbols and terminology inconsistencies, not a machine verdict on construct validity. G5 recomputes the report. Prepare `reviews/original-comments.json` and `reviews/concern-cards.json` for the final simulated or external review set, then use `scripts/rebuttal_triage.py --project my-phd --paper P01 --original papers/P01/reviews/original-comments.json --cards papers/P01/reviews/concern-cards.json --output-dir papers/P01/reviews/concern-response`. G5 requires complete concern coverage, internal full response, concise response, editor summary and current hashes; the revision trace still verifies actual manuscript changes.

If a venue requires Word, author the evidence-bound source as English Markdown and metadata JSON, record both as non-Claude outputs, then run `scripts/manuscript_docx.py` to create the canonical `manuscript/main.docx`. Pandoc with a journal reference DOCX is preferred; the declared `python-docx` fallback remains available. The receipt is hash-bound, and a named human visual review of pagination, equations, citations, tables and figures is mandatory before G5.

Optional detector feedback is read from a user-provided versioned score report (0–100, both text hashes). `scripts/detector_feedback.py --prepare --before <draft> --feedback <report.json> --output <brief.json>` emits hash-bound, line-located academic-language findings and a bounded revision brief without a model call. After a GPT/Codex editorial revision, run the same command without `--prepare`, with `--after <revised>` and a refreshed score report. It compares scores, language regressions and protected numeric/citation/claim-language tokens. A lower score may guide further targeted editing, but never asserts human authorship or overrides numeric/citation/claim-strength drift checks and required AI disclosure. No detector API or outcome guarantee is built in.

## Budgeted API tasks and independent Skill manager

Auxiliary extraction, formatting, screening, evidence synthesis and independent critique can be preflighted with no paid call:

```bash
python3 scripts/task_router.py --project my-phd --kind metadata-extraction --provider uuapi-openai --prompt-file evidence/auxiliary-task.txt
```

After examining its model/cost ceiling, append `--execute` to send one paid request. It saves internal output only under ignored `api_runs/`. The full paper still uses `api_orchestrator.py cycle` and its Claude planner/critic versus GPT writer roles. Declare quality-tier candidates in `DR_OS_ROUTING_CANDIDATES_JSON` and exact prices in `DR_OS_MODEL_PRICING_JSON`. `scripts/model_health.py --execute` performs a deliberately tiny paid endpoint probe; models marked failed within 24 hours are excluded. Low-risk jobs may choose the cheapest qualifying healthy route, while high-risk scientific judgment prioritizes quality. Requested/reported model and budget stops remain active.

Skill inventory is separate from paper state:

```bash
python3 scripts/skill_catalog.py scan --root '/mnt/d/Research/lunwen/skills' --output-dir '/mnt/d/Research/skill-catalog'
```

It produces hash-cached latest/history JSON and offline searchable HTML, security lint results and optional MCP inventory. Possible overlap is a hint, not an automated equivalence decision. `plan` followed by a one-use-token `apply` can install a lint-clean Skill to an explicit D-drive root, back it up, fast-forward update a clean standalone HTTPS GitHub Skill, or move one Skill into recoverable trash. Any source change invalidates the token. It never updates or deletes Skills during `scan` and will not update plugin-managed or parent-repository directories.

## Upstream method and license boundary

The workflow ideas from Supervisor Skills and Academic Research Skills are independently expressed through the theory/measurement audit, pre-submission concern prioritization, deep literature comparison and paragraph ledger. No restricted upstream code, Skill text, figures or assets are copied into this repository. Their license obligations would need separate review before any future direct installation or redistribution.
