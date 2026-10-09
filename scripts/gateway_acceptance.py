"""Cloud software acceptance: real five-role orchestration, simulated HTTP only.

Fixtures never contact a provider, modify my-phd, or establish scientific facts.
Budget reservations are pushed to an isolated bare Git remote before each
simulated HTTP request, through the production checkpoint implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator, cloud_checkpoint, model_runtime, model_spend

ROOT = Path(__file__).resolve().parents[1]
SLUG = "gateway-fixture"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(directory: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=directory, check=True,
                          capture_output=True, text=True).stdout


class Response:
    def __init__(self, value: dict):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.value).encode()


def response_texts() -> list[str]:
    semantic_plan = json.dumps(
        {
            "schema_version": "1.0",
            "stage": "topic-intelligence",
            "objectives": ["compare candidates"],
            "artifact_specs": [],
            "evidence_requirements": [],
            "figure_specs": [],
            "risks": [],
            "open_questions": [],
        }
    )
    writer_bundle = json.dumps(
        {
            "schema_version": "1.0",
            "stage": "topic-intelligence",
            "artifacts": [
                {"path": "program/topic.md", "content": "draft"}
            ],
            "notes": [],
        }
    )
    initial_audit = json.dumps(
        {
            "verdict": "revise",
            "fatal_findings": [],
            "major_findings": ["missing comparison"],
            "minor_findings": [],
            "missing_evidence": [],
            "remediation_steps": ["add comparison"],
            "uncertainty": [],
        }
    )
    remediation = json.dumps(
        {
            "schema_version": "1.0",
            "stage": "topic-intelligence",
            "artifacts": [
                {"path": "program/topic.md", "content": "revised"}
            ],
            "notes": ["fixed: added the requested comparison"],
        }
    )
    final_audit = json.dumps(
        {
            "verdict": "pass-with-conditions",
            "fatal_findings": [],
            "major_findings": [],
            "minor_findings": ["human verification remains"],
            "missing_evidence": [],
            "remediation_steps": [],
            "uncertainty": ["external facts remain provisional"],
        }
    )
    return [semantic_plan, writer_bundle, initial_audit, remediation, final_audit]


def run_case(directory: Path, *, separate: bool, protocol: str,
             token_field: str = "max_completion_tokens") -> dict:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gateway-acceptance-") as temporary:
        root = Path(temporary)
        project = root / "projects" / SLUG
        state = {"stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work",
                 "active_paper": "P01", "approved_gates": ["G0"],
                 "fixture_only": True, "scientific_completion_verified": False}
        write(project / "state/run.json", state)
        (root / "config").mkdir()
        shutil.copyfile(ROOT / "config/stages.json", root / "config/stages.json")
        model_spend.write(project, model_spend.initial())
        model_spend.grant(project, new_ceiling_cny=300, actor="Synthetic fixture owner", run_id="fixture-grant")
        authority_before = model_spend.read(project)["authorization_events"]
        state_before = (project / "state/run.json").read_bytes()
        remote, checkout = root / "remote.git", root / "billing"
        remote.mkdir()
        checkout.mkdir()
        git(remote, "init", "--bare")
        git(checkout, "init")
        (checkout / "README.md").write_text("Isolated billing fixture.\n", encoding="utf-8")
        git(checkout, "add", "README.md")
        git(checkout, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-m", "Isolated fixture")
        git(checkout, "remote", "add", "origin", str(remote))
        env = {
            "UUAPI_OPENAI_MODEL": "gpt-fixture", "UUAPI_ANTHROPIC_MODEL": "claude-fixture",
            "UUAPI_OPENAI_PROTOCOL": protocol, "UUAPI_OPENAI_CHAT_TOKEN_FIELD": token_field,
            "UUAPI_STRICT_MODEL_ID": "true", "DR_OS_REQUIRE_MODEL_AUTH": "1",
            "DR_OS_REQUIRE_REMOTE_RESERVATION": "1", "GITHUB_ACTIONS": "true",
            "DR_OS_STATE_WORKTREE": str(checkout), "DR_OS_STATE_BRANCH": f"cloud-state/{SLUG}",
            "DR_OS_MODEL_PRICING_JSON": json.dumps({
                model: {"input_per_million": 2, "output_per_million": 10}
                for model in ("gpt-fixture", "claude-fixture")}),
        }
        if separate:
            for family in ("OPENAI", "ANTHROPIC"):
                env[f"UUAPI_{family}_API_KEY"] = f"fixture-{family.lower()}-key"
                env[f"UUAPI_{family}_BASE_URL"] = f"https://{family.lower()}.example.invalid/proxy/v1"
        else:
            env.update(UUAPI_API_KEY="fixture-shared-key", UUAPI_BASE_URL="https://shared.example.invalid/v1")
        requests = []
        texts = response_texts()

        def transport(request, timeout=0):
            index = len(requests)
            assert index < 5, "unexpected extra/retried request"
            # Inspect the actual remote, not just an in-process reserve mock.
            remote_control = json.loads(git(remote, "show",
                f"refs/heads/cloud-state/{SLUG}:projects/{SLUG}/state/model-spend-control.json"))
            assert len(remote_control["reservations"]) == 1
            assert remote_control["authorization_events"] == authority_before
            assert abs(remote_control["spent_cny"] - index * 0.00044) < 1e-8
            payload = json.loads(request.data)
            anthropic = index in (0, 2, 4)
            family = "anthropic" if anthropic else "openai"
            expected_model = "claude-fixture" if anthropic else "gpt-fixture"
            suffix = "messages" if anthropic else "chat/completions" if protocol == "chat_completions" else "responses"
            base = f"https://{family}.example.invalid/proxy" if separate else "https://shared.example.invalid"
            assert request.full_url == base + "/v1/" + suffix
            assert request.get_method() == "POST" and payload["model"] == expected_model
            key = f"fixture-{family}-key" if separate else "fixture-shared-key"
            headers = {k.lower(): v for k, v in request.header_items()}
            assert headers["authorization"] == "Bearer " + key
            if anthropic:
                assert headers["x-api-key"] == key and payload["max_tokens"] == 4000
            else:
                field = token_field if protocol == "chat_completions" else "max_output_tokens"
                assert payload[field] == 12000
            requests.append({"index": index, "endpoint": request.full_url,
                             "model": expected_model, "remote_reservation_verified": True})
            value = {"id": f"synthetic-{index}", "model": expected_model}
            if anthropic:
                value.update(content=[{"type": "text", "text": texts[index]}],
                             stop_reason="end_turn",
                             usage={"input_tokens": 120, "output_tokens": 20})
            elif protocol == "chat_completions":
                value.update(choices=[{"message": {"content": texts[index]}, "finish_reason": "stop"}],
                             usage={"prompt_tokens": 120, "completion_tokens": 20})
            else:
                value.update(output=[{"type": "message", "content": [{"type": "output_text", "text": texts[index]}]}],
                             status="completed",
                             usage={"input_tokens": 120, "output_tokens": 20})
            return Response(value)

        discovery = json.dumps({"literature": {"receipts": [{"fixture_only": True}], "pending_searches": 0}})
        with patch.dict(os.environ, env, clear=True), patch.object(api_orchestrator, "ROOT", root), \
                patch.object(api_orchestrator, "discover_context", return_value=discovery), \
                patch("scripts.ai_providers.urllib.request.urlopen", side_effect=transport), \
                patch.object(socket.socket, "connect", side_effect=AssertionError("external network forbidden")):
            manifest = api_orchestrator.run_cycle(SLUG, "topic-intelligence", "uuapi-anthropic",
                "uuapi-openai", "uuapi-anthropic", "", "", automatic_data=False)
            # The final settled balance must survive the runner too.
            cloud_checkpoint.sync_billing(project)
            control = model_spend.read(project)
            assert control["reservations"] == {} and abs(control["spent_cny"] - 0.0022) < 1e-8
            assert control["authorization_events"] == authority_before
            remote_final = json.loads(git(remote, "show",
                f"refs/heads/cloud-state/{SLUG}:projects/{SLUG}/state/model-spend-control.json"))
            assert remote_final == control
            assert (project / "state/run.json").read_bytes() == state_before
            entries = model_runtime.ledger_entries(project)
            assert [entry["role"] for entry in entries] == [
                "semantic-planner", "persistent-writer", "independent-critic-initial",
                "persistent-remediator", "independent-critic-final"]
            assert len(requests) == 5 and all(not entry["usage_estimated"] for entry in entries)
            provenance = json.loads((project / "state/output-provenance.json").read_text())
            output = project / "program/topic.md"
            recorded = provenance["files"]["program/topic.md"]
            assert recorded["family"] == "openai" and recorded["role"] == "persistent-remediator"
            assert manifest["independent_audit"]["final_verdict"] == "pass-with-conditions"
            for name, audit in manifest["provider_audit"].items():
                assert audit["requested_model"] == audit["reported_model"] and audit["request_id"]
            for path in project.rglob("*"):
                if path.is_file():
                    cloud_checkpoint.check_file(path, project)
            # Keep auditable artifacts with placeholder keys excluded by check_file.
            for relative in ("state/run.json", "state/model-spend-control.json", "state/model-usage.jsonl",
                             "state/output-provenance.json", "reviews/decision-log.md", "program/topic.md"):
                destination = directory / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(project / relative, destination)
            write(directory / "manifest.json", manifest)
            review_dir = project / "reviews/independent"
            shutil.copytree(review_dir, directory / "reviews/independent")
        receipt = {
            "schema_version": "1.0", "scope": "software only; synthetic model and discovery responses",
            "separate_gateways": separate, "openai_protocol": protocol, "chat_token_field": token_field,
            "simulated_requests": requests, "real_paid_calls": 0, "scientific_completion_verified": False,
            "five_roles_verified": True, "remote_reservations_verified": True,
            "settled_fixture_cost_cny": control["spent_cny"], "human_gates_unchanged": True,
            "files": [{"path": p.relative_to(directory).as_posix(),
                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in sorted(directory.rglob("*")) if p.is_file()],
        }
        write(directory / "receipt.json", receipt)
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    write(args.directory / "acceptance.json", {
        "status": "incomplete", "scope": "synthetic software acceptance",
        "real_paid_calls": 0, "scientific_completion_verified": False})
    cases = []
    for name, separate, protocol, field in (
        ("shared-responses", False, "responses", "max_completion_tokens"),
        ("separate-responses", True, "responses", "max_completion_tokens"),
        ("shared-chat-legacy", False, "chat_completions", "max_tokens"),
        ("separate-chat", True, "chat_completions", "max_completion_tokens"),
    ):
        receipt = run_case(args.directory / name, separate=separate, protocol=protocol, token_field=field)
        cases.append({"case": name, "receipt": f"{name}/receipt.json",
                      "sha256": hashlib.sha256((args.directory / name / "receipt.json").read_bytes()).hexdigest(),
                      "simulated_calls": len(receipt["simulated_requests"])})
    result = {"schema_version": "1.0", "status": "passed", "real_paid_calls": 0,
              "source_commit": os.environ.get("GITHUB_SHA"), "workflow_run": os.environ.get("GITHUB_RUN_ID"),
              "scope": "software wiring and budget persistence only; provider transport and discovery are simulated",
              "scientific_completion_verified": False, "cases": cases}
    write(args.directory / "acceptance.json", result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
