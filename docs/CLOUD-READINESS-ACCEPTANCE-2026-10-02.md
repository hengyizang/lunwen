# Cloud readiness acceptance follow-up — 2026-10-02

This record concerns software validation for PR #57, not scientific completion of `my-phd`.

The first GitHub acceptance run failed before Docker execution because a relative project root was compared against resolved input paths. After normalizing the executor and acceptance paths, the real container run exposed a file-ownership mismatch: dropping all Linux capabilities removed the root user's ability to write runner-owned output files. Both the experiment and TeX containers now use the cloud runner's UID/GID while retaining read-only inputs, disabled networking, resource limits and dropped capabilities. The DOCX and TeX acceptance fixtures also use separate paper directories to preserve the one-canonical-manuscript rule.

Failure logs and executor receipts are retained in GitHub Actions artifacts. Successful export receipts include restored-file count, checkpoint SHA-256 and each DOCX, PDF, PNG and SVG output SHA-256. The DOCX and TeX PDFs are reopened to check expected synthetic content.

## Verified run

- [GitHub Actions run 36904033630](https://github.com/hengyizang/lunwen/actions/runs/36904033630): **success**.
- PR source commit: `b334e9e1552ddf29cc902882ccfa5a92347f1e5b`.
- GitHub-tested merge revision: `55b79ac1ca827a8bc1e58afb9289dba4e68bc39c`.
- 316 tests passed on each of Python 3.10, 3.12 and 3.13; compilation, repository validation, whitespace checks and Windows syntax also passed.
- 19 files restored byte-for-byte on the second runner; the negative result and failed attempt were retained, with no automatic retry.
- [Acceptance receipt](acceptance/cloud-pipeline-2026-10-02.json), copied from the completed consumer job's structured output. SHA-256: `3d1f83745ae006b60f6c17ca447da274d1681cc627c6d23445ff5a596a5935e8`.
- [Cloud acceptance artifact](https://github.com/hengyizang/lunwen/actions/runs/36904033630/artifacts/11182648610). ZIP SHA-256: `8d8debd929c4e79515fd8291efb1e64985fa27999bcca259d9652a901075865b`.

Only R25, R26 and R31 are marked software-acceptance verified against this scoped receipt. Paid-provider acceptance and real research requirements retain their pending statuses.

## Validation scope

The workflow runs repository unit/regression tests on Python 3.10, 3.12 and 3.13, Python compilation, repository validation, whitespace checks and the Windows installer parser. Two separate GitHub-hosted Ubuntu runners exercise the real Docker executor, preserve a synthetic negative result and intentional failed attempt, restore all fixture hashes, reject automatic retry of the failed experiment and export native DOCX, vector/raster figures and isolated TeX PDF.

These checks make no model generation calls and do not change budget authorization or any scientific gate. Credentialed literature probes, optional research-adapter smoke tests and live paid gateway validation are not part of this PR run.

## Remaining external and scientific work

The inspected `cloud-state/my-phd` records have only G0 approved; the project remains at G1. Its ledger records a CNY 300 authorized ceiling, CNY 0 spent and no outstanding reservations. The latest inspected scheduled continuation (run 36879394907) paused with `configuration_pending`. The saved status lists missing `UUAPI_API_KEY`, `UUAPI_BASE_URL`, `UUAPI_ANTHROPIC_MODEL`, `UUAPI_OPENAI_MODEL` and `DR_OS_MODEL_PRICING_JSON`. Secret values were neither read nor changed. No OpenRouter or Bocha live capability is established by these synthetic checks.

Real source screening, data-rights review, approved experiments, independent scientific review, current venue checks and human G1–G5 decisions remain required. No paper is declared complete or submitted. Recovery artifacts expire: the test artifacts last 14 days and research checkpoints use 90-day retention; real study evidence still needs reviewed durable archiving.
