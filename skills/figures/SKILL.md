---
name: figures
description: Profile research data and produce reproducible SCI data charts, method/architecture diagrams, or disclosed conceptual illustrations for an active paper.
---

# Figures

Read the active paper's claims, approved experiment registry, target venue and `docs/RESEARCH-CAPABILITIES.md`. Keep data charts distinct from conceptual diagrams and AI illustrations.

1. Profile a real CSV/TSV/JSON with `scripts/figure_profile.py`; ask what registered claim the figure serves. Never infer significance, error bars, sample size, PCA coordinates or ROC metrics in a plotting prompt.
2. Create `schemas/publication-figure-spec.schema.json`-compatible specs. Before `--record`, ensure the source spec has current non-Claude provenance: an actual Codex/GPT authorship record or `scripts/output_provenance.py attest` for a genuinely human-authored/reviewed spec. Use `scripts/publication_figures.py render`; review SVG/PDF/PNG layout, missing labels, legend occlusion and grayscale legibility. The 29 chart families include distribution, uncertainty, diagnostic, meta-analysis, survival, correlation, funnel, Q–Q and effect-contribution views. ROC, PR, survival, PCA and Q–Q coordinates are inputs, not computed by the renderer. Enable `source_data_export` only if redistribution is authorized. For specialized plot types, write a local Python renderer and retain identical source-run/claim/provenance checks.
3. For study architecture, methods, mechanism or data flow, create a typed `schemas/research-diagram.schema.json` IR; run `scripts/research_diagrams.py --project <slug> --spec <project-relative-json>`. Check that every edge is scientifically defensible and inspect all exported formats. `--record` requires a named English-label reviewer and current non-Claude provenance for the IR.
4. GPT Image may create only a clearly labeled conceptual illustration, never a measured result or substitute chart. `scripts/concept_illustrations.py` supports an explicit paid API generation or a manual ChatGPT-web PNG import. The image remains unregistered until a person visually checks all scientific details and runs `scripts/figure_provenance.py approve-illustration` with an AI-use disclosure location. Do not silently replace a deterministic data figure.
5. Before packaging, run `scripts/figure_provenance.py validate --project <slug> --paper <Pxx>` and preserve the original editable source, prompt receipt, figure and hashes.
