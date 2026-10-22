"""Synthetic controller receipts for isolated tests; no scientific certification."""
import os
from unittest.mock import patch

from scripts import review_receipts, scientific_scope
from scripts.research_artifacts import read, write, sha


from scripts.acceptance_scope import prepare_scope


def seal_review(project, state, *, gate="G5", run_id="fixture-review", notes=None):
    stage = review_receipts.STAGES[gate]
    paper = state.get("active_paper") if gate == "G5" else None
    identity = {"provider": "synthetic-critic-fixture", "family": "anthropic", "requested_model": "synthetic-critic-model",
                "reported_model": "synthetic-critic-model", "completion_status": "completed", "cache_hit": False,
                "request_id": "synthetic-fixture-no-model-call"}
    audit = {"verdict": "pass-with-conditions", **{f: [] for f in review_receipts.FIELDS - {"verdict"}}}
    if notes is None:
        codes = [f"H{n:02d}" for n in range(1, 27)] + [f"AD{n:02d}" for n in range(1, 9)] + [f"CFH{n:02d}" for n in range(1, 39)]
        notes = [f"rejected: {code} Synthetic fixture criterion {code} is exercised at manuscript/main.tex; no actual scientific or semantic clearance is claimed." for code in codes] if gate == "G5" else []
    key = gate + ("-" + paper if paper else "")
    with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
        for phase in ("initial", "final"):
            path = project / f"reviews/independent/{key}-{run_id}-{phase}.json"
            write(path, audit)
            review_receipts.seal_phase(project, stage=stage, run_id=run_id, phase=phase, audit_path=path,
                prompt="Synthetic source packet for isolated receipt tests only", identity=identity, writer_family="openai",
                materials=review_receipts.material_snapshot(project, stage, paper), notes=notes if phase == "final" else None)
