---
name: data
description: Discover, acquire, version and document source-bound research datasets without bypassing access controls.
argument-hint: <project-slug> [paper-id]
disable-model-invocation: true
---

# Data

Read the Experiment design contract and `references/research-integrity.md`. Use `data-steward` for an independent review.

For every candidate dataset:

1. Use `scripts/data_discovery.py` for bounded public metadata search when useful, then resolve the canonical provider page, version, DOI or stable identifier.
2. Verify source, version, integrity, privacy, access method and known restrictions. Licence/research-use review is optional metadata, not a pre-use gate or an extra human approval; never invent permission. Check actual redistribution restrictions before publishing data.
3. Document unit of analysis, coverage, sampling, labels, missingness, known biases, leakage routes and overlap with benchmarks or pretrained models.
4. Prefer official APIs and publisher-provided downloads. Respect terms, robots controls, authentication, rate limits and deletion requests.
5. Reject unverifiable source/version or integrity, privacy failures and access-control bypasses; unknown optional licence metadata alone does not reject a source.
6. Write a manifest conforming to `schemas/dataset-manifest.schema.json`.
7. Treat discovery licence claims as unverified optional metadata. Use `scripts/dataset_fetch.py` with the current source/version-bound manifest and recorded acquisition controls; no human licence acceptance is required. Store raw data under the ignored `data/raw` path.
8. Verify SHA-256 and preserve the exact transformation/split pipeline.

Synthetic or simulated data must be labeled as such and cannot be described as collected observations.
