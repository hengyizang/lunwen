# Editorial skills and text watermark cleanup

This user-authorized integration adds all Humanizer patterns, the complete anti-defensive writing review and actual Unicode character-carrier cleanup. Models, routing, effort, budgets, G0–G5 and submission controls stay unchanged.

## Pinned sources and coverage

Exact commits, MIT licenses and LF-normalized file hashes are in `integrations/editorial-upstreams.lock.json`. Original skills are readable under `third_party/`; local adapters and scientific-preservation rules govern execution.

| Tool | Implemented | Interpretation |
|---|---|---|
| Humanizer 3.1.0 | All 26 numbered items; located pattern/structural findings, weak-alone exceptions and explicit contextual review | Complete rule coverage does not certify semantic correctness or an external detector result |
| Anti-defensive-writing | All 10 checklist items, 5 rewriting steps, 6 sentence functions and expanded paper rules, mapped to AD01–AD08 | Necessary scope, uncertainty, ethics, controls, negative results and evidence-based rebuttals stay protected |
| watermarks-remover | Actual pinned `text_unicode.clean_text` through `scripts/watermark_cleanup.py`, on bounded TXT/MD/TeX/DOCX prose candidates | Removes supported invisible character carriers; KGW/SynthID/vendor-key statistical watermark absence is not verified |

Humanizer covers binary contrasts; redundant closers/fragments; empty sayings; staged openings; imaginary objections; forced triads; repeated openings; universal dashes; stacked qualifiers; excessive hyphens; passive/missing subjects; stock vocabulary; inflated significance; vague associations; shallow participles; sales language; borrowed authority; copula avoidance; decorative bold; decorative headings; curly quotes; chatbot residue; source-limit guesses; repeated headings; document metadiscourse; reader-mismatched over-explanation.

A weak signal such as passive voice, a dash or quotation typography never establishes AI authorship. Scientific uncertainty or a valid negative statement cannot be strengthened or removed to satisfy a style preference. Unavailable Word-format checks explicitly remain review-required.

## Existing two-pass workflow

API and Codex orchestration receive compact full-skill contracts at G5, reusing the existing initial author and remediation calls. No extra model/detector API or repeated paid rewrite loop is introduced. The added context still consumes tokens within the existing budget.

The controller saves separate initial/final academic-audit snapshots and hashes. Final remediation requires one substantive `fixed:`, `rejected:` or `unresolved:` disposition per H01–H26 and AD01–AD08. An intentional scientific exception needs a reasoned retention. Recording the writer's judgement is not independent scientific verification.

The protected academic audit contains both complete reviews. G5 recomputes them against current manuscript and rule hashes. A partial/stale coverage report cannot pass merely by setting a boolean. Existing scientific editing, human revision authorization, exact revision ledger, citation/claim checks, English-language requirements and human approval remain mandatory.

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

Only supported prose is cleaned. Mathematics, citations, URLs/link targets, code, commands, quoted text, AI disclosure and source metadata are protected. DOCX fields, relations, equations, images and other package parts remain unchanged. NFKC, homoglyph rewriting and space normalization are disabled; legitimate multilingual/emoji/directional characters and scientific invisible operators are retained.

Candidates never overwrite canonical sources or gain automatic promotion. They can inform a subsequent evidence-preserving edit by the existing OpenAI writer, subject to normal revision checks. Claude source ancestry cannot be converted to OpenAI/human authorship by cleanup.

## Limits

Meaning-preserving prose revision may reduce statistical watermark signals, but neither it nor character cleaning verifies watermark absence without the applicable detector/key. Receipts retain `not_assessed` for KGW and SynthID-Text.

Image pixel regeneration, experimental-image alteration, C2PA/source stripping and media watermark removal are outside this manuscript-text integration. Required AI disclosure and internal traceability remain intact.

Cloud regressions cover all 26 Humanizer items, legal scientific exceptions, anti-defensive source coverage, real character removal, scientific/code protection, genuine DOCX preservation, forged receipts, source changes, path limits, writer protections and operation reuse. These are engineering checks, not an “AI percentage”, scientific calibration or doctoral/Q1 acceptance guarantee.

