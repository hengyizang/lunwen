# Question-scoped literature evidence and efficient reading

Use the existing authorized shared workbench and the same doctoral question.
The current writer prepares specifications during its existing stage cycle;
no additional model, paid planning loop, external workbench or desktop plugin
is required. Read docs/LITERATURE-EVIDENCE-READING.md for executable interfaces.

1. Use title/abstract/keywords to prioritize discovery, retaining direct,
   adjacent and contrary searches. Full-text claims require original method,
   result, appendix or figure evidence. A missing abstract field is unknown,
   not a research gap. Retain preprint/published source versions separately;
   citation counts never replace the version that supplied evidence.
2. For a concrete question select registered papers and prepare at most five
   explicit query_expansions with reasons about alternative terminology for
   that same question. literature_retrieve fuses BM25 routes by RRF. Mark
   known contrary/mixed papers in stances; inability to fit them requests an
   explicit narrower scope, not silent deletion. Vectors are optional existing
   source/query/model-version-bound caches. No embedding service is enabled.
3. Request literature_reading_index for stable original sentence IDs, exact
   reader lines and physical PDF pages. locate_pdf=true explicitly uses the
   cloud PDF positioner; absent/ambiguous coordinates or page labels stay
   unknown. Translations and generated explanations cannot become originals.
4. Record actual question-bound reading answers through literature_progress.
   literature_coverage distinguishes located material from attributed answers
   and semantic/human review. Reuse current exact evidence before re-reading;
   read counts, summaries and extraction do not prove coverage. Ask for missing
   method/result/appendix/figure evidence rather than repeating whole summaries.
5. Prepare program/literature-extraction.json for all selected papers and
   fields. Reuse all relevant existing card entries, preserving unknown cells.
   Bind each field to original text and its interpretation boundary. Numbers
   need exact raw token, unit, quantity, population and conditions; tables also
   need row/column labels and footnotes. Located regions remain visually and
   scientifically pending. Deterministic Decimal conversion preserves original
   values, signs, inequalities and intervals. Never use generated calculations
   or an automatically populated cell as an approved Meta-analysis input.
6. Request literature_benchmark against attributed source-bound gold anchors.
   Compare unchanged source scopes, quote integrity, missing-evidence responses,
   numeric values/units and measured retrieval time. Reconcile actual existing
   runtime costs, including cache writes/reads, embeddings, reranking, failures
   and tools; missing cost is unknown, not zero. Synthetic software acceptance
   cannot establish real reading quality or justify automatic model promotion.

Source mechanisms are independently expressed adaptations of the pinned
PaperQA2, paperai, llm-for-zotero, Beaver, OpenPaper and daily-paper-reader
references in integrations/upstreams.lock.json. PaperPilot/PaperLens inform
discovery only: DOI format or a nonempty citation list does not prove identity,
entailment, novelty or scientific strength. No upstream code is copied here.
