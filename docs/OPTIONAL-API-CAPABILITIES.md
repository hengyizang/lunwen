# Optional model capabilities and safe alternatives

The production profile uses the existing CheapAI/CodeKey Actions Secrets. No
UUAPI subscription or additional key is required for the native reading routes.
Project execution and paid requests remain on the authorized cloud runner.
Every paid native reading request passes through `model_runtime.call`, the
selected route, exact-request cache, source/model receipts and shared cumulative
budget. Enabling a route never grants a new budget or a scientific gate approval.

| Capability | Production behavior | Remaining scope |
| --- | --- | --- |
| PDF extraction and page images | Existing deterministic reader; no model charge | User must have source-processing rights; encrypted or textless pages need separately authorized extraction |
| Personal Chinese PDF translation | `reader-translation`: CheapAI GPT Pro, `gpt-6.1-sol`, high; selected pages only | Reading aid; original page text and source-map hashes remain authoritative |
| Source-bound local paper Q&A | Native deterministic lexical retrieval, optional central `reader-qa`: GPT Pro Sol 6.1 high | This is a bounded native alternative, not the full PaperQA2 SDK or an exhaustive literature search |
| Conceptual image import | Authorized downloaded PNG import and source receipt remain available | Human visual review and actual AI-use disclosure remain mandatory |
| Paid conceptual image generation | Disabled, including legacy `--execute` | Current key/model catalogs provide no verified image-generation permission or metered image adapter; no automatic paid request is possible |
| Result figures and method diagrams | Existing deterministic data renderers and `research_diagrams.py` | Generated images cannot serve as measured experimental evidence |
| PaperQA2 SDK vector retrieval | Explicit literature_paperqa uses the pinned real SDK vector store with source-bound CPU vectors and the centrally metered reader-qa answer | Its autonomous agent/provider transports remain outside this controlled adapter; ToolUniverse operations that bypass the meter stay paused |

## Native source Q&A

The [reading upgrades](LITERATURE-EVIDENCE-READING.md) support optional bounded
multi-query fusion and precomputed vectors through an explicit retrieval plan.
Explicit literature_semantic now generates pinned CPU vectors/reranking without
an embedding API. The controlled literature_paperqa bridge uses the actual SDK
vector store and central metered answer; it never launches the upstream agent.
New paid answers also map every answer statement to its individual citations;
verbatim matching remains separate from semantic support.

Supply explicit authorized project-relative `.md`, UTF-8 `.txt` or unencrypted
`.pdf` sources. PDF extraction requires the optional reader dependency. No web
crawler, live embedding API, paid reranker or hidden model call is used for retrieval.
Control/private/raw directories, symlinks and paths escaping the project are
rejected. Select at most 20 files, each at most 2 MB; total extracted text is
bounded to 500,000 characters and each PDF to 100 pages. Retrieved context is
bounded to 12 blocks and 24,000 characters by default (maximum 48,000).

The question file is also project-relative. For example, on the cloud runner:

```bash
python -m scripts.paper_qa --project study \
  --question-file evidence/questions/sample-size.txt \
  --source evidence/readers/pilot.md \
  --output evidence/qa/sample-size-retrieval.json
```

The default writes a deterministic retrieval diagnostic without a model request.
Add `--execute` with a **new output filename** only when the existing cumulative
budget already authorizes the request. With `DR_OS_ROUTING_PROFILE=production`,
the model role is routed to Sol 6.1 high through the central runtime. The legacy
provider configuration remains available outside the production profile.

The cloud request's historical `settings` values (`fast`, `medium`, `high`) are
accepted only for compatibility with the earlier SDK request shape. They do not
select a different model, reasoning effort, context limit, output limit or extra
paid pass. The native production route stays Sol 6.1 high with the same bounded
defaults. Adjusting explicit source/context bounds is a separate reviewed request.

Every source has its original SHA-256. Blocks retain exact extracted text,
text hashes, source IDs and original PDF page/line locators. Sources are rehashed
before saving the result. A source with no lexical match causes abstention
without a paid request. Model output must be strict JSON with explicit
abstention and verbatim quotes whose source ID and locator match a supplied
block. Fabricated quotes, unknown anchors and unsupported uncited answers are
rejected and saved only as unusable diagnostics. There is no automatic paid
retry or switch of model after a rejected response.

Citation matching checks source identity and exact quoting; it cannot prove
that a quote entails every answer sentence. A human must check semantic support
and retrieval completeness. The output is explicitly marked as a reading
diagnostic, cannot establish novelty or exhaustive absence from the literature,
and never performs final literature exclusion or supplies verified scientific
evidence. A real source-backed research review remains a separate gated task.

## Image route boundary

An existing text-model API key does not establish image-generation availability.
The old direct image API transport is removed. Paid generation fails before
credentials or network transport are accessed, even if `--execute` is supplied.
Adding that feature later requires a verified supported model/endpoint,
explicit image pricing and permissions, central durable reservations and debit
reconciliation, and human approval of the conceptual illustration. Importing an
authorized PNG and deterministic figures/diagrams provide working alternatives
today. These availability limits are not claims about final scientific quality.
