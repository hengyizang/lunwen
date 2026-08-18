# v1.0 completeness contract

The system is complete when the following chain is available for every paper:

1. **G0 intake** — user constraints, compute, time, geography, ethics and application goals.
2. **G1 topic intelligence** — literature discovery, current web evidence when configured, candidate comparison, doctoral Theme A, extension Theme B, rejection reasons and uncertainty.
3. **G2 architecture** — 5–6+ papers with distinct falsifiable questions, dependencies, shared assets and fallback venues; anti-salami-slicing review.
4. **G3 experiment design** — public/licensed data manifests, SHA-256, splits, leakage controls, baselines, ablations, statistics, seeds, stopping rules, negative-result policy and hard budget.
5. **G4 execution** — only the exact approved plan runs; failures are preserved; outputs and inputs are hashed; claim/evidence and reproducibility reports are required.
6. **G5 writing/review** — claim-constrained manuscript, DOI audit, venue-template compliance, two adversarial review rounds, itemized responses and disclosures.
7. **JCR/SCI guard** — before manual packaging, a human records current Clarivate JCR evidence with impact factor **> 1.0** and SCI/SCIE indexing. This is a human verification contract, not an automated claim that the portal was queried.
8. **Manual submission package** — deterministic ZIP and SHA-256 manifest; no portal login, credential collection, upload or submission confirmation.

## API-first execution

Use:

```bash
python3 scripts/api_orchestrator.py cycle my-phd topic-intelligence \
  --author-provider anthropic \
  --critic-provider openai \
  --context 'AI + robotics/mechanical engineering; no laboratory; limited GPU.' \
  --discovery-query 'AI robotics predictive maintenance mechanical systems'
```

The cycle is author → independent critic → remediation → final critic. It stops for the human gate. The model cannot approve the gate.

For later stages, repeat the cycle with the current stage name. Experiments remain local and G3-gated:

```bash
python3 scripts/experiment_runner.py --project my-phd
```

## Topic intelligence evidence

Literature metadata can be collected without a paid search provider:

```bash
python3 scripts/literature_discovery.py 'physics informed machine learning structural dynamics' --limit 30 \
  --output projects/my-phd/literature/openalex-crossref.json
```

For live job/industry/current-market evidence, configure `TAVILY_API_KEY` and run:

```bash
python3 scripts/web_research.py 'AI robotics engineer jobs Europe PhD 2026' --max-results 20
```

Search results are evidence leads. The G1/G5 human review must open primary sources and record the source and access date.

## JCR/SCI verification

After manually checking the current JCR record:

```bash
python3 scripts/jcr_verify.py \
  --paper-dir projects/my-phd/papers/P01 \
  --year 2026 \
  --impact-factor 3.8 \
  --quartile Q1 \
  --category 'Engineering, Mechanical' \
  --indexing SCIE \
  --source-url 'https://...' \
  --verified-by 'Hengyi'
```

The command refuses an impact factor of 1.0 or lower and refuses non-SCI/SCIE indexing.

Then package only through the guarded command:

```bash
python3 scripts/submission_guard.py --project my-phd --paper P01
```

This is the final deterministic threshold check. It still does not submit anything.
