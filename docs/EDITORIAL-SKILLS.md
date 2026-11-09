# Editorial skills and text watermark cleanup

Pinned Humanizer, anti-defensive and CCFA methods inform the existing writer and
independent critic. Their separate H/AD/CFH mechanical scanners, scorecards and
per-ID disposition parsers are retired. Actual Unicode character-carrier cleanup
remains active. Model assignments, budgets, G1/G2 topic choices and scientific
integrity controls remain unchanged.

## Pinned sources and method guidance

Exact commits, MIT licenses and LF-normalized file hashes are in
`integrations/editorial-upstreams.lock.json`. Original skills remain readable
under `third_party/`; the CCFA resource lock binds its pinned policies. Native
adaptations identify their current configuration hashes. These sources supply
guidance, not a completed review or scientific clearance.

| Source | Available implementation | Interpretation |
|---|---|---|
| Humanizer 3.1.0 | H01–H26 applicability pointers; full selected guidance and legitimate-use exceptions within an existing model call | No independent pattern scan, coverage table, per-ID disposition or detector result is produced |
| Anti-defensive-writing | AD01–AD08 applicability pointers; full selected guidance includes the 10-item checklist, 5 rewriting steps, 6 sentence functions and contextual checks | Optional editorial judgment preserves necessary scope, uncertainty, controls and interpretation-changing evidence; semantic success is not inferred from a checklist |
| watermarks-remover | Actual pinned `text_unicode.clean_text` through `scripts/watermark_cleanup.py`; automatic source hygiene and post-build/G5/package checks through `scripts/manuscript_hygiene.py` | Removes supported invisible character carriers; KGW/SynthID/vendor-key statistical watermark absence is not verified |

Humanizer guidance addresses binary contrasts; redundant closers/fragments; empty sayings; staged openings; imaginary objections; forced triads; repeated openings; universal dashes; stacked qualifiers; excessive hyphens; passive/missing subjects; stock vocabulary; inflated significance; vague associations; shallow participles; sales language; borrowed authority; copula avoidance; decorative bold; decorative headings; curly quotes; chatbot residue; source-limit guesses; repeated headings; document metadiscourse; reader-mismatched over-explanation. This is a method inventory, not evidence that every pattern has been assessed in a manuscript.

A weak signal such as passive voice, a dash or quotation typography never establishes AI authorship. Scientific uncertainty or a valid negative statement cannot be strengthened or removed to satisfy a style preference. Unassessed Word formatting remains unassessed.

The anti-defensive guidance was refreshed on 2026-10-18 against the reviewed upstream
commit f516147d017a3fe43ae99192cb89d8261b0c8679. Its technical-plan/SOP guidance
also preserves real operations, research purpose, parameters, prerequisites and
prohibitions. Vague conditions stay unresolved until the source supplies the
actual prerequisite; concise wording cannot make a conditional step unconditional.
Technical verbs cannot be replaced with different operations for rhetorical effect.

Scientific content and its surrounding framing call for separate judgment.
Association, confidence intervals, sample counts or baselines do not exempt
stacked hedges or empty modesty from advisory review. Necessary scope, uncertainty
and genuinely small effects remain protected. Code, quotations and equations are
outside stylistic rewriting; existing scientific-preservation checks still bind
actual numbers, claims, citations and source evidence.

`scripts.ccfa_runtime` supplies compact method titles and exact source identities
to ordinary calls. An explicit `ccf-humanization` or `full-reference-review`
request supplies the complete native guidance, exceptions and selected pinned
CCFA policy bodies within the same authorized call. Omitted full text is not
described as consumed. Missing or changed optional H/AD sources are reported as
unavailable without creating another scientific gate or paid request.

## Submission editorial passes

The [evidence-led narrative guide](EVIDENCE-LED-NARRATIVE.md) gives central
claims, decisive figures and exact advantages priority over equal coverage.
Existing stage prompts apply it within the same calls; optional AD06/AD07
guidance addresses contribution framing. Internal
scientific review distinguishes demonstrated issues from verification questions
and optional extensions; the manuscript states the supported contribution and
necessary boundaries. Reframing follows the evidence while preserving original
hypotheses, outcomes, fair comparisons and actual analysis phases.

Complete editorial guidance remains available for explicitly selected review.
Ordinary writing loads current task guidance. H/AD/CFH methods do not produce
standalone current reports. The remaining generic academic-style/linter report
records `editorial_methods.status: retired`,
`mechanical_review_performed: false` and `semantic_review_status: unknown`.
Historical reports remain protected history and cannot supply a current pass.
The legacy `ccfa_humanization` operation returns a nonpaid retired result without
writing a replacement report. Remaining language, style, layout, Unicode and
watermark observations are C; G5 and packaging do not require every disposition
or a clean heuristic report. Use concrete advice for targeted improvement;
missing scores or tables do not require paid rewrites, extra review or approval.

The controller retains actual style/hygiene audit snapshots and their source
hashes. Actual unsupported citation/numeric/claim changes, missing scientific
evidence, omitted interpretation-changing adverse evidence and falsified
provenance remain A problems. Cleanup originals and scientific-preservation
checks remain active. Complete negative/failed/registered comparisons are backed
up separately under `experiments/archive`; manuscripts need not reproduce every
row. Licence/research-use checks remain optional metadata; source/version,
integrity, privacy and known-access controls remain. Public AI-use statements are
optional and author-editable; truthful internal provenance is retained. Apply the current critique and
final blind panel from [workflow.md](../references/workflow.md), without forced
two-round reviews. Actual G1/G2 human topic choices remain unchanged.

## Cloud cleanup request

Write this non-billable request in `program/cloud-operations.json`:

```json
{
  "schema_version": "1.0",
  "operations": [{
    "stage": "writing-and-review",
    "action": "watermark_cleanup",
    "paper_id": "P01",
    "source": "papers/P01/manuscript/main.tex",
    "expected_sha256": "REPLACE_WITH_ACTUAL_CURRENT_SOURCE_SHA256"
  }]
}
```

The placeholder is deliberately invalid. The exact source must exist under this paper's manuscript directory and match its hash. Cloud-only `scripts.research_improvementctl` also exposes `editorial-audit`, `watermark-cleanup` and `watermark-validate`. Cleanup requires `--project`, `--paper`, `--source` and `--expected-sha256`.

Output: `reports/watermark-cleanup/<id>/candidate.<ext>`, `changes.json`, `diff.txt`, `receipt.json`. Receipts retain source provenance, input/output hashes, implementation/upstream hashes, actual removal counts and cloud identity. Repeated operations reuse only a receipt that still recomputes correctly. Models cannot write anything in this output tree.

Only supported prose is cleaned. Automatic cleanup leaves mathematics,
citations, URLs/link targets, code, commands, quotations, AI-use statements and
source metadata intact; this does not prevent author edits to a public AI-use
statement. DOCX fields, relations, equations, images and other package parts
remain unchanged. NFKC, homoglyph rewriting and space normalization are disabled;
legitimate multilingual/emoji/directional characters and scientific invisible
operators are retained.

Explicit-operation candidates never overwrite canonical sources or gain automatic promotion. They can inform a subsequent evidence-preserving edit by the existing OpenAI writer, subject to normal revision checks. Claude source ancestry cannot be converted to OpenAI/human authorship by cleanup.

The separate [automatic hygiene contract](MANUSCRIPT-HYGIENE.md) applies to every G5 author/remediation pass. Eligible current OpenAI or human-authored prose has supported character artifacts removed before builders; original bytes and differences are retained outside the manuscript. Generated outputs and structured metadata are scanned without blind edits. Scans and protected reports remain inspectable C observations; actual scientific-integrity checks and G1/G2 topic decisions remain mandatory.

## Limits

Meaning-preserving prose revision may reduce statistical watermark signals, but neither it nor character cleaning verifies watermark absence without the applicable detector/key. Receipts retain `not_assessed` for KGW and SynthID-Text.

Image pixel regeneration, experimental-image alteration, C2PA/source stripping and media watermark removal are outside this manuscript-text integration. Public AI-use statements remain author-editable; truthful internal traceability stays protected.

Existing [reference-routing tests](../tests/test_ccfa_reference_routing.py) check
compact/full method selection, source binding and unavailable optional sources.
[Editorial integration tests](../tests/test_editorial_integration.py) and
[academic-style tests](../tests/test_academic_style.py) check retired/unknown
status and ensure legacy reports cannot supply a current pass.
[Cleanup tests](../tests/test_watermark_cleanup.py) and
[hygiene tests](../tests/test_manuscript_hygiene.py) cover actual character
removal, original preservation, scientific/code and DOCX protection, forged
receipts, changed sources, path limits and reuse. These checks do not establish
26-pattern manuscript coverage, completed semantic review, an “AI percentage”,
scientific calibration or doctoral/Q1 acceptance.
