# Incremental vector publication panels

An existing publication figure can opt in with `"reuse_panels": true` in its
`*.spec.json`. The existing cloud `render_figure` operation reads that spec;
there is no new model cycle, paid API, upstream notebook or rendering service.
The publication renderer also accepts `--reuse-panels`. Specs without this flag
retain the existing full-figure constrained-layout renderer.

The opt-in renderer draws each changed panel as an independent Matplotlib
SVG/PDF, then composes the vector files into the exact figure width/height.
SVG text and shapes remain editable. PDF text, fonts and paths remain vector
objects. The optional high-resolution PNG comes from the composed PDF at the
declared DPI. Native image artists, such as a heatmap, retain their original
representation; a line plot is never replaced by a whole-panel image.

Independent cells use fixed, equal physical gutters. Their layout can differ
from the ordinary constrained-layout figure. Dense legends, long labels,
colorbars or aspect-constrained panels can require a revised specification or
the ordinary renderer. The renderer does not waive a failed alignment,
collision or text check to make reuse succeed. Inspect the actual final-size
outputs before approval.

## What is reused

Executor-owned `reports/figure-panel-cache/<key>/` contains only ordinary
`panel.svg`, `panel.pdf` and `panel.json` files. Checkpoint transfer preserves
these files and the existing output-provenance registry. There is no pickle,
executable deserialization or second provenance database.

Each key binds the exact data path/bytes/table shape, complete panel spec,
style, cell dimensions, axes geometry, panel letter, DPI, palette, markers,
line styles, Matplotlib defaults, resolved font bytes and renderer/recipe/QA
source hashes. Installed Matplotlib, NumPy, pandas and PyMuPDF identity includes
actual installed file hashes and versions, including their active runtime
dependency closure (for example Pillow, fontTools and contourpy). That full package scan occurs once
per executor process, under the explicit assumption that installed packages
are immutable during that process. A new cloud process scans them again.
Project source, fonts, style, specification and input data are rechecked for
each render.

An exact hit skips `_draw_panel` entirely. Changing one panel's separate data
file or title redraws that panel. A shared table change invalidates every panel
bound to those bytes, even if the edited column was unused by one panel.
Changing a shared style or renderer dependency invalidates all dependent
panels. Editing only a caption or the final publication-width QA target does
not require drawing unchanged panels; the full spec and new QA remain bound
to the new build. Changing the grid may reuse panels only when their actual
cell dimensions and letters remain identical; final composition is always new.

Cache receipts have current deterministic executor provenance and bind both
vector files and measured labels/geometry. Missing, unsafe, changed or
incomplete entries fail explicitly. Re-signing an edited cache receipt by
changing its JSON hash fields does not create executor provenance. Preserve
such failed entries for diagnosis; clear only the affected cache entry through
an authorized executor maintenance action before rebuilding it.

## Checks and receipts

Every composition runs the existing editable-label/math checks, physical-size
checks, grayscale and color-vision previews, panel-alignment audit and
final-PDF collision audit. Cached measured label expectations and axes geometry
are translated into their exact final cell positions. A cache hit never reuses
a prior final-figure QA verdict. Final G5 validation rechecks cache receipt and
vector bytes plus current renderer, style, font and installed runtime identity.

The ordinary `.figure-build.json` and `.render-receipt.json` include panel keys,
cache receipt hashes, drawn/reused counts and exact source bindings. Existing
spec/data/output seals, source-run lineage, English-label review, figure
registration, independent scientific review and G0–G5 approvals still apply.

The reported execution scope is explicitly `downstream_rendering`, with
`experiment_reproduction_assessed: false`. Replotting recorded outputs or
reusing a vector panel does not reproduce their experiment. Existing native
reproduction controls remain authoritative:

| Requirement | Existing native control |
| --- | --- |
| Full immutable inputs/helpers and actual execution receipts | `experiment_runner.py` checks approved frozen protocol hashes, full declared input files and successful dependency receipts. |
| Pinned isolated environment and captured runtime | `study_environment.py` and `research_quality.validate_clean_room_reproduction` retain locked runtime, image digest, disabled network, read-only root, disjoint isolation instances and exact source commit. |
| Actual scientific output comparison | `research_quality.validate_baseline_reproduction` and `validate_clean_room_reproduction` check exact successful attempts, complete current output sets and G3-predeclared metric tolerances. |
| Scope and independent human judgment | G3-declared original/clean-room run sets and `create_reproduction_confirmation` bind a named reviewer to both current reports. Downstream rendering grants none of these judgments. |

The upstream AIPOCH notebook barriers for truncated source, partial helper
capture or partial environment locks are not imported as new local notebook
states. Native full-file hashes and runtime/executor checks already block
missing or changed declared evidence. A hash cannot establish that a scientist
declared every necessary helper or that a numerical comparison is scientifically
adequate; those remain explicit scientific-review responsibilities.

`tests/test_figure_panel_cache.py` is a synthetic cloud CPU regression: actual
two-panel drawing, an unchanged redraw skip, one-panel data/spec edits, shared
style and renderer invalidation, retained editable SVG/PDF, existing QA and
tamper rejection. It is software acceptance evidence only.
