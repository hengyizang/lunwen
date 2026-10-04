# Automatic cloud recovery

The owner's instruction enables bounded engineering recovery for `my-phd`.
Research execution remains entirely on GitHub Actions; recovery uses no model
API calls and rents no compute. Existing model budget approvals and G0–G5
decisions remain authoritative.

## What happens after an error

* Git state inspection, fetch/push and installation of the exact declared
  dependency set retry transient network failures at most three times, with
  two-second and eight-second backoff. Permission errors, dependency conflicts,
  hash failures and non-fast-forward pushes stop. Every attempt has a redacted
  receipt. Experiments and model generation never use this retry wrapper.
* Completed failed research jobs trigger the recovery workflow. A 15-minute
  schedule provides a fallback; GitHub scheduling and queues can delay it.
  Checkout/setup failures may replay only if the research step was skipped.
  Already executed jobs are never replayed wholesale.
* Transient dependency setup failures before execution can resume from the
  persisted checkpoint. A fresh continuation rechecks credentials, approvals,
  budget, unresolved reservations and stage progress. All old failures and
  progress counters remain recorded.
* Recognized regressions in `cloud_runtime.prepare` and
  `manuscript_docx._python_docx` can restore their exact implementation from a
  recent revision that passed all ten required cloud checks. Imports, function
  signatures, other functions and protected controls must agree. The controller
  opens a one-file repair PR, explicitly dispatches validation without secrets,
  verifies the exact PR identity, patch, unchanged base and ten successful jobs,
  then merges and requests a fresh continuation. This is a verified rollback,
  not unrestricted model-written code modification.
* Unknown faults, missing/stale checkpoints, uncertain billing, failed formal
  experiments, human gates and exhausted progress/budget bounds pause and open
  a deduplicated GitHub issue linked to the failure. These need an inspected
  repair, evidence review or billing reconciliation before the owner resumes.

There are at most two recoveries per incident and four per UTC day. Recovery
history is stored in `cloud-state/my-phd` under `state/cloud-recovery.json`;
the original status and its hash are recorded before reset. Recovery never
deletes negative evidence, changes the frozen design, weakens validation,
approves a scientific gate or declares paper completion.

## Validation and limits

Cloud CI injects network failures, ambiguous billing, failed experiments,
malicious/untrusted events, protected-code changes and incomplete/stale CI.
Synthetic acceptance verifies software controls; it does not validate a
scientific contribution, result, paper or journal ranking.

Repository settings must allow GitHub Actions to create pull requests. If the
setting or branch rules deny creation/merge, recovery retains the pause and
reports the denial. There is no guaranteed recovery time and no promise that
all new code defects can be fixed automatically. Missing API keys, depleted
credits, upstream outages and Codex desktop/cloud service failures cannot be
repaired by changing this repository.

An owner `preflight` also dispatches a nonbillable permissions probe. It creates
and immediately closes an isolated draft PR, removes only its temporary branch,
and saves `recovery-capabilities.json`. It never merges the probe or touches
research state. If creation is denied, the receipt records the exact GitHub
error; ordinary safe infrastructure recovery still works.

To disable recovery, set `config/cloud-recovery.json` `enabled` to `false`.
The existing owner resume operation remains the escape hatch after review.
