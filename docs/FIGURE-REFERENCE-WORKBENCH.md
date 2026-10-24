# Source-linked figure workbench

Discover reference layouts, bind an original figure brief to the paper, and export
native editable diagrams through the existing cloud controller. No paid image API,
new model route, local inference, GPU rental or parallel research state is needed.

## Sources and retrieval

[Top-Conf Figure Gallery](https://github.com/qwdwqfwq/topconf-paper-figure-gallery)
is pinned at `dbf360a533ee46bc7d4a8f6037717c83f21a633a`. The verified metadata
contains **3449 records**, rather than assuming the article's count. The metadata,
MIT notice and image policy are bound in `integrations/topconf-figure-gallery.lock.json`.
MIT code licensing does not license paper images: reuse permission must be checked
with the original author/publisher. We do not redistribute the images or recolor
another paper's scientific content as our own.

- Default search: metadata BM25 with Chinese/English concepts. Filters cover
  venue, year (2023–2026), best paper/oral/spotlight/unknown, layout and topics.
  Topics are explicitly title-inferred: the upstream records do not provide
  verified abstracts or Chinese image descriptions.
- Optional `semantic:true`: real quantized CLIP on cloud CPU against pinned
  512-dimensional image/text embeddings. Exact bytes/Git-blob checks bind fixed
  assets; execution receipts record SHA-256 and actual ONNX execution. Roughly
  82 MB downloads once per ephemeral runner, with no provider key. English CLIP
  uses explicit Chinese concept expansion. Queries beyond 77 tokens fail rather
  than silently truncate. A failed semantic run never claims lexical fallback
  was semantic. Relevance is not accuracy, scientific quality or visual approval.

## Controlled operations

Prepare a project `program/figure-operation.json`, then use the existing owner
`literature` cloud action with `allow_paid:false` and that `request_file`.
The same operations may be queued at G1–G5 with the current `stage` in
`program/cloud-operations.json`. Neither route approves a gate or figure.

1. Sync once: `{"action":"figure_gallery_sync"}`.
2. Search only for a concrete figure need; reuse the bound report later:

```json
{"action":"figure_gallery_search","query":"时间序列预测的架构图","top_k":5,"semantic":true,"venues":["iclr","icml","neurips"],"patterns":["architecture","framework","pipeline"]}
```

The result returns `report_binding`. The safe offline
`reports/figure-gallery/<id>/index.html` links to originals; `packet.json` is a
bounded reference packet. The preview never downloads remote images. Search
returns at most 20 records and never grants image reuse rights.

3. Select only useful references for existing planner/writer/critic roles in
   `program/figure-reference-context.json` (three to five preferred, one or two
   allowed). Full index/model bytes/duplicate reports stay outside paid context:

```json
{"report":{"path":"reports/figure-gallery/REPORT_ID/search.json","sha256":"CURRENT_REPORT_SHA256"},"figure_ids":["SELECTED_ID_1","SELECTED_ID_2"]}
```

The controller verifies report bindings before supplying selected metadata.
Original full papers remain available through existing literature acquisition
and reading operations when scientific content, rather than layout, is needed.

4. Write an original typed diagram IR and a request following
   `schemas/figure-story-request.schema.json`. Call
   `{"action":"figure_story","operation":"prepare","request_file":"program/main-figure-brief.json"}`.
   It binds paper contract, claims, IR, exact text quotes/line locators and
   selected references. Every module and arrow needs a text/phase mapping.
   Numeric labels require exact source bindings; observed results require real
   sealed executor outputs. Planned and observed evidence stay distinct. Missing
   manuscripts remain unavailable; existing canonical TeX includes are followed.
   Direct DOCX paragraph alignment is not implemented: provide an authorized
   source text mapping first; the controller will not claim an unchecked match.

5. Optionally establish shared six-paper tokens through `figure_story` with
   `operation:"style_prepare"` and a request following
   `schemas/figure-visual-style.schema.json`. `figure_story.default_style()` is
   a starting template, not a journal mandate. It defines fonts, node meanings,
   edge types and redundant non-color encodings. IRs opt in with
   `style_ref:{path:"program/figure-visual-style.json",sha256:"CURRENT_HASH"}`.
   Existing IRs without this reference keep their prior behavior.

6. Export with `{"action":"editable_figure_export","request_file":"program/main-figure-export.json"}`:

```json
{"schema_version":"1.0","diagram_spec":"papers/P01/figures/main.spec.json","expected_source_sha256":"CURRENT_IR_SHA256","formats":["svg","pptx","drawio"],"evidence":[{"path":"papers/P01/method.md","sha256":"CURRENT_METHOD_SHA256","locator":"Method, lines 1-8"}],"story_ref":{"path":"reports/figure-story/main-brief.json","sha256":"CURRENT_BRIEF_SHA256"},"reference_notes":[]}
```

Source IRs require current non-Claude provenance. Outputs contain actual SVG
text/shapes, native DrawingML text/shapes/attached connectors, and draw.io graph
nodes/edges. They are not whole-image wrappers. The receipt preserves IR, layout,
evidence, shared style, implementation and a replay renderer.
For a story-based figure, always carry the current `story_ref` into the export.
The final receipt then revalidates its canonical manuscript, include files,
claims and other brief dependencies, not just the diagram and method file.
Legacy exports without a brief remain usable but explicitly report narrative
alignment as not assessed.
`editable_figure_verify` takes `receipt` with its project-relative path. Story
`validate` and `style_validate` take a `{path,sha256}` request file.

7. Inspect each format at publication size. Export cannot establish scientific
   validity, font availability or final visual quality. Use the existing named
   human-review figure provenance route for final SVG registration, retaining
   the receipt's renderer/IR and all evidence/style dependencies. G5 rechecks all
   existing editable receipts: source/request/evidence/style/implementation/output
   changes require rebuilding. Data-result charts keep their existing registered
   data plotting pipeline. No automatic scientific approval or submission occurs.

## Cloud validation

`.github/workflows/figure-reference-workbench.yml` executes the focused tests and
`scripts/figure_reference_acceptance.py`: actual pinned metadata, bilingual and
filtered retrieval, real ONNX CPU inference, source-bound synthetic briefs,
native exports and independent LibreOffice/PDF/PNG rendering. The fixtures are
explicitly synthetic: they cannot establish research, novelty or Q1 readiness.
Native editable files survive checkpoint transfer; large model caches do not.
No paid model calls occur. Model allocation, CNY500 cumulative ceiling, deadline
and scientific approvals remain unchanged.
