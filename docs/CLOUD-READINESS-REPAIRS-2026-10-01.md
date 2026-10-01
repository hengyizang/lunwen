# Cloud readiness repairs, 2026-10-01

This change addresses the reproducible failures in `CODE-READINESS-AUDIT-2026-10-01.md`. It changes software capabilities, not the scientific status of `my-phd`. The six real papers have not been completed by these tests.

| Audit gap | Repair | Verification |
|---|---|---|
| An API writer could write experiment facts | Registry, run logs, results, declared outputs and controlled acquisition/source records are writer-protected; Docker project mount is read-only with only declared output files writable | Boundary regressions and real Docker acceptance fixture |
| Ambiguous generation retries could undercount charges | Exactly one generation POST; unsettled reservations block further paid calls; push reservation before transport | Timeout/non-JSON and durable-reservation failure tests |
| Continuation only drafted plans | Controlled stage dispatcher for actual literature search, licensed acquisition, approved Docker runs, data quality, power and export operations | Stage tests plus two-runner cloud pipeline |
| File whitelist lost executable inputs and binary evidence | Git for small sources/control; 90-day hash-verified Actions checkpoint for results, large/binary files and API audit/cache; authorized raw rehydration | Exact-byte restoration, corrupt/missing archive fail-closed and fresh-runner acceptance |
| Metadata search did not create G1 evidence | Controlled literature receipts, family/query cache and bounded provider fallbacks | No-receipt/no-paid-call and failed-provider batching tests |
| Real runtime lacked figure/reader/statistics/export tools | Declared cloud dependency groups and pinned isolated TeX image, native DOCX and deterministic figure exports | Actual GitHub runtime, DOCX, SVG/PDF/PNG and PDF text acceptance |
| Direction ranking lacked dated employment/PhD evidence | Primary-source collector, eligibility/salary evidence, deduplication, separate competition factors, fixed weights and sensitivity; optional metered web search | Source freshness, counts, salary missingness and evidence-bound scoring regressions |
| Continuous work could repeatedly spend on unresolved inputs | Two stalled paid cycles / six paid repair cycles per stage and paper; typed external blockers; exact-status-hash owner repair resume | Progress, external input and authority-preserving resume regressions |
| Requirements matrix claimed completion from file existence | Schema v2 separates code implementation, bound tests, real acceptance and research completion; verified claims need a scoped hash-bound workflow receipt | Negative verification-claim test and repository validator |
| Optional tools were conflated with production readiness | OpenRouter zero-credit and Bocha current-policy metadata triage are callable but optional; every lead retained. PaperQA2/arbitrary ToolUniverse paid SDKs remain disabled pending metering | Fixed-label, zero-cost-key, source receipt and no-retry tests; live credentials still required |

## Owner-only control jobs

Use the existing structured owner-created `[research-cloud]` issue envelope. New non-billable actions:

```json
{"schema_version":"1.0","action":"authorize_data","project":"my-phd","actor":"Hengyi Zang","allow_paid":false,"manifest":"data/manifests/example.json","expected_sha256":"EXACT_REVIEWED_MANIFEST_SHA256"}
```

```json
{"schema_version":"1.0","action":"resume","project":"my-phd","actor":"Hengyi Zang","allow_paid":false,"expected_sha256":"EXACT_REVIEWED_CONTINUATION_STATUS_SHA256","repair_note":"Describe the inspected cause and concrete repair."}
```

These examples intentionally contain invalid placeholder hashes. Replace them only after reviewing the actual artifact. Resume resets bounded repair counters/failure status, preserves a history, and never grants spending or G0–G5 approval. Configuration, budget, data rights and all scientific gates are rechecked next time. New external human input can unblock a paused stage automatically when its protected hash changes.

## Configuration and limits

Required for the paid author/critic chain: repository secret `UUAPI_API_KEY`; variables `UUAPI_BASE_URL`, `UUAPI_OPENAI_MODEL`, `UUAPI_ANTHROPIC_MODEL`, `DR_OS_MODEL_PRICING_JSON` with exact current CNY prices. The existing CNY 300 standing authorization is reused; no per-call confirmation is added. Next tranche boundaries remain 600/900/etc. Credentials must never be pasted into issues or committed.

Optional: `OPENALEX_API_KEY`, literature contact email, other public-source keys. Optional Tavily uses `TAVILY_API_KEY` and `DR_OS_TAVILY_CREDIT_CNY`, one basic search credit reserved against the same cumulative cap; unknown usage blocks subsequent paid calls. Optional Jev uses a dedicated OpenRouter zero-credit key with BYOK included in its cap, or `BOCHA_JEV_API_KEY` plus the owner's current-date `BOCHA_JEV_FREE_POLICY_CHECKED_ON`. Bocha's policy claim is not a billing receipt. No configured provider is advertised as live-tested without a live receipt.

Small checkpoint files are limited to 2 MB each and 14 MB total in Git. Other supported evidence is limited to 512 MB per archive. Missing/expired/corrupt artifacts block resumption; they cannot be replaced with a smaller incomplete checkpoint. Identical idle checkpoints reuse the previous archive, refreshing before 60 days while it remains available. Ninety-day Actions retention is recovery storage, not a permanent publication archive; export real study evidence to a reviewed durable repository before expiration. Unknown file types require an explicit storage plan.

The cloud has no dependency on the user's local hardware, WSL or physical laboratory. Heavy GPU work or proprietary/nonredistributable data needs an explicit cloud/storage plan. PaperQA2 and arbitrary ToolUniverse provider calls remain optional and blocked where cost cannot be counted; the controlled core workflow does not require them. The October 7 goal never relaxes novelty, doctoral depth, originality, real experiments, current JCR checks or human review.

## Acceptance evidence

`validate.yml` now has a real Docker producer and a separate fresh-runner restore/export job on pull requests. Fixtures are labeled synthetic, live outside `projects/my-phd`, make no model API calls, and cannot create a research approval. A green fixture tests the software path only. Review the exact commit's workflow and its `cloud-pipeline-acceptance` artifact before calling the cross-runner repair verified.
