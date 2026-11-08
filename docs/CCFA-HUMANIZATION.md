# Complete CCFA Humanization Integration

The project uses the complete `ccf-humanization` skill from
[`mikubaka88/CCFA-Skills` revision f157d7ed2777b655809471873b32b9632e784cfa](https://github.com/mikubaka88/CCFA-Skills/tree/f157d7ed2777b655809471873b32b9632e784cfa/ccf-humanization),
including its full policy, bilingual repair examples, experimental discipline and
the upstream paper writer's exact nonmutating `check_prose_quality.py` checker.
Pinned originals remain under `third_party/ccfa-skills/`; source changes fail
closed. This supplements the existing Humanizer H01–H26 and anti-defensive
AD01–AD08 mechanisms, keeping optional contextual review available.

## Every Task Receives the Baseline

`scripts.ccfa_humanization.prompt_contract(stage, role)` supplies the compact native baseline in ordinary model requests, with exact pinned source identities available for retrieval. An explicit Humanization/full-reference task loads the complete selected original bodies. Current task and submission rules remain active; absent full text is never claimed as consumed. Writers preserve evidence and uncertainty; critics remain read-only. No extra model call, report or parallel stage authority is created.

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

The full original bilingual examples are available in explicitly selected full-reference contracts.
They explain how to replace defensive framing with its scientific payload and
when an accurate negation, uncertainty, contrast or technical property must stay.

For an explicitly selected complete editorial review, `disposition_contract()` supports the existing remediation-note format:
`fixed: CFH01 <contextual reason>`, `rejected: CFH01 <contextual reason>` or
`unresolved: CFH01 <contextual reason>`. `validate_dispositions(notes, stage)`
validates only supplied optional observations, with unique current IDs and bounded
nonempty reasons. Empty and partial lists are valid. Related observations may
share an actual explanation; the parser checks format and never certifies that
the reason is scientifically sound. Unresolved records remain visible C
observations. Exhaustive CFH/H/AD tables are not required for G5 or packaging.
Native author bundles use the existing `notes` strings and
`validate_dispositions()`; no parallel structured disposition form is required.
The parser does not verify reasons or replace source-bound semantic review.

## Deterministic Checks and Protected Information

The native academic-style wrapper reuses one bounded adapter for proselint and
Harper. Tool failures are reported as errors rather than empty successful output.
Located native prose observations stay advisory. Stock-phrase density, minimum
500-word eligibility, sentence-length ratios and cadence thresholds have been
retired; the pinned upstream checker below remains optional contextual advice.
Actual suppression of adverse evidence remains an integrity finding. Author
field navigation and validation share the current repository JSON Schemas, so
optional venue planning cannot become a hidden ranking or candidate-count gate.

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

Use `scripts/revision_integrity.py --project <slug> --paper <Pxx>` for the actual
canonical manuscript and preserved revision baseline. It checks numeric
associations, citations, formulae and scientific context; unchanged signatures
do not prove scientific equivalence. Source-bound edit locations remain
available through the revision ledger. Public AI-use statements remain optional
and author-editable; truthful internal provenance remains separate.

## Experiments

Use the existing paper experiment design and `experiment-evidence-plan.json`
for actual comparison roles, configurations, splits, baselines and ablations.
`scripts/experiment_evidence.py` validates the plan and executor-bound evidence;
`scripts/experiment_runner.py` executes the approved inputs. Planning and cited
methods do not fabricate executed results. A debug or smoke run cannot become
scientific evidence through a new label or a self-declared `confirmed` field.

The unused Python helpers `compare_edit()`, `experiment_review()` and
`validate_disposition_records()` are retired. They had no workflow consumers;
their free-text signatures and self-declared method notes were separate from
these native scientific controls. Their old return formats are not replacement
contracts for the native authorities above. The 38-item guidance, full pinned
sources, Humanizer/anti-defensive observations and normal note parser remain.

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
