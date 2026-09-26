# Research capabilities v2.2

## Venue portfolio

The default six-paper programme assigns P01–P03 to current JCR Q1 and P04–P06
to at least current JCR Q2. A later redesign may choose more than three Q1
papers, but never fewer. Every venue must be SCI/SCIE with JIF greater than
1.0. The target is stored in each `paper-contract.json` and repeated in the
paper map and venue registry.

Q2 is a venue target, not a lower scientific tier. All papers keep the same
novelty, baseline, leakage, statistics, power, external-validity,
reproducibility, English-writing and adversarial-review gates.

## Model roles, protocols and budget

Claude/Anthropic remains the read-only semantic planner and independent
critic. GPT/OpenAI remains the only model family allowed to write or remediate
persistent research artifacts. This gives a real family separation even when
both routes use one third-party gateway.

The GPT gateway route defaults to Responses. If the gateway only supports
OpenAI-compatible Chat Completions, configure it explicitly:

```bash
export UUAPI_OPENAI_PROTOCOL='chat_completions'
```

No automatic protocol or model fallback is permitted. Requested and reported
model IDs must still match.

The default prices and hard ceilings are in `config/defaults.json`:

- Claude: CNY 2/M input and CNY 10/M output;
- GPT: CNY 2.2/M input and CNY 11/M output;
- project hard limit: CNY 300;
- active-paper hard limit at G5: CNY 60.

Override a ceiling for one WSL session only when the user authorizes it:

```bash
export DR_OS_PROJECT_BUDGET_CNY='300'
export DR_OS_PAPER_WARNING_CNY='45'
export DR_OS_PAPER_BUDGET_CNY='60'
export DR_OS_ANTHROPIC_INPUT_CNY_PER_M='2'
export DR_OS_ANTHROPIC_OUTPUT_CNY_PER_M='10'
export DR_OS_OPENAI_INPUT_CNY_PER_M='2.2'
export DR_OS_OPENAI_OUTPUT_CNY_PER_M='11'
```

`state/model-usage.jsonl` records role, model, tokens, estimated CNY cost and
cache status. It is local and ignored by Git. The exact-request cache is keyed
by provider, exact model, endpoint, protocol, output limit, system hash and
prompt hash. It never reuses a merely similar request and never removes a
required planner or critic role.

## Lawful open-full-text resolution

Resolve a DOI through OpenAlex, Unpaywall and Crossref:

```bash
python3 scripts/open_fulltext.py \
  --project my-phd \
  --doi '10.xxxx/example' \
  --email 'your-contact-email@example.org'
```

The output is saved under `evidence/fulltext/`. All returned locations are
candidates only: `license_verified=false` and `download_authorized=false` until
the exact copy, license and terms are reviewed. The resolver never bypasses a
publisher login or assumes that library access permits redistribution to a
model API.

## SciencePro without an API

Log in manually when necessary, complete CAPTCHA/2FA yourself, and export a
PDF, DOCX, CSV, TSV, BibTeX, JSON, Markdown or text file. Import it from the
Windows D drive inside WSL2:

```bash
python3 scripts/sciencepro_import.py \
  --project my-phd \
  --source '/mnt/d/Research/ScienceProExports/result.bib' \
  --actor 'Hengyi Zang'
```

The original is copied to `data/private/sciencepro/`, which Git ignores. The
small receipt under `evidence/sciencepro/` records the SHA-256 and extracted DOI
or HTTPS candidates. SciencePro results remain advisory until primary-source,
license and data-provenance checks pass. Do not reuse cookies, reverse engineer
hidden endpoints or automate access that the platform blocks.

## Publication-grade Python figures

Install the local renderer:

```bash
bash scripts/bootstrap-wsl.sh --with-figures
```

Create an English JSON spec such as:

```json
{
  "schema_version": "1.0",
  "data": "results/P01-metrics.csv",
  "output_stem": "papers/P01/figures/model-comparison",
  "style": "high-impact",
  "formats": ["png", "pdf", "svg"],
  "dpi": 600,
  "caption": "Held-out performance with predeclared uncertainty intervals.",
  "alt_text": "Performance curves for the proposed model and two baselines.",
  "claim_ids": ["C-P01-01"],
  "panels": [
    {
      "kind": "line",
      "x": "epoch",
      "y": "macro_f1",
      "hue": "model",
      "xlabel": "Training epoch",
      "ylabel": "Macro F1",
      "title": "External test cohort",
      "uncertainty": {"lower": "ci_low", "upper": "ci_high"}
    }
  ]
}
```

Render it:

```bash
python3 scripts/publication_figures.py render \
  --project my-phd \
  --spec papers/P01/figures/model-comparison.spec.json
```

After the referenced experiment run succeeds and a named person confirms all
figure text is English, bind the final outputs to provenance:

```bash
python3 scripts/publication_figures.py render \
  --project my-phd \
  --spec papers/P01/figures/model-comparison.spec.json \
  --record --run P01-main-seed-1 --language-checked-by 'Hengyi Zang'
```

The renderer also supports common distribution, comparison, diagnostic, embedding, survival and flow panels; see [`NEW-CAPABILITIES.md`](NEW-CAPABILITIES.md) for the exact list and input semantics.
Its journal style uses restrained high-contrast color, marker and line-style
redundancy, vector text, clean grids and a minimum 300 DPI raster. Decorative
3-D perspective and fabricated values are excluded. GPT Image bitmap output is allowed only as a separately registered, visually verified and disclosed conceptual illustration—not a result-bearing chart. Custom Python plot programs remain allowed
when a paper needs a specialized scientific visualization; the same data,
claim and provenance checks still apply.
