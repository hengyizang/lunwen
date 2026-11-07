# Automatic manuscript Unicode hygiene

At G5 both existing authoring paths automatically use the pinned watermarks-remover implementation. No extra model, detector or paid call is introduced; model routing and reasoning effort stay unchanged.

## Writing and final checks

1. After the author or remediator writes, scan the paper's manuscript sources, including drafts and TeX includes, tables, figures with textual sources, supplements, upload material, disclosures and response matrix.
2. Before builders execute, remove supported character artifacts from eligible TXT/Markdown/TeX/DOCX prose. Eligibility requires current OpenAI or explicit human provenance and excludes executor-owned artifacts. Preserve the original bytes, cleaned copy, exact character locations, diff, source origin, source/output hashes and reviewed implementation hashes in protected reports/manuscript-hygiene/Pxx/changes/<id>/ directories. Atomically replace eligible prose and preserve its author family. Unknown or Claude-authored sources cannot gain new authorship through cleanup.
3. Run the declared Word/TeX/figure/other builders from the resulting sources. Scan again without changing generated files. Initial/final, before/after-build audit snapshots remain in protected run records. An old explicit watermark_cleanup request can resolve to an automatic receipt only when its exact source, pre-clean hash, current cleaned hash and source family all match.
4. Expose the protected latest.json audit as a C observation at G5 and packaging. Missing scan reports, unscanned text and remaining character hints stay visible without creating another release gate. The separate A integrity check still blocks deleted or altered cleanup originals, changed receipts, false source origins and unsupported scientific changes. Packaging itself does not modify approved text.

Structured JSON/CSV/TSV and SVG text is decoded and scanned without normalization; bibliography text is inspected without rewriting. PDF extraction is bounded and read-only. Word body/table prose is eligible for conservative cleanup; headers, footers and notes are inspected without altering their structure. Generated output findings require a source correction and rebuild. Unreadable/encrypted/image-only manuscript PDFs and unsupported/oversized inputs cannot masquerade as a complete scan. An image-only figure PDF is preserved and explicitly marked outside text inspection; the existing figure provenance and actual source-bound automated visual inspection remain mandatory, and media-watermark absence is never inferred.

Mathematics, exact numbers, citations, URLs, quotations, code, commands, source metadata and AI-use disclosure remain protected. Legitimate multilingual, emoji, directional characters and scientific operators are preserved. Retained findings are visible warnings for contextual scientific/human review; their presence does not prove a watermark. Word package metadata, fields, relationships and images remain intact. NFKC, homoglyph replacement and space normalization remain disabled. Revision integrity, visible change records, the current independent critique and final blind panel and actual G1/G2 topic decisions and automated stage checks still apply.

The authoring instructions encourage argument-driven paragraphs, consistent technical terminology and evidence-preserving edits. Random sentence shuffling and mechanical synonym rotation are not used as quality criteria or detector claims. Humanizer H01–H26 and anti-defensive AD01–AD08 remain available as contextual observations; exhaustive dispositions and cadence/length targets are not required. Preserve warranted scientific uncertainty.

## Cloud controls

These optional maintenance commands run only on the authorized cloud executor:

```bash
python -m scripts.research_improvementctl manuscript-hygiene --project PROJECT --paper P01
python -m scripts.research_improvementctl manuscript-hygiene-scan --project PROJECT --paper P01
```

The first applies eligible character cleanup and records a fresh audit. The second records a read-only audit. Neither supplies a human approval. Immutable originals are excluded from general model context and submission packages; a compact diagnostic summary and exact audit path remain available to writers and independent critics. Both orchestrators automatically perform the normal checks without an explicit queue request.

The scientific fingerprint binds actual cleanup receipts and their preserved
ancestry, rather than the latest C scan. Refreshing or removing a scan alone does
not revoke G5. Deleting an original, changing a cleanup receipt or altering the
scientific text still fails the shared A checks at G5 and packaging.

## What a pass establishes

A pass means the assessed supported prose has no remaining removable character artifacts under the pinned conservative policy. It does not mean every invisible character was deleted, that text contains no statistical watermark, or that authorship/AI-detector percentages are established. Reports retain statistical_watermarks: not_assessed and watermark_absence_verified: false. Image pixels, C2PA, EXIF and generic media-watermark removal are outside this text workflow.

Primary references checked 2026-10-11: [watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover), [SynthID Text reference implementation and keyed watermark configuration](https://github.com/google-deepmind/synthid-text#defining-a-watermark-configuration). A vendor-key sampling watermark needs its applicable detector/configuration; a Unicode cleanup result is not a substitute. Required AI-use disclosure stays intact.
