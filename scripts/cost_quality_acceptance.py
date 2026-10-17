"""Cloud-only synthetic acceptance for lossless context and request reuse."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator, model_runtime
from scripts.ai_providers import ModelResult
from scripts.research_artifacts import write


def run(directory: Path) -> dict:
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise RuntimeError("cost-quality acceptance runs only on the approved cloud executor")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        project = root / "projects/fixture"
        source = project / "evidence/fixture.json"
        value = {"negative_result": "The registered null result contradicts the mechanism.",
                 "interval": [-0.02, 0.01], "registered_seeds": [1, 2, 3],
                 "observations": [{"unit": i, "outcome": -i / 1000, "limitations": "No causal conclusion."} for i in range(150)]}
        write(source, value)
        history = project / "state/runs/previous/critic.stdout.txt"
        history.parent.mkdir(parents=True)
        history.write_text("OLD_VERDICT_MUST_NOT_ENTER_NEW_REVIEW\n" * 2000, encoding="utf-8")
        write(project / "state/run.json", {"active_paper": "P01"})
        with patch.object(api_orchestrator, "ROOT", root):
            context = api_orchestrator.project_snapshot("fixture", stage="topic-intelligence", exclude_reviews=True)
        assert "OLD_VERDICT_MUST_NOT_ENTER_NEW_REVIEW" not in context
        assert value["negative_result"] in context
        assert hashlib.sha256(source.read_bytes()).hexdigest() in context
        rendered_source = context.split("representation=json-whitespace-compacted ---\n", 1)[1].split("\n--- END FILE ---", 1)[0]
        assert json.loads(rendered_source) == value
        observed = []

        def configuration(provider):
            return {"configured": True, "model": "fixture-model", "protocol": "openai_responses",
                    "endpoint": "https://fixture.invalid/responses"}

        def transport(provider, prompt, **kwargs):
            observed.append(kwargs)
            return ModelResult(provider, "fixture-model", "Synthetic fixture answer", {
                "input_tokens": 100, "output_tokens": 20}, f"fixture-{len(observed)}", "fixture-model",
                "openai_responses", "https://fixture.invalid/responses", "fixture", completion_status="completed")

        # The mock is the only transport; never contact the invalid host or use
        # provider credentials. Full cross-family cycles have separate gateway CI.
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(model_runtime.ai_providers, "configuration", side_effect=configuration), \
                patch.object(model_runtime.ai_providers, "call", side_effect=transport):
            def invoke(role):
                return model_runtime.call(project, run_id="fixture", stage="topic-intelligence", role=role,
                                          provider="uuapi-openai", prompt=context, max_output_tokens=100)
            first, repeated = invoke("persistent-writer"), invoke("persistent-writer")
            initial, final = invoke("independent-critic-initial"), invoke("independent-critic-final")
        assert not first.cache_hit and repeated.cache_hit
        assert not initial.cache_hit and not final.cache_hit and len(observed) == 3
        source_bytes = source.stat().st_size
        raw_bytes = source_bytes + history.stat().st_size
        result = {"schema_version": "1.0", "status": "pass", "fixture_only": True,
                  "scientific_quality_or_actual_cost_savings_verified": False,
                  "real_paid_model_calls": 0, "network_requests": 0,
                  "fixture_raw_source_and_history_bytes": raw_bytes,
                  "fixture_optimized_snapshot_bytes": len(context.encode()),
                  "fixture_scientific_source_bytes": source_bytes,
                  "fixture_compacted_scientific_source_bytes": len(rendered_source.encode()),
                  "scientific_json_values_preserved": True, "negative_evidence_preserved": True,
                  "source_hash_preserved": True, "historical_verdict_excluded": True,
                  "logical_fixture_invocations": 4, "fixture_transport_invocations": 3,
                  "exact_writer_replays": 1, "fresh_independent_assessments": 2,
                  "real_model_families_or_routing_not_evaluated": True}
    directory.mkdir(parents=True, exist_ok=True)
    write(directory / "acceptance.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.directory), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
