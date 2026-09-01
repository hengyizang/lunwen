---
name: experiment
description: Design or execute reproducible experiments with baselines, ablations, statistics, compute budgets and failure logging.
argument-hint: <project-slug> <design|run> [paper-id]
disable-model-invocation: true
---

# Experiment

Read the relevant G3 or G4 contract and `references/research-integrity.md`.

For `design`:

- delegate an independent plan to `experiment-designer`;
- state hypotheses, estimands, baselines, ablations, datasets, splits, leakage controls, metrics, uncertainty, seeds, stopping rules and falsification conditions;
- distinguish confirmatory and exploratory analyses;
- estimate wall time, storage, API/cloud cost and a hard stop;
- create a minimal pilot before expensive runs;
- stop at G3.

For `run`:

- require recorded G3 approval;
- execute only the hash-locked plan through `scripts/experiment_runner.py`;
- log every run, including failures and negative results;
- capture environment, code revision, data hashes, seed, command, runtime, cost and output hashes;
- ask `statistical-auditor` and a model family different from the Codex/OpenAI writer to independently inspect leakage, inference, robustness and reproducibility;
- populate the claim-evidence matrix before conclusions;
- stop at G4.

Never fill missing outputs with plausible numbers.
