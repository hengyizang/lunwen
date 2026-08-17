# Claude Science handoff

Do not assume an undocumented Claude Science command line or API.

## Export contract

Place each export in `projects/<slug>/evidence/claude-science/<bundle-id>/`:

- `bundle.json` conforming to `schemas/science-evidence.schema.json`;
- source PDFs or permitted local references, when licensing allows;
- extracted notes with page/section anchors;
- search log and inclusion/exclusion decisions;
- unresolved questions and contradictions.

## Import procedure

1. Validate the bundle structure.
2. Resolve every citation to a DOI, stable URL or local source identifier.
3. Spot-check quoted/paraphrased support against the source.
4. Mark sources that cannot be opened or independently verified.
5. Add accepted evidence IDs to the project corpus; do not copy a model’s prose directly into a manuscript without verification.

When an official automation interface becomes available, implement only an adapter that emits this contract.

