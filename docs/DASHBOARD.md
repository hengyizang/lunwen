# Local visual dashboard (v1.5)

The dashboard is a beginner-facing local client over the existing Doctoral
Research OS. It does not replace the G0–G5 control plane. Every mutation is
executed by the same reviewed Python scripts used by the CLI.

## Start

From WSL2 Ubuntu:

```bash
cd ~/code/lunwen
git switch main
git pull --ff-only
bash scripts/bootstrap-wsl.sh
bash scripts/start-dashboard.sh
```

Open `http://127.0.0.1:8765` if Windows does not open it automatically. Keep the
terminal open. Press `Ctrl+C` to stop the client.

The server binds only to loopback. It rejects non-local Host and Origin values,
requires a per-process CSRF token for writes, emits a restrictive Content
Security Policy, and never returns an API key in a response.

## API session

Open **API 设置** and enter:

- the exact UUAPI base URL shown by the dashboard;
- the UUAPI key;
- the exact Claude model ID for internal planning/auditing;
- the exact GPT/Codex model ID for persistent writing;
- optionally, a Tavily key for additional public web discovery.

The secret fields are not stored in Local Storage, cookies, a project, `.env`,
or Git. Blank secret fields preserve an already configured in-memory value.
Closing the dashboard process clears values entered through the page.

Run the non-billable configuration check first, then the explicitly labelled
small billable probe. Stop on a model-ID mismatch. Do not disable strict model
checking simply to hide a gateway substitution.

## Project workflow

1. Create a project and provide complete, truthful G0 constraints.
2. Wait for the live job to finish and inspect the log.
3. Read the project files and the dashboard's deterministic gate errors.
4. Use **检查闸门**. A successful check is necessary but not sufficient for
   scientific approval.
5. Add a meaningful review note and use **锁定并等待审批**.
6. Approve only after reading the exact locked version. If it needs changes,
   use **重新打开** instead.
7. Use **进入下一阶段** only after approval.

The main action card always calls the current stage from `state/run.json`; the
dashboard does not accept a user-supplied stage and therefore cannot skip a
gate.

## Broad dataset discovery

Enter several English query formulations, one per line. The client searches
the selected sources concurrently:

| Source | Coverage |
|---|---|
| DataCite | Cross-repository DOI metadata |
| Zenodo | General research deposits |
| Hugging Face | ML, language and multimodal datasets |
| OpenML | ML benchmark datasets and tasks |
| Figshare | General institutional research data |
| Dryad | Publication-linked research data |
| Harvard Dataverse | University and social-science data |
| Data.gov / CKAN | US government, agency and NASA-linked metadata |

Results are deduplicated by DOI or canonical landing URL. The displayed score
uses only query overlap, title matches, persistent identifiers and the presence
of license metadata. It is not a quality, license, novelty or JCR-readiness
score. A high-scoring dataset can still be biased, too small, leaked,
incompatible with the hypothesis, or legally unusable.

The reviewed API registry is maintained in
[`references/dataset-discovery-sources.md`](../references/dataset-discovery-sources.md).

Kaggle is intentionally shown as an optional disconnected source because it
requires separate account credentials and terms. The dashboard does not scrape
Kaggle or reuse the UUAPI key as a Kaggle credential.

Before download, create a schema-valid manifest and verify the official record,
terms, privacy, provenance, version and research fitness. The dashboard's
download checkbox is the explicit human `--accept-license` action; it does not
convert ambiguous terms into permission. Record the resulting SHA-256 before
G3 approval.

## Monitoring and judgement

The dashboard reports:

- current stage, gate and state;
- deterministic gate errors and the next legal action;
- active, successful and failed jobs with sanitized output;
- API run count and recorded input/output tokens;
- dataset-manifest and experiment-attempt counts;
- paper-by-paper completion;
- ranked discovery candidates.

It cannot truthfully decide data rights, doctoral originality, causal validity,
authorship, ethics, current JCR category evidence, or final submission fitness.
Those decisions remain named human actions. Model consensus is not scientific
validation.

## Experiment and submission controls

The experiment button delegates to `scripts/experiment_runner.py`. It will fail
unless the current plan and budget exactly match the human-approved G3 hashes.
Failed, timed-out and negative runs remain registered.

The submission button delegates to `scripts/submission_package.py`. It creates
only a local ZIP after the paper's G5 controls pass. It never opens a journal
portal, uploads a file or submits a manuscript.

## Troubleshooting

- **Port already in use:** `bash scripts/start-dashboard.sh --port 8877`
- **Browser did not open:** manually visit the printed loopback URL.
- **403 from UUAPI:** verify the exact dashboard host and documented User-Agent.
- **Model mismatch:** use the exact model ID reported by UUAPI; keep strict mode.
- **A job appears stuck:** inspect its live log. Stop the dashboard with
  `Ctrl+C` only after considering whether an experiment should finish.
- **Dashboard refresh lost the key:** this is expected after restarting the
  process; enter the key again.

The CLI remains available at all times. Never run a CLI mutation and a
dashboard mutation concurrently for the same project.
