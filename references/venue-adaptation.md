# Venue adaptation

Treat scientific content and venue rendering as separate layers.

## Inputs

- semantic manuscript sections, figures, tables, bibliography and declarations;
- current official submission guidelines;
- official Word or LaTeX author template downloaded by the human or an authorized tool;
- `venues/<venue>/venue.json`.

## Procedure

1. Re-verify the venue identity, ISSNs, scope, current metric year, JCR category/quartile, article type, fees, length, reference style and AI/data policies.
2. Record official URLs and access dates. Do not use Scopus/SJR quartiles as JCR evidence.
3. Inspect the archive with `scripts/venue_adapter.py inspect`.
4. Import it into the paper’s ignored `venue-template/` directory.
5. Identify the canonical sample file, class/style files, bibliography style, required metadata and declarations.
6. Map semantic blocks into a new manuscript file. Do not overwrite the publisher sample.
7. Compile or render; inspect page size, margins, columns, fonts, equations, figures, tables, references and metadata.
8. Record any rule that could not be verified. Block G5 for unresolved mandatory rules.

Retargeting must change presentation and venue-specific declarations, not experimental results or scientific claims.

