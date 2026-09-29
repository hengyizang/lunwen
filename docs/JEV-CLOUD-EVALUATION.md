# Jev-class cloud services: limited research-workflow trial

Status: proposal, 2026-09-29. No provider has been enabled and no model call or spending approval is implied. This record concerns the six-paper `my-phd` sprint ending 2026-10-07 (Asia/Shanghai).

## Decision

Use a decision model only to **prioritize a review queue of public literature or dataset metadata** after the provider contract and a small labeled trial pass. Keep all retrieved records available for ordinary review. Do not let a classifier discard a source, declare novelty, judge doctoral depth, verify a license, choose the doctoral direction, approve a scientific gate, write manuscript content, or act as the independent model-family critic. Exact source provenance, human scientific review, and the G0–G5 gates remain authoritative.

| Candidate | What the accessible first-party material establishes | Decision for this sprint |
|---|---|---|
| Bocha Jev (`bocha-jev-v1`) | The public playground advertises a decision engine and links to API documentation and an installable agent skill. The linked API document was not accessible during this review; the public page does not establish a production free allowance, rate limit, retention policy, exact API response, or billing receipt. | Possible **bounded-choice metadata triage** trial once the API contract, account terms, and actual zero-cost allowance are verified. Do not install the remote skill or send unpublished research material as a shortcut. |
| OpenRouter TypeSafe Jev Router (`typesafe/jev-router`) | Its listing describes a **chat model router** that chooses another model and reasoning effort, and advertises zero prompt/completion token price for the router listing. It is not the typed Choice/Score/Noul decision endpoint. | Exclude from the manuscript writer, Claude planner/critic, scientific gates, and current paid cycle. It can change the actual model family and complicate identity, independence, provider-policy, and cost accounting. Trial only with public test prompts if the full call cost, actual serving model, and account availability can be checked. |
| TypeSafe Jev 1.13 (`typesafe/jev-1.13`) | OpenRouter lists typed decisions through its Decisions API at USD 0.042 per million input tokens and USD 0 output. | Optional comparison after a CNY spending tranche is approved and exact provider pricing is entered in the ledger. It is **not free** at the listed input rate. |
| OpenRouter Free Models Router (`openrouter/free`) | OpenRouter says it selects among free models and that the selected model appears in the response. It is random free-model routing, not the Jev decision model. | Optional zero-price comparison for public test metadata; not a scientific author or reviewer. |

The zero price advertised for `typesafe/jev-router` does not by itself establish the final bill for every downstream completion. Unlike OpenRouter's separately documented Auto Router, the accessible Jev Router page does not spell out a selected-model billing rule. Treat end-to-end cost as **unverified** until a test response, generation record, and account balance agree. Do not assume the generic Auto Router rule is a contract for Jev Router. OpenRouter documents a generation record with the actual model and `total_cost`, and an opt-in router metadata field for provider/model attempts. Confirm those fields work for this specific route before adoption.

## Trial contract

1. First record the provider's dated API reference, free quota or exact charge, response model identity, failure behavior, retention/training terms, and account eligibility. Never place keys in an issue, commit, log, or prompt. Use a GitHub Actions secret only after the above is verified. No user workstation is part of execution.
2. Keep the approved model API ceiling at **CNY 0** unless the owner records the first cumulative **CNY 300** tranche. A zero-price claim is not spending authority. Stop before any call whose maximum charge cannot be bounded or reconciled. The CNY 600, 900, ... increases need their own approvals; individual calls inside unused approved capacity do not.
3. Run an isolated, non-persistent public-metadata trial (30–50 researcher-labeled titles/abstracts or dataset descriptions). Compare the bounded labels `prioritize`, `ordinary_review`, and `uncertain` with a deterministic baseline. Record all cases, disagreements, latency, request IDs, actual serving model, and final cost; never filter out an `ordinary_review` or `uncertain` record. A model-reported confidence is not a measured error rate. No private draft, restricted data, unpublished hypothesis, or author identity goes to an unverified endpoint.
4. If a candidate fails to return exact serving-model identity, auditable cost, and an allowed provider/data policy, stop the trial. Do not silently fall back to another model or treat a routed OpenAI-family response as an independent Claude-family critique. Any production adapter must be opt-in, bounded, disabled by default, and outside G0–G5 approval decisions.
5. Reassess the trial only if it speeds evidence review without delaying the dated G0 direction decision, cloud-only feasibility checks, six distinct paper designs, or the 2026-10-07 submission-package target. It cannot supply missing experiments or raise the probability that unsupported papers pass their gates.

## Current blockers independent of Jev

The latest inspected cloud acceptance run (`36436741307`, 2026-09-28) passed Crossref, Europe PMC, DBLP, HAL, and OpenCitations. OpenAlex returned HTTP 429 with no `OPENALEX_API_KEY` configured, and arXiv returned HTTP 406. These are recorded provider failures; a Jev classifier cannot stand in for literature retrieval. The current G0 proposal is still draft PR #36 and the project has no approved scientific direction or six completed studies.

## Sources checked 2026-09-29

- [Bocha Jev public playground](https://jev.bocha.cn/) and the API-document link on that page (the linked Feishu document required sign-in during this review).
- [OpenRouter Jev Router model listing](https://openrouter.ai/typesafe/jev-router).
- [OpenRouter Jev 1.13 model listing](https://openrouter.ai/typesafe/jev-1.13) and [Jev tutorial](https://openrouter.ai/blog/tutorials/how-to-use-jev/).
- [OpenRouter Free Models Router documentation](https://openrouter.ai/docs/guides/routing/routers/free-router), [Router Metadata](https://openrouter.ai/docs/guides/features/router-metadata), [Generation record API](https://openrouter.ai/docs/api/api-reference/generations/get-generation), and [ZDR policy](https://openrouter.ai/docs/guides/features/zdr).
- [Cloud acceptance run](https://github.com/hengyizang/lunwen/actions/runs/36436741307), [G0 draft PR #36](https://github.com/hengyizang/lunwen/pull/36), and the repository's [direction ranking contract](../references/direction-ranking.md).
