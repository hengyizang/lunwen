# Retired panel cache; complete publication rendering

Panel caching and independent vector-panel composition are retired. The native
`publication_figures` renderer uses its existing complete constrained-layout path
on every invocation. Legacy `reuse_panels` booleans and `--reuse-panels` remain
accepted inputs, but do not reuse panels or create cache receipts. New build and
render receipts contain no `panel_cache` claims.

Old cached builds fail final validation with a rebuild instruction. Keep historical
cache/checkpoint files; render the original specification with the current renderer,
then re-register the changed final outputs through the existing cloud workflow.
Validation never relabels an old cache as a current full render. Frozen experimental
protocols and raw experiment records remain unchanged.

Complete drawing retains actual data hashes, all existing chart recipes, editable
SVG/PDF, optional high-DPI PNG, per-panel source-data export, expected labels,
alignment/collision/output QA, cloud render receipts and output provenance.
Executor-output lineage, independent scientific review and final B export checks
remain authoritative. Replotting recorded data never establishes experiment
reproduction; the existing baseline/clean-room execution and comparison controls
remain required for that separate claim.

The retired cache used fixed independent axes and exact-size PDF composition.
Complete drawing uses constrained layout and a tight output bounding box; page
size, gutters and geometry can differ. Inspect final-size outputs after rebuilding.
Cached SVG parsing and cache dependency fingerprints are removed with their input
path; ordinary source/output/renderer/QA seals still apply.

## Local software comparison, 2026-11-08

Compared the `2dfbf97` renderer and this retirement using two line panels, each
with series A/B at x=1,2,3 and y=[0.4,0.7,0.6]/[0.3,0.5,0.8]. Both panels used
separate CSV inputs, `technical` style, 7.2 by 3.8 inches and 300 DPI. Actual drawer
observations matched all four series, x/y values, axis labels and panel titles.
Every exported source CSV matched its recorded input bytes. The new SVG/PDF/PNG
were byte-identical to the former ordinary full-render outputs in this fixture.
They were not byte/pixel-identical to the retired composition: cached PDF size
was 182.88 by 96.52 mm; full output was 186.18 by 98.98 mm. Actual output QA and
alignment checks passed, and both PNGs were visually inspected.

| Mode | CPU seconds, repeated renders 2 / 3 | Panels drawn each time |
| --- | --- | --- |
| Former cache hit | 0.2268 / 0.2251 | 0 |
| Former full renderer | 0.8718 / 0.8912 | 2 |
| Current full renderer | 0.8648 / 0.8712 | 2 |

Times use `time.process_time()` in the same CPU runtime, with three sequential
renders per mode. Baseline modes shared a process; the current mode used a new
process. First-render CPU was 1.7703 seconds for cache fill and 1.4368 seconds for
the current full path, including process-local initialization. This small fixture
shows the real loss of the cache-hit speedup, not a general performance guarantee.
No model calls or scientific experiments were used.

`tests.test_publication_figures` covers repeated redraws, actual values and vector
outputs, per-panel source exports without top-level data, strict legacy booleans,
and rejection of old cache builds. `tests.test_figure_accessibility` and
`tests.test_figure_provenance` retain final output and scientific source checks.
