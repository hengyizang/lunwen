# Complete CCFA Humanization Integration

The project uses the complete `ccf-humanization` skill from
[`mikubaka88/CCFA-Skills` revision f157d7ed2777b655809471873b32b9632e784cfa](https://github.com/mikubaka88/CCFA-Skills/tree/f157d7ed2777b655809471873b32b9632e784cfa/ccf-humanization),
including its full policy, bilingual repair examples, experimental discipline and
the upstream paper writer's exact nonmutating `check_prose_quality.py` checker.
Pinned originals remain under `third_party/ccfa-skills/`; source changes fail
closed. This supplements the existing Humanizer H01–H26 and anti-defensive
AD01–AD08 mechanisms, preserving both sets of individual dispositions.

## Every Task Receives the Baseline

`scripts.ccfa_humanization.prompt_contract(stage, role)` supplies the complete
three policy documents to the existing model request. Planning, literature
retrieval, criticism, experiments, figures and maintenance apply direct,
evidence-faithful communication without inventing a prose-edit pass. An already
active baseline is reused at handoffs; no recursive invocation, extra agent or
extra model call is needed. Only authorized writers edit persistent prose;
critics remain read-only. Repository cloud execution, budget, G0–G5 approval,
six-paper thesis and provenance controls retain precedence.

The policy applies different evidence boundaries to proposed mechanisms,
planned experiments and reported observations. It does not require completed
experiments merely to discuss an idea, draft from a specification or explain a
cited method. It also never converts an unexecuted plan into a reported result.

## Full Contextual Coverage

The local CFH01–CFH38 coverage IDs organize all upstream decisions for review;
they are not a claimed upstream rule count. They cover:

- the universal baseline and evidence stage;
- sentence payload, supported facts, calibrated uncertainty, empty defense and
  genuinely missing support;
- paragraph messages, actual logical connections and recurring scope;
- abstract, introduction/related work, method, experiment, discussion and
  conclusion argument responsibilities;
- openings, canonical terminology, references/antecedents, meaningful ordering,
  scientific explanation instead of execution logs, and unnecessary triads;
- selected punctuation conventions, sentence/paragraph rhythm, useful contrasts,
  precision, supported findings and source formatting;
- internal method status, material negative information, warning-only decisions,
  existing checksum/provenance requirements and a final scientific reading;
- actual full-method comparisons, intended controlled/minimal studies, labeled
  ablations, proportionate smoke checks and experiment-to-paper consistency.

The full original bilingual examples are present in each applicable contract.
They explain how to replace defensive framing with its scientific payload and
when an accurate negation, uncertainty, contrast or technical property must stay.

At G5, `disposition_contract()` uses the existing remediation-note format:
`fixed: CFH01 <contextual reason>`, `rejected: CFH01 <contextual reason>` or
`unresolved: CFH01 <contextual reason>`. `validate_dispositions(notes, stage)`
requires all 38 current IDs exactly once and a substantive reason of at least
20 characters for every item. Other Humanizer, AD and actionable-finding notes
retain their native validators. Unknown IDs, duplicates, ranges standing in for
individual items, repeated pass flags and a checklist-wide copied rationale are
rejected. Related criteria may share an actual inapplicability explanation;
unresolved records remain for the fresh independent critic and human gate.
`validate_disposition_records()` supports structured `id`, `disposition` and
`reason` fields without changing the native bundle schema. Neither adapter
claims to verify the truth of a reason or to replace source-bound semantic
review.

## Deterministic Checks and Protected Information

`audit_text()` reuses every upstream prose signal: English and Chinese defensive
framing, openings, internal engineering status, vague terminology, repeated
enumerations, uniform sentence/paragraph lengths, punctuation, clustered
capability labels and unsupported generic justifications. It masks code,
equations, quotations and citation material as upstream specifies. The original
checker's error/warning levels are retained as metadata, with every result
presented as advisory for contextual review. A match never triggers a blind
replacement.

The selected em-dash convention overrides the generic defaults; `off` removes
the numeric quota. The semicolon density signal applies only to at least 500
words of predominantly English paragraphs. Chinese character counts do not
become English word counts. Local paragraphs with three or more semicolons and
three or more contrasts remain contextual signals for both languages.

`compare_edit()` flags possible changes to numeric associations, citations,
formulae, quotations, code, disclosed assistance, negative findings and related
scientific context. Equal numeric token counts cannot conceal swapping which
method obtained which value. These conservative signatures can require review;
they cannot prove that unchanged signatures mean unchanged scientific meaning.
They never authorize random synonym spinning, withholding material adverse
results, deleting required AI-use statements or claiming detector/watermark
evasion.

## Experiments

`experiment_review()` checks supplied internal method-use records. Reported full
comparisons need full recorded identity/configuration and actual run bindings;
planned and cited methods do not require an executed checkpoint. Properly
labeled ablations preserve their full reference and changed component. An
intended minimal, fixed-budget or synthetic study retains its actual protocol
and interpretation; a debug substitute cannot become scientific evidence simply
through a new label. The existing execution, protocol, reproduction and
statistics validators remain the authority, regardless of self-declared
`confirmed` metadata.

A retained smoke check needs a changed critical path, realistic failure,
distinct signal, lower cost than substantive validation and an outcome that
changes the next action. Duplicate coverage needs a concrete reason. Smoke
success is engineering evidence and never benchmark or scientific evidence.
No checker initiates experiments or reduces an approved experiment protocol.

## Internal Reports and Freshness

`audit(project, paper_id=None)` runs only in the cloud. It writes internal
`papers/Pxx/reviews/ccfa-humanization.json` reports and their deterministic
provenance. It does not modify manuscripts. Every report binds the actual
canonical manuscript, all TeX includes, complete policy sources and checker
implementation. `validate_saved_audit()` recomputes the report and rejects stale
or altered content and missing deterministic provenance. No passing heuristic
result grants G5, human scientific approval, publication readiness or a claim
about who authored the text.

The adapter's existing provenance checks are an implemented project dependency.
The upstream preference against gratuitous manuscript hashes does not remove
them or insert them into publication prose.
