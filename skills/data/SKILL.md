---
name: data
description: Discover, license-check, acquire, version and document public research datasets without bypassing access controls.
argument-hint: <project-slug> [paper-id]
disable-model-invocation: true
---

# Data

Read the Experiment design contract and `references/research-integrity.md`. Use `data-steward` for an independent review.

For every candidate dataset:

1. Use `scripts/data_discovery.py` for bounded public metadata search when useful, then resolve the canonical provider page, version, DOI or stable identifier.
2. Verify license, research-use permission, redistribution permission, privacy/ethics terms and access method.
3. Document unit of analysis, coverage, sampling, labels, missingness, known biases, leakage routes and overlap with benchmarks or pretrained models.
4. Prefer official APIs and publisher-provided downloads. Respect terms, robots controls, authentication, rate limits and deletion requests.
5. Reject sources whose rights or provenance cannot be established.
6. Write a manifest conforming to `schemas/dataset-manifest.schema.json`.
7. Treat discovery licenses as unverified. Use `scripts/dataset_fetch.py` only after human license acceptance. Store raw data under the ignored `data/raw` path.
8. Verify SHA-256 and preserve the exact transformation/split pipeline.

Synthetic or simulated data must be labeled as such and cannot be described as collected observations.
