# Original research first

Owner preference recorded and methodological references checked: 2026-10-15.

The portfolio prefers primary original research for all configured papers.
Narrative reviews and literature-summary-only papers do not fulfill it. Types
remain unassigned until real topic/material assessment; there is no quota of
one theory paper, one review, or one paper per method. This changes no model,
reasoning effort, spending authority, gate approval or execution resource.

Meta analysis is a statistical method. Merely naming it, adding a bibliometric
plot, retitling a survey or selecting Research in a submission menu does not
establish an original contribution. Substantive secondary quantitative research
is a conditional option only when it answers a distinct new question through
an appropriate new analysis, rather than restating known summaries.

## Paper identity at G2

Create `papers/P01/research-identity.json` (and each configured paper) using
`schemas/research-identity.schema.json`. New project templates start unassigned;
existing projects need these records before G2. The read-only
`scripts/research_identity.py` validator runs at G2 through G5 and packaging.

Required fields:

- `schema_version: "1.0"`, exact `paper_id`;
- `research_kind: "primary"` or `"secondary_quantitative"`;
- `design_family`: primary empirical, computational, theoretical, case-study,
  policy or software; secondary meta-analysis, quantitative-reanalysis or
  bibliometric-hypothesis-test. A bibliometric method does not establish novelty;
- unique `methods`, truthful `reporting_description`, concrete
  `new_analysis_rationale` and `validation_plan`;
- `claim_ids`, matching the existing paper contract's independent claim IDs;
- `secondary_protocol` (null for primary work), `venue_classifications`,
  `analysis_evidence` and `reporting_statement` as described below.

G2 assesses a proposal, not completed results. The existing originality audit,
closest-work searches, paper independence, independent scientific criticism and
named human approval remain necessary. Structural completeness cannot determine
whether a question or result is scientifically novel.

## Secondary quantitative exception

`secondary_protocol` must contain concrete `question`, `input_selection`,
`data_extraction`, `comparability`, `bias_and_dependence`, `estimand`,
`analysis_method`, `uncertainty`, `robustness`, `added_knowledge` and
`cloud_execution` plans. Missing uncertainty, dependence/bias, comparability or
new-knowledge plans cannot be replaced with a method name. Inputs remain subject
to licensing, provenance, complete selection and negative-result preservation.

At G4/G5, `analysis_evidence` must contain one or more
`{attempt_id, path, sha256}` entries for exact successful executor attempts of
this paper. The current human G3 plan hash, predeclared output path, registry row,
stored run receipt and current output hash must match. Existing G4 all-attempt,
statistics, independence, preregistration and clean-room checks still apply.
This additional binding is not a substitute for substantive statistical review.

This policy **does not add a Meta-analysis executor, a supplemental-experiment
route, or a complete non-empirical G3/G4 branch**. Existing engine requirements
are retained. Do not claim end-to-end Meta/theory readiness until an appropriate
protocol and scientifically suitable execution/validation route are separately
implemented and verified. Unsupported routes remain blocked rather than filling
irrelevant experiment fields with invented evidence.

## Honest publication categories

Every G2 target needs a `venue_classifications` entry:

```json
{
  "venue_name": "Exact registered journal name",
  "article_type": "Exact official category, for example Research Article",
  "official_url": "https://actual-publisher-domain/actual-guidelines",
  "checked_at": "Actual timezone-aware check timestamp",
  "research_article_eligible": true,
  "design_eligible": true,
  "rationale": "Explain why the actual proposed study design qualifies under the preserved official policy.",
  "evidence": {
    "path": "evidence/actual-policy.txt",
    "sha256": "ACTUAL_SHA256",
    "start_line": 1,
    "end_line": 3,
    "quote": "Exact policy excerpt identifying the actual category and eligibility."
  }
}
```

This is a shape example, not a passing record or a real policy assertion. The
category must match both the paper contract and registered venue candidate.
The URL must use that candidate's official guideline/policy domain; policy checks
expire after 30 days. G5 rechecks the selected venue. Actual Review/Survey/opinion
categories do not satisfy this preference and must never be renamed. Unknown
eligibility is a blocker, not an implied exception. Hashes/quotes verify source
consistency, not webpage authenticity or meaning: the human must review source
authenticity, publisher interpretation and actual study eligibility at the gate.

At G5 `reporting_statement` supplies `{excerpt, location}` using the existing
canonical source-location contract. It must contain the actual
`reporting_description`. Meta analysis must be explicitly described as such.
Use `methods: ["meta_analysis"]` for a secondary Meta analysis; a synthesis of
one's newly conducted primary studies may instead explicitly identify
`meta_analysis_of_own_studies`. Never hide literature-derived inputs as newly
collected primary observations.

Secondary quantitative work retains the `review` scientific pre-submission
checklist for search, selection, bias, heterogeneity and synthesis even when a
publisher uses Research Article. The checklist name is an assessment route,
not the publisher category. Journal classification does not establish university
or doctoral eligibility; check the relevant institution's actual requirements.

Current official methodological/classification references:

- [PRISMA distinguishes systematic review processes from statistical Meta analysis](https://www.bmj.com/content/372/bmj.n160).
- [BMJ Research guidance includes systematic reviews and Meta analyses](https://www.bmj.com/about-bmj/resources-authors/article-types).

These are examples of terminology and policy, not approved targets or claims of
current JCR rank. No AI detector result, wording change or completed checklist
can certify originality, journal acceptance or doctoral completion.
