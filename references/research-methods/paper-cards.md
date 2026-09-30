# Read a paper before deriving a candidate topic

Method sources: nature-skills, kdense-topic-methods.

Use an authorized PDF, publisher HTML or existing page-anchored reader. Record
whether the supplied scope is full_text, abstract, excerpt or metadata. A
filename, DOI, successful extraction or source-map registration does not prove
full-text reading. Preserve the reader's stable block IDs, exact source hashes,
PDF page indices, formulas, tables and figure references. OCR failure never
licenses invented page numbers or missing content.

Write an optional evidence/paper-cards/<paper-id>.json using
schemas/paper-card.schema.json. Record paper_id, research_question,
claimed_contribution, source_scope, methods_assessed, experiments_assessed,
claim_evidence and candidate_ideas. Every claim_evidence item needs claim,
boundary, attribution (author_statement or agent_analysis) and an anchor.
Keep methods_assessed=false and experiments_assessed=false for partial sources;
state which questions are not assessable. Record methods, assumptions,
baselines, ablations, metrics, every main figure/table and limitations when the
actual source supports them.

Every candidate idea must be triggered by a located assumption, limitation,
contradiction or unexplained result. Apply all six idea checks: traceable source,
falsifiable hypothesis, exact change from prior work, controlled validation,
at least two failure reasons, and novelty language pending prior-art search.
Use the hypothesis-register field contract for candidate_ideas. Reject generic
requests to improve efficiency or use a larger model without a discriminating
scientific prediction.

Use scripts/research_candidates.py paper-card to audit the card. The card and
translation are reading aids. Promote a located observation to the established
citation/fact ledgers only after original-source verification. Keep external
field-history checks separate from the paper's own related-work narrative.
Do not treat a card's candidate idea as a proved original contribution.

For full_text cards, require primary_source (path and sha256) and scope_record
(path and sha256) pointing to a current protected record under
evidence/source-scopes/. Only a named human's actual source-scope confirmation
through scripts/source_scope.py can create that record. It confirms supplied
material scope, never human full-text reading or semantic verification.
Without it return source_scope_unconfirmed; keep partial scope assessments
false. Anchor full-text observations to the confirmed primary file.
