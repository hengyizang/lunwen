# Incremental research capabilities

These tools complement G0–G5. None approves a gate, writes fictitious evidence, automates submission, or makes a Q1/Q2 publication promise. Run them in a WSL2 checkout on D: if storage is constrained. Most commands are local and cost no model tokens.

## Scientific figures and diagrams

Install `bash scripts/bootstrap-wsl.sh --with-figures` first. Profile the exact data before choosing a plot. A hand-written figure spec must first have an explicit, truthful non-Claude authorship attestation; specs already written through the GPT/Codex provenance pipeline are recorded there:

```bash
python3 scripts/figure_profile.py projects/my-phd/results/metrics.csv
python3 scripts/output_provenance.py attest --project my-phd --path papers/P01/figures/performance.spec.json --actor 'Hengyi Zang' --note 'I reviewed and authored this chart design'
python3 scripts/publication_figures.py render --project my-phd --spec papers/P01/figures/performance.spec.json --record --run P01-main-seed-1 --language-checked-by 'Hengyi Zang'
```

The renderer now supports 29 data-chart families: line, scatter, grouped bar, heatmap, forest, box, violin, strip, histogram, binned density, ECDF, area, stacked bar, dumbbell, errorbar, ROC, precision–recall, calibration, confusion matrix, correlation matrix, volcano, precomputed PCA/embedding scatter, precomputed survival curve, two-sided Sankey flow, raincloud, hexbin density, precomputed Q–Q, funnel and waterfall. `schemas/publication-figure-spec.schema.json` defines the exact input fields. ROC/PR/calibration/survival/PCA/Q–Q values must already be computed by registered analyses; the renderer never fits them. Violin, raincloud and box plots use raw observations. Funnel uses precomputed effect (x) and positive standard error (y) coordinates; its optional `reference` must be explicitly declared. Waterfall preserves the supplied category order and sums only supplied contributions. Review output visually for clipping, crowded labels, grayscale legibility and accessibility. `source_data_export: true` explicitly copies source tables into the figure folder and must be enabled only if release rights allow it. Journal column widths, color policy and supplementary-file instructions still need per-venue visual QA.

For architecture, method, mechanism, workflow, sequence, lifecycle or dataflow diagrams, prepare an author-reviewed JSON IR following `schemas/research-diagram.schema.json`:

```bash
python3 scripts/research_diagrams.py --project my-phd --spec papers/P01/figures/method.json --record --language-checked-by 'Hengyi Zang'
```

One IR produces editable JSON and HTML plus SVG/PDF/PNG. For a complex architecture, assign every node an integer `layer` (left-to-right 0–7) and optional `rank` (top-to-bottom 0–7); duplicate positions fail. Without these coordinates a deterministic compact grid is used. Review each arrow's scientific meaning and final layout. More complicated topology can use specialized local Python/SVG code, but still needs claim and figure-provenance checks.
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

Quick needs at least one receipt, Standard two, Deep/Audit three. These are workload profiles, not certificates of search completeness. Fill `evidence/systematic/screening.json` with named title/abstract and full-text decisions, individual exclusion reasons, explicit `not_retrieved` full-text outcomes and exact included-study evidence locations. Deep/Audit need two distinct named reviewers' decisions at each decided stage; disagreement requires a third named adjudicator and reason. Their included studies also need method, population, outcome and limitation comparisons. The report exports a PRISMA-style SVG/JSON flow (including records screened, reports sought/not retrieved/assessed), executed-query receipt log, included JSON/BibTeX/RIS, a comparison-matrix CSV, escaped HTML and a deliberately uncompleted PRISMA 2020/PRISMA-S author checklist template. Fill effect comparability and contradictions from verified full text. See [official PRISMA 2020](https://www.prisma-statement.org/prisma-2020-flow-diagram) and [PRISMA-S](https://www.prisma-statement.org/prisma-search): reconcile multiple reports per study and all checklist items manually; this ledger assumes one normalized work per record/report and does not itself certify compliance. No pending decision is silently counted as included.

Read-only local Zotero exports, Obsidian notes, BibTeX and PDFs:

```bash
python3 scripts/local_library.py --project my-phd --source '/mnt/d/Research/Papers' --actor 'Hengyi Zang'
```

The index and research-wiki map keep source paths and SHA-256, without copying or uploading source PDFs. A discovered DOI is a lead, not evidence or a license.

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

Record `reviews/paper-facts.json` following `schemas/paper-facts.schema.json`. It links exact facts to file hashes and page/row positions, construct–measurement–analysis chains, claim anchors in five manuscript sections, introduction paragraph functions and the glossary. A ledger must contain actual facts, claims and argument entries; an empty measurement array needs an explicit `measurement_not_applicable_reason`. Run:

```bash
python3 scripts/manuscript_audit.py --project my-phd --paper P01 --manuscript papers/P01/manuscript/main.tex --spec papers/P01/reviews/paper-facts.json --output papers/P01/reviews/manuscript-audit.json
```

The audit reports missing/stale anchors and terminology inconsistencies, not a machine verdict on construct validity. Have the independent reviewer inspect its findings. For real external reviewer letters, prepare `reviews/original-comments.json` and `reviews/concern-cards.json`, then use `scripts/rebuttal_triage.py --project my-phd --paper P01 --original papers/P01/reviews/original-comments.json --cards papers/P01/reviews/concern-cards.json --output-dir papers/P01/reviews/triage`. It refuses missing comments or over-budget submitted drafts; the existing response-matrix and revision-trace still check actual manuscript changes.

Optional detector feedback is read from a user-provided versioned score report (0–100, both text hashes). `scripts/detector_feedback.py --prepare --before <draft> --feedback <report.json> --output <brief.json>` emits hash-bound, line-located academic-language findings and a bounded revision brief without a model call. After a GPT/Codex editorial revision, run the same command without `--prepare`, with `--after <revised>` and a refreshed score report. It compares scores, language regressions and protected numeric/citation/claim-language tokens. A lower score may guide further targeted editing, but never asserts human authorship or overrides numeric/citation/claim-strength drift checks and required AI disclosure. No detector API or outcome guarantee is built in.

## Budgeted API tasks and independent Skill manager

Auxiliary extraction, formatting, screening, evidence synthesis and independent critique can be preflighted with no paid call:

```bash
python3 scripts/task_router.py --project my-phd --kind metadata-extraction --provider uuapi-openai --prompt-file evidence/auxiliary-task.txt
```

After examining its model/cost ceiling, append `--execute` to send one paid request. It saves internal output only under ignored `api_runs/`. The full paper still uses `api_orchestrator.py cycle` and its Claude planner/critic versus GPT writer roles. `DR_OS_FAST_OPENAI_MODEL` selects an alternate cheap GPT model; set exact `DR_OS_MODEL_PRICING_JSON`, for example `{"your-model":{"input_per_million":1.0,"output_per_million":6.0}}`. The gateway's requested/reported model check and budget stop remain active.

Skill inventory is separate from paper state:

```bash
python3 scripts/skill_catalog.py scan --root '/mnt/d/Research/lunwen/skills' --output-dir '/mnt/d/Research/skill-catalog'
```

It produces hash-cached latest/history JSON and offline searchable HTML. Possible overlap is a hint, not an automated equivalence decision. `plan` followed by a one-use-token `apply` can back up, fast-forward update a clean standalone HTTPS GitHub Skill, or move one skill into recoverable trash. It never updates or deletes Skills during `scan` and will not update plugin-managed or parent-repository directories.

## Upstream method and license boundary

The workflow ideas from Supervisor Skills and Academic Research Skills are independently expressed through the theory/measurement audit, pre-submission concern prioritization, deep literature comparison and paragraph ledger. No restricted upstream code, Skill text, figures or assets are copied into this repository. Their license obligations would need separate review before any future direct installation or redistribution.
