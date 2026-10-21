# Literature discovery and reading workbench

All five native adaptations are committed under .agents/skills as well as
skills/, so fresh Codex Cloud checkouts discover them without desktop setup.
Selected actual discovery candidates enter the library through
literature_register(candidate_id,expected_leads_sha256,paper_id?,
acquisition_receipt?,manifest?,reader?). Metadata-only entries remain explicitly
metadata-only. Full-text attachments require a matching acquisition receipt and
the existing owner-approved manifest. Conference discovery defaults to the
upstream-style DBLP Search API; explicit transport:sparql remains available.
The CLI register command accepts --candidate-id and --expected-leads-sha256.
Search/itinerary accept --topic-id and --limit for scoped queries.

The project installs native adaptations of all five evil-read-arxiv skills:
start-my-day, paper-analyze, extract-paper-images, paper-search and conf-papers.
The complete pinned source directories, configuration example and README are in
third_party/evil-read-arxiv/. The native entry point is scripts/literaturectl.py.
Use the repository's cloud runner; no local research execution is required.

## Functional route

1. Discover public metadata using program/literature-plan.json. Search direct,
   adjacent and counterevidence query families; use citation chaining to inspect
   closest work. Existing providers include arXiv, Semantic Scholar, DBLP,
   OpenAlex, Crossref, Europe PMC and HAL.
2. Inspect ranked candidates, source receipts and provisional topic leads in
   program/topic-leads.json. Keywords in title/abstract, author novelty/performance
   rhetoric, recency, citation visibility and explicit interest feedback are
   explainable DISCOVERY signals. They do not establish research quality.
3. Resolve an explicit HTTPS landing page/PDF/arXiv lead. Save acquisition
   receipts, hashes, actual final URLs and failures. Raw PDF/HTML/image bytes
   stay in data/raw/literature; public access alone does not grant reuse rights.
4. After the existing owner review of an exact data/manifests/*.json, acquire
   the pinned PDF and request read_paper to create literature/readers/*.md.
   The manifest must match exact size/hash and approved cloud/redistribution
   rights. No paywall bypass or invented license is supported.
5. Add the paper/source/reader bindings to program/literature-workbench.json.
   Use paper-analyze to prepare a source-bound card request. --execute explicitly
   uses the existing budgeted OpenAI evidence-synthesis role; it does not create
   a new model choice or allowance. The approved OpenAI writer can also author
   a card from the exact passages. Claude remains read-only.
6. Extract original raster assets, vector-containing page previews or requested
   bounded crops. Index actual PDF page, matched figure/table number and caption,
   source PDF hash, method and permission state. An object index is never a
   paper figure number; unmatched labels remain unknown.
7. Build shared notes/search/graph/comparison views. Ask for a reading itinerary
   around a precise question, search a remembered example, or compare selected
   source papers' baselines/splits/metrics/ablations with source anchors.
8. Reuse current source-bound extraction and notes. Changed sources, code, scope,
   prompts, provider/model or permissions invalidate the relevant cache. Daily
   recommendation deltas preserve history; they do not create an automatic
   scheduler or silently change research interests.

## Discovery plan

A proposed scope is allowed before the doctoral question is chosen. Once a
nonempty current core question exists, the discovery question must match it.
Neither heuristic ranking nor a topic lead approves G1. Keep all six papers
within the final human-reviewed doctoral question and contribution structure.

Example (replace the question and keywords with the real proposed scope):

```json
{
  "schema_version": "1.0",
  "doctoral_question": "A specific proposed doctoral research question",
  "topic_keywords": ["method keyword", "problem keyword"],
  "exclude_keywords": [],
  "max_requests": 12,
  "cache_max_age_days": 7,
  "ranking_weights": {
    "topic_relevance": 1.0,
    "recency": 0.2,
    "citation_visibility": 0.2,
    "abstract_rhetoric": 0.1,
    "interest_feedback": 0.1
  },
  "searches": [
    {
      "provider": "arxiv",
      "query": "method keyword problem keyword",
      "query_family": "direct",
      "date_range": "2024-2026",
      "filters": {},
      "limit": 20
    },
    {
      "provider": "crossref",
      "query": "problem keyword limitation",
      "query_family": "counterevidence",
      "date_range": "2020-2026",
      "filters": {},
      "limit": 20
    }
  ],
  "conferences": [
    {"venue": "conf/icml", "year": 2026, "limit": 20, "enrich_limit": 2}
  ]
}
```

max_requests is cumulative per exact plan hash, not a fresh allowance every
cycle. Failed public requests have a cooldown. Receipts can be explicitly reused
by ID; stale/tampered records are rejected. DOI/arXiv versions and corroborated
title/author identities are deduplicated; conflicting identities are retained
for inspection. Conference enrichment never accepts title similarity alone.

Dates may be YYYY, YYYY-YYYY, ISO..ISO or structured from/to values. Structured
filters support the provider capabilities implemented in literature_evidence.
Legacy descriptive text remains a recorded declaration with an explicit
unapplied/unfiltered status, rather than pretending it constrained the query.
When a bounded response needs local filtering, report examined/dropped/unknown
records and do not claim complete provider coverage.

## Topic selection method

The skills support topic intelligence; their recommendation score is not a
topic-selection verdict. Use the existing G1 model planning/writing/audit loop
to turn source-bound leads into serious candidates:

- Preserve the author-reported problem and the exact abstract/full-text location.
- Compare closest methods, their assumptions, protocols and claimed contribution.
- Test whether a proposed gap is already answered by adjacent or contrary work.
- Propose a distinct mechanism/hypothesis and the experiment that could refute it.
- Check data rights, cloud execution, compute/time/budget and six-paper coherence.
- Produce the existing topic-shortlist, hypothesis register, novelty matrix and
  thesis mapping; retain rejected alternatives and unresolved uncertainty.

Do not choose a topic because an abstract says first/SOTA, rename a review as
original research, or infer doctoral merit from citations/conference prestige.
Literature discovery feeds the G1 evidence dossier and never grants approval.

## Shared library inputs

program/literature-workbench.json accepts schema_version 1.0 and papers:
id,title,topic_id,paper_ids (P01-P06), source {path,sha256}, optional manifest,
reader {path,sha256}, notes, card and HTTPS url. For a quarantined binary PDF,
manifest must refer to the exact owner-authorized full-text manifest. Raw text,
private/control files and unrelated reader substitutions are blocked.

Cards contain fields research_question, contributions, methods, baseline, splits,
metrics, ablations, findings, limitations and counterevidence. Missing information
stays unknown. Each item includes text, kind and evidence. Exact anchors require
path,sha256,start_line,end_line,quote; native PDF-reader anchors additionally
require actual pdf_page and current reader/map/original provenance. Model
inference and human interpretation require an inference_boundary. Located
quotes do not certify semantic support.

Typed relationships include cites, extends, supports, contradicts, compares_with,
replicates, uses_baseline, uses_dataset and shares_method. They need kind,
rationale and source evidence for both endpoints (cites needs the citing
endpoint); non-author interpretations need an inference boundary. A shared
keyword never creates a scientific edge.

## Cloud commands and operations

```bash
python -m scripts.literaturectl install
python -m scripts.literaturectl discover --project SLUG
python -m scripts.literaturectl resolve --project SLUG --url https://arxiv.org/abs/IDENTIFIER
python -m scripts.literaturectl build --project SLUG
python -m scripts.literaturectl search --project SLUG --query "remembered experimental example"
python -m scripts.literaturectl itinerary --project SLUG --question "Which protocol distinguishes the proposed mechanism?"
python -m scripts.literaturectl compare --project SLUG --paper-ids sourceA sourceB
python -m scripts.literaturectl analyze --project SLUG --paper-id sourceA
```

analyze without --execute makes no paid call. Explicit --execute still requires
current project model-spend authorization and the central meter; it cannot spend
through a web refresh, expand a budget or auto-retry a failed response.

The API writer can request these actions in program/cloud-operations.json:
literature_discover(plan), literature_resolve(url),
literature_figures(pdf,manifest,figures?), literature_analyze(paper_id,execute?),
literature_workbench(config?), literature_search(query,topic_id?,paper_id?,limit?),
literature_itinerary(question,topic_id?,paper_id?,limit?) and
literature_compare(paper_ids,question?). Queues do not approve rights or gates.

An owner can run a single non-billable operation independently of a model cycle
using cloud-job action literature with request_file under program/ and
allow_paid:false. That route forbids analyze execute:true. Use the existing
owner issue format from CLOUD-HUMAN-CONTROLS.md; do not open issues automatically
just to obtain scientific approval.

## Outputs and persistence

The [reasoning and reading-progress contract](LITERATURE-REASONING.md) extends
the shared library into five linked reading phases per source, source-bound
semantic objectives, adaptive answers, pairwise comparison conditions, nearest
work, gap hypotheses and a 20-axis experiment dossier. The existing approved
scientific writer supplies semantic decisions; deterministic code validates and
organizes them. No additional paid role or automatic scientific decision is used.

The generated HTML now has actual no-network search with topic, P01-P06 and
material filters. Metadata-only discoveries have their own category. Matching
examples, card experiment settings and captions link to actual source pages.
Reading and comparison views survive unchanged builds; changed source, objective
or progress inputs invalidate stale views. Downloaded folders must retain their
relative hierarchy and authorized source files.

Use `literaturectl request --project SLUG --request-file program/REQUEST.json`
for one nonpaid operation. It accepts literature_progress, literature_feedback
and literature_feedback_propose in addition to the existing actions. Feedback
events conform to schemas/literature-feedback.schema.json. They cover relevance,
duplicates, source accessibility, evidence sufficiency and actual experiment
usefulness; exact source/claim/run evidence is checked. Proposals retain before,
after, event IDs and affected scope. Owner-authenticated cloud requests alone
may adopt/reject with current hashes; model operations and the CLI cannot
self-approve an adoption. Adoption changes only additive topic keywords and
bounded weights, never exclusions, doctoral scope, scientific gates or budgets.

Conference discovery preserves DBLP failures and can use separately identified
Crossref/OpenAlex fallback with exact venue/year checks. A fallback result is not
DBLP coverage or complete conference enumeration. No access challenge is bypassed.

- program/topic-leads.json and reports/literature-intelligence/: discovery
  receipts, ranking components, proposed questions, recommendation history.
- evidence/literature/assets/ and figures/: acquisition/extraction manifests.
- literature/cards/: provenance-bound author reading cards.
- reports/literature-workbench/: library.json, search-index.json, graph.json,
  cards, comparison.json, itinerary.json, index.html and manifest.json.
- reports/literature-analysis/: prepared/rejected/successful analysis receipts.

The static HTML is a linked reading view; keep its project hierarchy when
opening/exporting it. The workbench does not need desktop Obsidian or a separate
Claude API subscription. Full-text PDFs under data/raw are excluded from Git
and cloud checkpoints and are rehydrated only from owner-reviewed acquisition
manifests. A missing source or revoked right blocks reuse.

A fresh reader extraction is not a human full-text read. A generated card is not
semantic verification. An original-paper image is not our experimental result.
Science gates, fresh independent audits, required disclosures and the six-paper
JCR portfolio remain unchanged.

## Installation and validation

All five upstream source trees are pinned by integrations/evil-read-arxiv.lock.json.
The cloud validation job runs the official pinned skill-installer helper to
install those trees into isolated temporary storage, verifies the repository
installation and installs the native project skills under .agents/skills/.
The upstream web service is excluded from execution: native adapters own network
boundaries, budget control, persistence and model provenance.

Validation uses adversarial source/hash/permission tests, real synthetic PDF
raster/vector/crop extraction and a static workbench acceptance demonstration.
It also executes search in actual headless Chromium and obtains the openly
licensed JOSS seaborn paper to check Figure 1 on PDF page 2, the original
sns.relplot example, source-linked search, extraction/read reuse and revoked
rights blocking. This isolated software acceptance never supplies production
owner approvals or demonstrates novelty or experimental correctness.
Public metadata availability is checked separately and preserves failures.
These checks establish engineering behavior, not novel research or model
scientific equivalence. No paid provider credentials are used in the job.
