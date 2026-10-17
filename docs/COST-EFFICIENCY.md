# Cost efficiency with scientific controls intact

Reviewed against main `f7548a0215edab1512ff67a9e989751518736218` on
2026-10-18 (Asia/Shanghai). These changes select no new model, reasoning effort,
gateway, paid service, scientific method or spending ceiling. Engineering checks
are not evidence of doctoral quality, scientific equivalence or journal acceptance.

## Changes and findings

| Area | Observed issue | Control |
|---|---|---|
| Default context | Historical CLI transcripts under `state/runs` could consume context and expose old preferred verdicts. | Omit operational transcripts and accounting logs, retaining scientific sources, intake constraints, paper contracts and spending authority. Explicit context plans cannot reintroduce those transcripts. |
| JSON sources | Repeated pretty-printed structures consume input. | Remove only formatting whitespace outside strings. Preserve every numeric literal, string, record boundary and the original source hash. Prose, quotations, code and equations are not paraphrased. |
| Context overflow | The legacy fallback could send partial files or omit later files. | Stop before inference when a required file or full packet exceeds its bound. Require explicit source ranges, complete constraints and full active counterevidence; do not silently compress scientific meaning. |
| Scoped evidence | A mandatory source could be selected again with another stance/reason. | Render an identical source range once, retaining all bindings, reasons and opposing stances. Partial counterevidence and stale hashes still fail. |
| Writer instructions | Every stage received long instructions for all other stages. | Retain shared constraints and every instruction applicable to the current stage. Stage contracts and independent scientific audits remain. |
| Artifact regeneration | Returning unchanged chapters could churn files and provenance. | Ask for changed artifacts only, allow a justified empty change set, and do not rewrite identical bytes or replace their authorship ancestry. G5's 34 contextual editorial dispositions remain required. |
| Search requests | Identical searches in one plan could run twice; cache lookup did not bind the requested limit. | Update the in-cycle receipt index immediately and match the exact request URL/limit, provider, query family, age and raw/normalized hashes. Identical work metadata share source-receipt IDs. Bounded metadata previews disclose omissions. |
| Citation checks | Repeated checks could fetch the same public metadata again. | The controlled `citation_audit` operation can reuse 24h hash-bound metadata; every bibliography/manuscript decision is recomputed. Changed titles, expired/corrupt/future cache records and explicit refresh cannot reuse a PASS. |
| Native PDF readers | Existence of an output alone could suppress a newly required extraction. | Reuse only an exact native-reader source, implementation, selected page scope, reader and source-map hash. Preserve stale readers and request a new output path. Never silently overwrite old source-bound evidence. |
| Model routes | A missing later route/quote could be discovered after paying the planner. | Preflight every distinct configured route and quote before the first paid role. This does not guarantee all future prompts will fit the remaining budget; per-request reservations remain mandatory. |
| Live health probes | The legacy API health `--live` path bypassed project accounting. | Require an existing project, spending authority and exact rates. Both health entry points now use the shared runtime, fresh responses and ledger; default configuration checks remain free. A blocked request is not labeled as paid. |
| Response caching | A request key did not explicitly separate stage/role; auxiliary review or health calls could replay an old response. | Cache version 4 binds stage, role, model, transport, strict identity, API version and billing identity. Validate response text hashes. Reviews and health always require fresh calls. |
| Cost observability | Ambiguous transport failures had reservations but little request-level diagnostic detail. | Record request hashes/bytes, output ceilings, cache policy and uncertain failures. Duplicate paid requests are inspection candidates, not proof of waste. Unknown charges are never certified free. |

## The recommendations already handled by programs

The existing controlled search APIs, DOI normalization, citation chaining,
dataset hashing/quality, power calculations, statistical analysis, Meta-analysis,
Lean kernel, experiment executor, scientific figure renderer and document checks
remain deterministic. They are not reassigned to LLM arithmetic or rewritten
through additional model calls. Baselines, seeds, negative results, independent
replay, statistical assumptions and human confirmations are not reduced.

Native PDF extraction remains the first route. OCR/vision is required when text
extraction is inadequate, but no paid OCR, embedding, reranker or translation
service is enabled by this change. There are no real topic/data materials here
that establish a need for one. Optional translation still requires explicit paid
authorization. Large language models are not self-hosted on the CPU runner.

## Lexical retrieval before paid semantic tools

`retrieve_evidence` is an optional controlled operation, available after G0.
It reads `program/retrieval-plan.json`:

```json
{
  "schema_version": "1.0",
  "query": "robustness falsification uncertainty",
  "limit": 8,
  "sources": [
    {"path": "literature/readers/authorized-paper.md", "sha256": "ACTUAL_CURRENT_SHA256"}
  ]
}
```

The standard-library BM25 implementation searches explicit, current source
hashes, English terms and Chinese bigrams. It records original line ranges,
excerpt hashes, the complete searched-source inventory and nonreturned counts.
An oversized quote becomes an explicit locator, never a truncated quotation.
The report is `reports/evidence-retrieval/latest.json`; the operation summary
contains only candidate locators, so it does not resend another copy of the
corpus. The report itself is not a primary source or a scientific conclusion.

Retrieval does not modify a context plan, screen out a paper or establish that
nonmatches are irrelevant. A narrower context packet needs explicit selections
and the existing constraints/full-counterevidence checks. Private files,
transcripts, previous reviews, raw datasets and secret-bearing paths are refused.
No embeddings or model calls are involved. Only consider a semantic index later
if a measured retrieval shortcoming justifies its maintenance and cost.

## Citations and public metadata

At G5 request:

```json
{"stage":"writing-and-review","action":"citation_audit","paper_id":"P01"}
```

The controller reads the canonical `manuscript/references.bib` and produces the
protected `reviews/citation-audit.json`. An optional `manual_verifications` path
must be owner-controlled `state/` input. The queue cannot invent a human name,
declare DOCX in-text mappings verified, or turn metadata into scientific claim
support. The actual bibliography/manuscript hashes are recomputed each time.
Offline mode never turns cached metadata into a live verification.

Cached metadata records have their source URL, actual retrieval time and content
hash. They are archived as non-authoritative checkpoint data rather than filling
the Git allowance reserved for authority. The source record is reusable for less
than 24 hours; use `refresh_metadata:true` after known publisher changes. Never
refresh only a report timestamp while reusing an expired verification decision.

The standalone citation CLI remains compatible and does not write a state cache
unless explicitly given `--cache-metadata`. This avoids mutation of protected
state from inside a writer/critic invocation. Use the controller for persistent
cache writes, and `--refresh-metadata` for an explicit public refresh.

## Required model roles are not redundant calls

The API stage still has five roles: Claude planning, OpenAI writing, fresh
initial criticism, OpenAI remediation, fresh final criticism. G5 editorial review
uses the existing writing/remediation passes, not new rewrite agents. Different
perspectives inside a critic are not extra paid agents or independent raters.

Do not remove a review just because the prompt or manuscript did not change.
A fresh final assessment can identify a missed problem. Conversely, unchanged
chapters need not be regenerated: the remediator can return reasoned dispositions
without a gratuitous edit. The final critic and all G0-G5 human gates still run.
Model family separation, approval, frozen experiments and manual submission are
unchanged. No independent review is fulfilled by a response-cache hit.

The zero-call `health` command is unchanged. For a deliberately billable check,
use `health --live --project PROJECT --provider PROVIDER` only within an existing
approved ceiling and explicit model quote. `model_health --execute` has the same
authority requirements. Neither starts an automatic health polling loop.

## Inspect costs without starting another model job

`python -m scripts.cost_audit --project PROJECT` writes `state/cost-audit.json`.
The API cycle also refreshes it at completion, and model usage summaries include
the diagnostics. It records cache hits, request-repeat candidates, fresh review
attempts, unresolved billing and current reservations. It never automatically
skips a call, raises a ceiling or interprets repeat requests as wasted spending.
CLI/subscription charges are explicitly outside the API ledger's measurements.

Existing safeguards already prevent an ambiguous generation POST from being
automatically retried, serialize owner/continuation jobs under the same cloud
lock, persist model-response caches in verified checkpoints, pause on external
blockers, and bound stalled/stage cycles. They are retained, not implemented a
second time. A no-progress bound is not a promise that every model call improves
the research, and no blanket savings percentage is claimed.

## Validation boundary

The existing gateway CI job also runs `scripts.cost_quality_acceptance` on a
cloud runner, with a mock transport and no provider credentials. Its receipt
checks lossless source content/hashes, preserved contrary evidence, excluded
historical verdicts, an exact writer response reuse and two fresh assessments.
The existing separate gateway acceptance still exercises a full cross-family
five-role cycle. Unit coverage adds stale/changed caches, overflowing context,
metadata/reader invalidation, changed search limits and duplicate diagnostics.

The receipt's byte counts and call counts are synthetic engineering evidence.
They are not observed project savings, validated model equivalence, successful
formal experiments or evidence that a paper meets a journal's scientific bar.
Real topic-based quality and total-cost comparisons remain necessary before
changing models or routing.

OpenAI's [prompt-caching documentation](https://developers.openai.com/api/docs/guides/prompt-caching)
(accessed 2026-10-18) distinguishes input-prefix reuse from response replay and
states that hits are not guaranteed. This patch makes no assumption about a
gateway's cache hit rate and enables no additional cache-write billing mode.
