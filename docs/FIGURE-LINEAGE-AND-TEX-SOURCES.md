# Sealed plot data and complete TeX sources

Final data figures bind every plotted input to an exact successful executor
attempt under the named human G3 plan, budget and frozen protocol. A matching
run ID alone is insufficient. Registration and G5/package validation recompute
the approved run definition, executor receipt, post-run input integrity, complete
expected output set and current output hashes. Unrelated hand-written CSVs,
wrong-paper outputs, changed plans and missing executor receipts are rejected.
Historical failed attempts remain in their original registry. The primary
recovery control selects a replacement only through its separate owner review.

Use parent run IDs normally. A confirmed reviewer extension uses an unambiguous
identifier such as `supplemental/P01/R001/s001/review-run` and the actual input
under `experiments/supplemental/P01/R001/s001/results/`. Its protected parent
control, unchanged original protocol, child G3 authority and named scientific
confirmation must all remain current. A retired, unconfirmed, changed or
other-paper scope cannot supply a final data chart. Validation is read-only;
it never rehydrates or runs a child study just to package the paper.

For permitted deterministic preparation, write a request under `program/`:

```json
{
  "output": "papers/P01/figures/source-data/group-means.csv",
  "source_run_ids": ["approved-analysis-run"],
  "transform": {
    "operation": "group_mean",
    "sources": ["results/approved-values.csv"],
    "columns": ["value"],
    "group_by": ["group"]
  }
}
```

Execute `python -m scripts.figure_lineage --project projects/PROJECT --paper P01
--spec program/figure-data.json` on the authorized cloud runner. The transform
supports explicit column projection, concatenation, grouped means and
`json_rows` projection from a literal dotted `record_path`. JSON columns are
literal dotted scalar paths, e.g. `summary.estimate`, preserving actual Meta
output values. Each operation keeps all source rows; statistical/model fitting,
adverse-result selection or other transformations require an approved analysis
run instead. A `reports/figure-data/` receipt retains source ancestry and output
hashes. Every use replays the transform; a self-authored or re-signed receipt
cannot replace deterministic provenance and matching recomputed bytes.

This transform prepares plot inputs. It does not grant causal interpretation,
repair sample dependence, create uncertainty estimates or establish a claim.
Publication figures retain their existing final-size layout, visual inspection,
English-label and non-Claude provenance requirements.

## Ordered manuscript expansion

`scripts/tex_sources.py` expands literal `input`, `include` and `subfile`
references at their actual positions. The shared language, citation and paper
facts audits use the same ordered source tree. Included section and math content
are checked with original source path/line locations. Cycles, missing files,
unsafe traversal, hidden/credential paths, symlinks and oversized source graphs
fail. Commented and verbatim examples do not become executable includes. This
is a conservative source reader, not a TeX interpreter; dynamic filename macros
must be replaced with explicit, reviewable dependencies.

Submission selection follows the exact local dependency closure: included TeX,
declared bibliography files, local class/style inputs and explicitly referenced
assets. Standard installed publisher/toolchain packages are not copied. An
unrelated manuscript working note is never added merely because it shares a
directory. Internal review/private/control files cannot become public source
dependencies. The existing final-file authorship/provenance check applies to
every selected dependency.

Local `.cls`, `.sty`, `.bst`, `.def`, `.cfg` and `.clo` files additionally need
current named redistribution-rights evidence in the internal
`reviews/tex-dependency-rights.json`:

```json
{
  "schema_version": "1.0",
  "files": [{
    "path": "manuscript/publisher.cls",
    "sha256": "CURRENT_FILE_SHA256",
    "license": "The actual license or submission permission",
    "redistribution_allowed": true,
    "confirmed_by": "The reviewing owner",
    "license_evidence": {
      "path": "manuscript/LICENSE-publisher.txt",
      "sha256": "CURRENT_LICENSE_EVIDENCE_SHA256"
    }
  }]
}
```

This human-reviewed permission is not inferred from an available download or an
MIT license on another repository. The license evidence enters the source ZIP;
the internal review ledger does not. Current scope seals, independent-review
receipts, human G5 approval, protected figure lineage and all existing package
validators still run before creating the manual-upload ZIP. Nobody submits it
automatically. Cloud regressions include extracting this selected source ZIP,
removing the original tree and compiling the isolated source with shell escape
disabled, in addition to missing/stale/cycle/privacy and provenance checks.
