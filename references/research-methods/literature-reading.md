# Question-scoped literature reading

Read the material needed for the current question and reuse valid prior work. The existing interfaces are described in `docs/LITERATURE-EVIDENCE-READING.md` and `docs/LITERATURE-COMPLETION.md`; they are available tools, not mandatory stages.

1. Use title/abstract/keywords to discover direct, adjacent and contrary work. Full-text claims need the relevant original methods, results, appendix or figure. Missing metadata is unknown, not proof of a research gap; retain preprint and published versions distinctly.
2. Use query expansion, BM25/RRF, optional vectors and reranking to find relevant passages. Their scores rank candidates, not scientific truth. Include known counterevidence and state any limits on the supplied source scope.
3. Use original sentence/page locations. Physical PDF page indices can differ from printed labels. OCR, translations and generated explanations never replace the original; unresolved positions remain unknown.
4. Record what was actually read and answered. Choose missing material that affects the question instead of repeating whole summaries or requiring every reading phase. Summaries, extraction and counts are not proof of comprehension.
5. For extracted numbers preserve the original token, unit, quantity, population, row/column labels, footnotes and conditions. Check unit semantics as well as arithmetic: exact Decimal conversion alone cannot distinguish a temperature interval from an absolute temperature. Inspect derived cells before using them as scientific evidence.
6. Benchmark retrieval or reading methods when that comparison is the task. Use the same appropriate corpus and source-backed reference judgments, preserve failures and compare actual time/cost. Small synthetic cases do not establish general reading quality.

Source mechanisms are independently adapted from pinned PaperQA2, paperai, llm-for-zotero, Beaver, OpenPaper and daily-paper-reader references in `integrations/upstreams.lock.json`; PaperPilot/PaperLens inform discovery. Preserve attribution and actual version information.

`literature_pdf`, `literature_matrix`, `literature_zotero`, `literature_roles`, `literature_comparison` and the native PaperQA2 adapter remain available. Install only needed dependencies and use supported interfaces. Retain actual failed requests and unknown charges; bounded reservations use the same cumulative budget without blocking independent affordable work. Do not invent human ratings or model authenticity from source-location checks.
