---
name: package
description: Build and inspect a deterministic manual journal-upload package after the paper passes its submission-phase G5 checks and recorded automated decision. Never log into, upload to or submit through a journal portal.
---

# Package for manual submission

Read the paper's `venue.json`, disclosures, citation audit, venue-compliance report, review rounds and response matrix. Confirm `state/run.json` marks the requested paper `submission_ready`.

Run:

```bash
python3 scripts/submission_package.py --project <slug> --paper <Pxx>
```

Inspect `SUBMISSION-MANIFEST.json`, its output-provenance section, `MANUAL-CHECKLIST.md` and every included file. The packager must reject any current hash recorded as Anthropic/Claude-authored. Report missing portal-only metadata or separate-upload requirements to the human. The ZIP is a convenience bundle, not evidence that a journal accepts a single archive.

Never request portal credentials, bypass access controls, upload files, click a submission confirmation or claim that submission occurred.
