# Existing disclosures and submission boundaries

The workflow adds no automatic AI-generated branding, mandatory AI-use statement
or journal AI-policy compliance gate. Internal source/model-use records remain
internal and are not automatically manuscript prose or publisher upload files.
The author remains responsible for actual external authorship, rights, ethics
and submission obligations. The software never submits a manuscript.

`scripts/publication_disclosure.py` preserves any existing declaration and its
actual canonical location. Legacy `disclosures.json.ai_policy` and `ai_use`
records remain readable; the program does not demand a new policy assessment,
30-day recheck or fabricated oversight statement. An absent declaration is not
a claim that no tools were used. A present statement must remain truthful and
cannot be silently deleted or strengthened during editing.

Existing statements use the current source-bound manuscript locator or an actual
separate file in `submission-materials/`; preserve the source SHA, exact excerpt
and location. A changed canonical source requires updated mechanical bindings.
The protected report at `reports/publication-disclosure/Pxx/latest.json` records
what was checked without inserting text, asserting legal compliance or inventing
a human signature. Final B submission checks bind the unchanged actual sources;
see [workflow.md](../references/workflow.md).

Character cleanup never establishes human authorship, statistical-watermark
absence or an exemption from external obligations. Preserve scientific evidence,
negative/null/failed results and existing disclosures with their source history.
