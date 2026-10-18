# Cache billing and reuse

Cache costs use the existing route-bound quote, authorization, reservation and
usage ledger. No separate budget or response store is introduced. Prices below
are official API list prices as checked on 2026-10-18, per million tokens;
gateway settlement still needs the exact account/group quote in CNY.

## Price components

| Standard model | Ordinary input | Cache read | Cache write | Output |
|---|---:|---:|---:|---:|
| GPT-6.1 Sol | $2 | $0.10 | $2.50, 30m | $10 |
| GPT-6 Astra | $10 | $1 | $12.50, 30m | $50 |
| GPT-6 Luna | $0.10 | $0.01 | $0.125, 30m | $0.50 |
| Claude Sonnet 5.5 | $2 | $0.10 | $2.50 / $4, 5m / 1h | $10 |
| Claude Opus 5.5 | $4 | $0.20 | $5 / $8, 5m / 1h | $20 |
| Claude Fable 5.1 | $10 | $0.25 | $12.50 / $20, 5m / 1h | $50 |
| Kimi K3, domestic CNY | CNY20 | CNY2 | CNY20 / CNY40, 5m / 1h | CNY100 |

Sources: official [Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing),
[Kimi pricing](https://platform.kimi.com/) and
[Kimi cache pricing](https://www.kimi.com/academy/best-practices-for-context-caching).
These rows do not activate candidate families. Apply the selected model's
context tier and service tier before the user's channel multiplier; never use a
short-context list price for an over-threshold request.

Input classes are disjoint. A written token uses the write rate in place of
ordinary input; a hit uses the read rate without another creation charge.
Output totals already include reported reasoning tokens. Request cost is
ordinary input + cache reads + cache writes by lifetime + total output + any
separately authorized tool or storage charge, each multiplied by its own rate.

## Quote and receipt contract

Schema `2.0` retains its four required base rates. The optional pair
`cache_write_5m_per_million`, `cache_write_1h_per_million` must be supplied
together, as finite non-negative CNY values, at the top level or within context
brackets. The generic `cache_write_per_million` prices unclassified writes,
including OpenAI's single-lifetime writes. The TTL pair requires the version 2
schema; legacy model-only maps reject these fields rather than ignoring them.

* OpenAI Responses: `input_tokens_details.cache_write_tokens` is part of total
  `input_tokens`. Chat Completions equivalents use `prompt_tokens_details`.
  Ordinary input is total input minus cached reads minus cache writes.
* Anthropic Messages: `input_tokens` is ordinary input. Read and creation
  counters are separate. Creation's `ephemeral_5m_input_tokens` and
  `ephemeral_1h_input_tokens` must sum to `cache_creation_input_tokens`.
* Gateway aliases must agree when supplied together. The ledger records total
  writes, both TTL counts and unclassified writes; it never adds an alias twice.
* A nonzero TTL count needs that exact TTL price. A quote with different TTL
  prices needs a complete TTL receipt to settle unclassified writes. Missing,
  malformed or inconsistent receipts keep the reservation, preserve the raw
  usage and prevent another paid attempt or response-cache reuse pending
  reconciliation. Nullable creation metadata is accepted when there are no
  writes. No missing price is silently replaced with zero.

Request reservations cover the largest quoted ordinary/read/write rate across
all context tiers and both TTLs, plus the output ceiling and bounded tool fees.
They assume no cache discount. Actual receipts determine settlement.

Official usage definitions: [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
and [Claude prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).

## Reuse policy

Put stable original evidence, the common doctoral question, frozen protocols
and role instructions before changing task material. Keep the latest results
and contradictory evidence available. Version changes invalidate the prefix;
never preserve a hit by withholding current evidence. Account/group/model,
region and relevant inference settings can prevent reuse. Marketing claims of
high cache use do not establish a hit rate.

OpenAI GPT-5.6 and later use 30m retention and support explicit breakpoints.
Use explicit writes for genuinely reusable prefixes when the selected gateway
supports them; avoid repeatedly writing a changing tail. No speculative warm-up
request is authorized by this document. Claude's 5m cache suits close follow-up;
1h suits longer gaps with enough reuse. For Sonnet/Opus 5.5, one subsequent full
read repays a 5m write premium; a 1h write requires two. This comparison covers
the shared prefix only, with unchanged output and no additional misses.

Gemini 4 Argon supports implicit caching, not explicit cache objects. Do not
borrow explicit cache-storage fees from earlier Gemini models or assume any
provider's cache TTL or hit rate applies to another.
[Gemini cache support](https://ai.google.dev/gemini-api/docs/caching).

Provider prefix caching reuses input processing while generating a new answer.
It does not replace the required fresh initial/final independent reviews with
an old response. The existing response-cache freshness rules, model-family
separation, human gates and cloud-only experiment controls remain in force.

## Validation scope

`tests/test_conditional_billing.py` exercises synthetic provider receipts,
write-token aliases, mixed lifetimes, context boundaries, malformed usage,
budget reservations and retry blocking. Run it through the repository's cloud
CI. No live gateway calls, scientific experiments, cache-hit measurements or
model quality claims follow from these checks.
