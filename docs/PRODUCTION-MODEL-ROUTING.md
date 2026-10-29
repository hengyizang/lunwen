# Production model routing

Current writing-pilot evidence: [2026-10-28 results](SCIENTIFIC-WRITING-RESULTS-20261028.md).
Two CodeKey Argon contracts failed response identity validation; no Argon prose
was accepted or promoted. Eleven GPT candidates and their actual costs are
recorded; independent human writing calibration remains pending. Formal roles
below are unchanged, and shared credential isolation still applies.

The assignments below are approved baselines. The cloud runtime now applies
[dynamic task routing](DYNAMIC-MODEL-ROUTING.md) immediately before each request.
Only separately accepted alternatives can replace a baseline. Unclassified
G4/G5 work takes the critical Astra/Opus baseline; an explicit routine task
profile preserves the routine Sol/Sonnet baseline. A candidate's presence in
the registry does not establish quality or authorize testing it.

The [2026-10-21 cloud comparison](MODEL-COMPARISON-RESULTS-20261021.md) records
current task observations, gateway differences, cache/debit evidence and remaining
isolations. It preserves these baselines and does not automatically accept any
alternate group, effort or context setting.

The production cloud workflows use CheapAI and CodeKey. They do not inject or
require UUAPI credentials. Historical UUAPI adapters and receipts remain for
reproducibility; they are not a production fallback. Model selection, requested
reasoning effort and exact endpoint pricing are versioned in
`config/model-routing.json` and `config/model-pricing.json`.

| Work | Route | Requested effort |
| --- | --- | --- |
| G1 topic selection, G2 scientific architecture, G3 experiment design; critical scientific tasks at any stage | CheapAI GPT Pro / GPT-6 Astra | high |
| Intake, routine implementation, local writing, translation and bounded source Q&A | CheapAI GPT Pro / GPT-6.1 Sol | high |
| Routine read-only planning and initial independent audit | CodeKey Kiro enterprise / Claude Sonnet 5.5 | high |
| Core scientific planning/audits and every final independent audit | CodeKey Kiro enterprise / Claude Opus 5.5 | high |
| Source-bound metadata fields with exact quotes and locators | CheapAI GPT discount / GPT-5.6 Luna | medium |
| Internal engineering diagnosis, routine code review, software test proposals and environment/replay troubleshooting | CodeKey DeepSeek / DeepSeek-V4.1-Flash | high |
| Internal inspection of supplied, hashed PDF/image attachments | CodeKey Gemini / `gemini-4-argon` | high |

The approved native base ID remains `gemini-4-argon`, with high thinking;
two historical 2026-10-19 receipts returned that exact ID. The separate
`gemini-4-argon-high` diagnostic is not an equivalent alias. On 2026-10-20,
catalogs briefly advertised high only, subsequently returned empty lists,
and a high generation attempt returned HTTP503. Catalog omission and a
descriptor404 do not prove that base generation is unsupported. The current
production catalog gate remains closed when the exact requested ID is absent:
access is unconfirmed and no production call is sent. The separately authorized
base diagnostic does not waive that guard or resolve historical billing holds.
Google catalog inspection uses `/v1beta/models` with native header authentication
and normalizes only `models/`. A requested/reported identity does not attest
upstream weights, effort passthrough or scientific quality.

The five-role scientific cycle is unchanged: read-only plan, OpenAI writer,
fresh initial independent audit, OpenAI remediation, fresh final Opus audit.
Auxiliary models cannot approve evidence or human gates or become persistent
scientific authors. A model's advertised or reported identity and requested
effort do not independently attest model weights or actual reasoning quality.
The limited earlier relay acceptance is not doctoral scientific equivalence.
Luna formatting and literature exclusion have not passed acceptance, so they
are not enabled. Deterministic extraction, checks, statistics and plotting
remain first choices whenever adequate.

Explicit critical task kinds include `core-story`, `novelty`,
`critical-experiment-design`, `complex-revision`, `key-algorithm`,
`thesis-synthesis`, `scientific-interpretation` and `scientific-judgment`.
An owner cloud `cycle` request can set `task_kind` to one of these names; it
selects Astra/Opus for the existing five roles, without adding a second cycle.
Routine routes must not be used to bypass this classification for critical
conclusions or algorithms. There is no automatic paid retry, provider change or
upgrade after transport, validation or debit reconciliation failure.

## Secrets and execution

The existing keys are imported into these GitHub Actions Secrets:

* `DR_OS_CHEAPAI_GPT_PRO_KEY`
* `DR_OS_CHEAPAI_GPT_DISCOUNT_KEY`
* `DR_OS_CODEKEY_KIRO_ENTERPRISE_KEY`
* `DR_OS_CODEKEY_DEEPSEEK_KEY`
* `DR_OS_CODEKEY_GEMINI_KEY`
* `DR_OS_CODEKEY_KIMI_KEY` (Kimi candidate transport; no automatic role promotion)

Owner research and continuation workflows set `DR_OS_ROUTING_PROFILE=production`
and inject only those model keys. No official OpenAI or Anthropic key is needed
for these routes. Optional literature services keep their independent optional
credentials; credential-free discovery remains available. Native source Q&A,
translation and safe alternatives are described in
[OPTIONAL-API-CAPABILITIES.md](OPTIONAL-API-CAPABILITIES.md).

All project execution, model calls, tests and experiments run in GitHub cloud.
The production runtime rejects paid calls outside that runner or without the
mandatory remote-reservation mode; the low-level generation transport also
rejects non-cloud execution. A reservation push failure blocks the POST.
Importing configuration does not start research. The repository variable
`DR_OS_AUTOMATIC_RESEARCH_ENABLED=false` prevents the older 24-hour continuation
confirmation from unexpectedly starting paid work during this configuration
change. Setting it to `true` starts no new budget: the controller still checks
the existing owner confirmation, persisted cumulative spending authority,
unknown reservations, approved current stage and human gates. An explicitly
requested manual paid cycle also uses only that existing authority.

The earlier CNY30 relay-test allowance stays closed and separate. Its ledger is
never reset or reused for production. No implementation or readiness check
grants a CNY300 tranche, resets actual spending or advances G0–G5.

## Pricing, caching and reconciliation

Quotes are scoped to provider, HTTPS endpoint, exact model, production plan,
group and mode. The owner's relay wallet rule is numeric USD wallet units =
CNY units; this is not a market currency conversion. Domestic DeepSeek rates
start from official CNY prices. Cached reads, writes, five-minute/hour cache
creation, context brackets and output/thinking tokens are accounted separately.

CheapAI reservation quotes use the public relay pricing snapshot accessed
2026-10-19: [model pricing](https://cheapai.info/pricing). Some channel rates
diverge from official rates; these are labeled relay quotes, not represented as
official OpenAI prices. CodeKey Claude rates use the recorded official
Sonnet/Opus rate card with the owner's 0.35 multiplier; DeepSeek uses peak CNY
rates with 0.1; Argon reserves at non-promotional prices with 0.3. Review current
channel prices before changing these contracts. The conservative reservation
adds protocol/context bounds and a factor of seven; it is a hold, not a charge.

Before a production POST, an existing approved project budget and independent
read-only debit meter are required. The reservation is saved to the cloud state
branch first. After one POST, CodeKey must show exactly one additional request
and an explicit actual-cost delta; CheapAI must show exactly one new matching
debit log. Only that attributable debit settles the hold. Unknown, concurrent,
reset or unavailable meters stop subsequent work and retain the reservation.
No token estimate, missing usage field or unchanged counter is treated as zero
cost. A known debit above its hold is recorded and execution stops for review.

Exact-response cache identity includes prompt/system, stage/role, model,
reasoning effort, attachment hashes, route-policy hash, endpoint, billing
identity, quote hash and declared tool limits. Cache hits are free replay, not
independent review. Initial/final critics and endpoint probes always make fresh
requests when explicitly authorized. Native provider caching is a separate
provider billing feature and never fabricates another scientific review.

## Bounded cloud auxiliary jobs

An owner `auxiliary` cloud job uses `allow_paid=true` and a project-relative
`manifest` under `evidence/auxiliary-jobs/`. The manifest accepts only a kind,
prompt file, optional output cap, a source contract for metadata extraction, or
hashed file attachments for multimodal inspection. It cannot override provider,
model, budget or command. Supported kinds are `metadata-extraction`,
`engineering-diagnosis`, `engineering-code-review`, `engineering-test-design`,
`engineering-reproducibility`, `multimodal-inspection`, `format-conversion` and
`screening-assist`. Outputs are internal candidates for review.

The cloud entry point supports free preview before execution:

```bash
python -m scripts.auxiliary_job --project my-phd \
  --manifest evidence/auxiliary-jobs/request.json \
  --output evidence/auxiliary/new-preview.json
```

Metadata requires a nonempty bounded source/field contract. Multimodal inspection
requires real attachments, validates file signatures/MIME and SHA-256, and
refuses missing/changed/private/symlinked sources. No base64 media or credentials
are written into audit reports. Scientific review and original source files
remain authoritative.

## DeepSeek engineering support

DeepSeek has four explicit uses. General `engineering-diagnosis` remains available;
the three specialized tasks below additionally require a bounded source contract.
They are optional work items, not extra calls attached to every scientific cycle.
Use deterministic checks first. When a model is useful for routine engineering
triage, use one of these routes instead of commissioning the same initial triage
from several models. Existing OpenAI implementation and validation consume only
reviewed, relevant findings; do not automatically request a second paraphrase.

| Kind | Inputs and useful output | Acceptance boundary |
| --- | --- | --- |
| `engineering-code-review` | Routine code, requirements and existing failure logs; suspected defects with exact quotes and verification steps | OpenAI reviews and implements; actual regression checks establish software behavior |
| `engineering-test-design` | Code and stated software requirements; boundary cases, regression cases and failure-injection suggestions | No experimental hypotheses, metric selection, statistical thresholds or fabricated test results |
| `engineering-reproducibility` | Environment snapshots, dependency versions, commands and run logs; candidate explanations and replay checks | Preserve frozen plans, raw data, seeds, splits and failed runs; execution remains with the approved cloud runner |

For these three tasks, the manifest's `source_contract_file` is mandatory.
Its strict JSON shape is `{"sources":[{"source_id":"S1","locator":"supplied code snapshot, line 3","text":"return values[0]"}]}`.
Supply actual authorized excerpts, not this illustrative fixture. At most eight
sources and 48,000 total UTF-8 source bytes are accepted. Locators describe the
supplied snapshots; the model does not fetch the files or verify their origin.

For example, a cloud job manifest can select:

```json
{
  "schema_version": "1.0",
  "kind": "engineering-code-review",
  "prompt_file": "evidence/auxiliary-jobs/code-review.txt",
  "source_contract_file": "evidence/auxiliary-jobs/code-sources.json",
  "max_output_tokens": 2500
}
```

Each finding must contain a supplied source ID, exact locator, verbatim quote,
tentative observation, candidate suggestion and a verification step. Unknown
sources, invented quotes, malformed JSON, extra execution fields and missing
verification steps fail validation. An empty finding list requires abstention
and never means that code or science passed review. Source hashes enter the
request/cache identity; changed sources or task roles cannot reuse an old answer.
Invalid responses are accounted for once and never cached, retried or applied.

This makes DeepSeek useful for engineering support while preserving scientific
authority. It does not establish equivalence to Sol/Astra on scientific tasks.
Broader transfer of literature synthesis, statistical interpretation, research
design or scientific writing requires a separately authorized, task-specific
comparison on real project material, including missed defects, unsupported
claims, correction effort and actual total cost. No new paid evaluation is
started by adding these routes.

## Validation boundaries

`production-readiness.yml` uses authenticated catalog and billing-counter GET
requests only. It checks five credentials, seven advertised model IDs, readable
debit meters, exact quotes and the routing policy, then preserves a sanitized
receipt without wallet balances or billing history. It sends zero generation
requests and cannot grant spending authority. Cloud unit tests use fake
transports to verify protocols, per-role effort, reservations, meter failures,
cache isolation and source contracts. Neither check establishes real research
findings, empirical quality, scientific completion or journal acceptance.

