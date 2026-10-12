# Journal-specific disclosure without manuscript branding

The workflow does not attach an automatic “AI generated” label to every paper.
Internal source and model-use records remain internal. They are not manuscript
prose, and the internal package manifest and checklist are not journal upload
files unless the journal requests them. Natural academic editing and character
hygiene do not change actual tool use or establish an exemption from a journal
policy.

At G5 and packaging, the cloud control plane checks a current, evidence-bound
`ai_policy` inside `papers/Pxx/disclosures.json`. The author still reviews the
actual journal rule, its applicability to the actual work and the final upload
placement at the human gate. The program verifies source hashes, quotes, dates
and locations; it cannot independently authenticate a manually preserved policy
page or decide the meaning of its exceptions.

## Input contract

Keep `ai_use` as a specific English account of the actual tools, purposes and
human oversight. Existing prose accounts are accepted. A structured account is
also supported:

```json
{
  "ai_use": {
    "tools": [{"name": "Actual tool and version", "purpose": "Actual supported task performed."}],
    "human_oversight": "The named authors checked sources, methods, results and final wording."
  },
  "ai_policy": {
    "venue_id": "the-current-venue-id",
    "official_url": "https://official-publisher.example/current-policy",
    "checked_at": "a-current-timezone-aware-ISO-timestamp",
    "requirement": "required",
    "required_placement": "manuscript",
    "rationale": "Explain why this actual use requires the declared placement under this policy.",
    "evidence": {
      "path": "evidence/journal-policies/current-policy.txt",
      "sha256": "the-current-source-SHA256",
      "start_line": 1,
      "end_line": 2,
      "quote": "An exact excerpt from these preserved policy lines."
    },
    "statement": {
      "placement": "manuscript",
      "excerpt": "The actual English declaration present in the current manuscript.",
      "location": {
        "kind": "source_lines",
        "path": "manuscript/main.tex",
        "sha256": "the-current-manuscript-source-SHA256",
        "start_line": 100,
        "end_line": 102
      }
    }
  }
}
```

This is a schema example, not a completed declaration or a verified journal
policy. Replace every illustrative value with the actual work and evidence.

The policy URL must be HTTPS on an official domain declared in `venue.json`
(`official_domains`, its official scope page, publisher page or template
guidelines). A named human confirms that the domain and saved source really
belong to the selected journal. Recheck the policy within 30 days; stale,
future-dated, unresolved or mismatched policies block completion.

`requirement` is either `required` or `not_required`. A conditional publisher
rule must be resolved for the actual use with a specific rationale and current
evidence. `not_required` permits a manuscript without an AI statement; it never
permits a false internal claim that no tools were used. Empty usage, unresolved
templates and explicit denial of this AI-assisted workflow are refused.

Required policies also declare `required_placement` as `manuscript`,
`separate_upload` or `either`. The real statement must match that declared rule.

For a required manuscript statement, source-line or Word paragraph/table-cell
locations are verified through the existing canonical manuscript locator. TeX
comments, internal reviews and unrelated draft files cannot stand in for the
declaration. Rebuild hashes and locations after source edits.

If the current policy requires a separate upload, use
`placement: "separate_upload"` and a real file inside
`submission-materials/`. TeX and Word use the same source-bound locator. Plain
`.txt` or `.md` files use `kind: "text_lines"` with the current `path`, `sha256`,
`start_line` and `end_line`. The author verifies that this placement actually
satisfies the journal; a separate file cannot replace a mandatory manuscript
section merely because it is easier to upload.

## Protected report and completion boundary

`scripts/publication_disclosure.py` provides `audit`, `refresh`,
`validate_saved_report`, `review_binding` and `prompt_feedback`. Refresh requires
an authorized cloud runner. It saves the protected deterministic report at
`reports/publication-disclosure/Pxx/latest.json`, performs no model or paid
call, and never rewrites or inserts manuscript prose. G5 approval binds this
report and the current disclosure/policy/statement sources; a changed source,
policy interpretation, declaration, report or implementation requires another
review. Passing mechanical checks does not substitute for human confirmation
that the source is genuine, the policy interpretation is correct and the
usage statement is truthful.

Known Unicode cleanup does not prove statistical-watermark absence, establish
human authorship or remove a disclosure requirement. Preserve substantive
scientific uncertainty, evidence, negative results and required declarations.

Primary policy reference checked 2026-10-12: [Elsevier's official generative AI
policy for journals](https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals).
Its current manuscript policy requires disclosure for substantive writing and
organization assistance, with a declaration in the manuscript; basic spelling,
grammar and punctuation checks are exempt. This is an example of why actual
journal policy and actual use control placement. It is not the policy of every
journal or evidence that an unidentified target venue permits any specific use.
