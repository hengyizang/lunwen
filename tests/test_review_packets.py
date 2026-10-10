"""Synthetic control-plane fixtures; no model calls or research conclusions."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts import output_provenance, review_packets as packets
from scripts.research_artifacts import read, sha, write


RUBRIC = {"dimensions": [{"id": "fidelity", "description": "Preserves evidence and scientific meaning",
                          "value_type": "integer", "min": 0, "max": 4}],
          "critical_errors": [{"id": "invented-fact", "criterion": "Invents or materially changes a protected fact"}]}


def bound(project, path, payload=None):
    target = project / path
    if payload is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload.encode() if isinstance(payload, str) else payload)
    return {"path": path, "sha256": sha(target), "locator": "complete test artifact"}


def fixture(project):
    evidence = bound(project, "evidence/source.md", "The recorded estimate is 2 units with uncertainty.")
    candidate = bound(project, "api_runs/private-left.md", "The estimate was 2 units; uncertainty remains.")
    failure = bound(project, "api_runs/failed.json", json.dumps({"status": "failed", "reason": "synthetic interruption"}))
    output_provenance.record_model_writes(project, [project / candidate["path"]], family="anthropic",
        provider="test-critic", model="model-a", role="read-only-critic", run_id="synthetic")
    common = {"authorized_for_internal_review": True, "authorization_note": "Authorized existing internal review text",
              "author_id": "author-a", "model": "model-a", "channel": "channel-a", "price_cny": 0.2}
    packet = {"id": "calibration-one", "kind": "calibration", "rubric": copy.deepcopy(RUBRIC), "cases": [
        {"id": "case-one", "sources": [evidence], "candidates": [
            {"id": "first", "status": "success", "artifact": candidate, **common},
            {"id": "failed", "status": "failed", "failure_reason": "synthetic interruption", "failure_receipt": failure, **common}]}]}
    write(project / packets.INPUT, {"schema_version": "1.0", "packets": [packet]})
    return packet


def judgments(project, packet_id="calibration-one"):
    snapshot = packets.review_snapshot(project, packet_id)
    rows = []
    for candidate in snapshot["roster"]:
        row = {"case_label": candidate["case_label"], "candidate_label": candidate["candidate_label"],
               "rationale": "Synthetic human observation; no scientific verdict inferred"}
        if candidate["status"] == "failed":
            row["status"] = "unscorable_failed"
        else:
            row.update(ratings={"fidelity": 3}, critical_errors={"invented-fact": False})
        rows.append(row)
    return {"rater_id": "reviewer-b", "independent": True, "independence_note": "No participation in candidate creation",
            "observations": rows}


def visual_fixture(project):
    original = bound(project, "papers/P01/manuscript/main.md", "Recorded manuscript source")
    artifact = bound(project, "papers/P01/manuscript/main.pdf", b"%PDF-synthetic-actual-output")
    preview = bound(project, "reports/previews/page-1.png", b"synthetic-preview-bytes")
    qa = bound(project, "reports/output-qa.json", json.dumps({"status": "pass", "outputs": [artifact, preview]}))
    output_provenance.record_model_writes(project, [project / qa["path"]], family="other", provider="deterministic-control-plane",
        model="synthetic-fixture", role="artifact-builder", run_id="synthetic-ci")
    receipt_value = {"schema_version": "1.0", "status": "pass", "inputs": [original], "outputs": [artifact, preview],
                     "renderer": {"name": "cloud_runtime", "implementation_sha256": sha(packets.ROOT / "scripts/cloud_runtime.py")},
                     "execution": {"mode": "cloud", "receipt_id": "synthetic-ci-render-1"}}
    receipt = bound(project, "reports/render.render-receipt.json", json.dumps(receipt_value))
    output_provenance.record_model_writes(project, [project / receipt["path"]], family="other",
        provider="cloud-tex-renderer", model="cloud_runtime.py", role="render-receipt", run_id="synthetic-ci")
    packet = {"id": "visual-one", "kind": "visual", "rubric": copy.deepcopy(RUBRIC), "artifacts": [
        {"id": "main-pdf", "artifact": artifact, "sources": [original], "previews": [preview], "qa_report": qa,
         "render_receipt": receipt, "checklist": ["math_symbols", "final_size_readability", "color_vision", "statistical_labels"]}]}
    write(project / packets.INPUT, {"schema_version": "1.0", "packets": [packet]})
    return packet


class ReviewPacketTests(unittest.TestCase):
    def test_blind_labels_stable_and_private_metadata_never_enters_materials(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            fixture(project)
            self.assertEqual(packets.refresh(project)["status"], "pass")
            first = packets.review_snapshot(project, "calibration-one")
            packets.refresh(project)
            second = packets.review_snapshot(project, "calibration-one")
            self.assertEqual(first, second)
            raw = "\n".join(path.read_text() for path in (project / "reports/review-packets/calibration-one/materials").rglob("*") if path.is_file())
            for hidden in ("model-a", "channel-a", "private-left.md", "author-a", "price_cny"):
                self.assertNotIn(hidden, raw)
            self.assertEqual(len(second["roster"]), 2)
            copied = next(row for row in second["roster"] if row["status"] == "success")["artifact"]
            origin = output_provenance.current_origin(project, project / "reports/review-packets/calibration-one" / copied)
            self.assertEqual(origin["family"], "anthropic")
            self.assertEqual(origin["role"], "internal-read-only-review-copy")

    def test_confirmation_is_prepare_only_and_preserves_every_attempt_without_upgrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            fixture(project)
            packets.refresh(project)
            path, receipt = packets.create_confirmation(project, "calibration-one", "Owner / safe", judgments(project))
            self.assertFalse(path.exists())
            write(path, receipt)
            path2, second = packets.create_confirmation(project, "calibration-one", "Owner / safe", judgments(project))
            self.assertEqual(path, path2)
            self.assertEqual(len(second["attempts"]), 2)
            write(path2, second)
            report = packets.audit(project)
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["calibration_status"], "NOT_CALIBRATED")
            self.assertFalse(report["gate_approved"])
            self.assertFalse(report["scientific_completion_verified"])
            self.assertEqual(len(report["packets"][0]["confirmations"][0]["attempts"]), 2)

    def test_invalid_scores_critical_flags_author_and_omitted_failures_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            fixture(project)
            packets.refresh(project)
            valid = judgments(project)
            variants = []
            own = copy.deepcopy(valid); own["rater_id"] = "author-a"; variants.append(own)
            omitted = copy.deepcopy(valid); omitted["observations"].pop(); variants.append(omitted)
            for score in (True, 9, 2.5, float("nan")):
                value = copy.deepcopy(valid)
                next(row for row in value["observations"] if "ratings" in row)["ratings"]["fidelity"] = score
                variants.append(value)
            value = copy.deepcopy(valid)
            next(row for row in value["observations"] if "critical_errors" in row)["critical_errors"]["invented-fact"] = "no"
            variants.append(value)
            for value in variants:
                with self.assertRaises(ValueError):
                    packets.create_confirmation(project, "calibration-one", "Owner", value)

    def test_changed_source_material_or_rubric_blocks_stale_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            fixture(project)
            packets.refresh(project)
            path, receipt = packets.create_confirmation(project, "calibration-one", "Owner", judgments(project))
            write(path, receipt)
            (project / "api_runs/private-left.md").write_text("Changed estimate is 3 units.")
            with self.assertRaises(ValueError):
                packets.review_snapshot(project, "calibration-one")
            self.assertEqual(packets.audit(project)["status"], "fail")
            self.assertEqual(packets.refresh(project)["status"], "fail")
            history = project / "reports/review-packets/calibration-one/refresh-attempts.jsonl"
            self.assertEqual(len(history.read_text().splitlines()), 2)

    def test_disclosing_model_name_is_refused_without_rewriting_the_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            packet = fixture(project)
            candidate = project / "api_runs/private-left.md"
            candidate.write_text("model-a wrote the estimate of 2 units.")
            packet["cases"][0]["candidates"][0]["artifact"]["sha256"] = sha(candidate)
            write(project / packets.INPUT, {"schema_version": "1.0", "packets": [packet]})
            self.assertEqual(packets.refresh(project)["status"], "fail")
            self.assertIn("model-a", candidate.read_text())

    def test_visual_relation_requires_current_controlled_renderer_and_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            packet = visual_fixture(project)
            self.assertEqual(packets.refresh(project)["status"], "pass")
            current = packets.review_snapshot(project, "visual-one")
            self.assertEqual(current["kind"], "visual")
            receipt_path = project / packet["artifacts"][0]["render_receipt"]["path"]
            fake = read(receipt_path)
            fake["renderer"]["implementation_sha256"] = "0" * 64
            write(receipt_path, fake)
            packet["artifacts"][0]["render_receipt"]["sha256"] = sha(receipt_path)
            write(project / packets.INPUT, {"schema_version": "1.0", "packets": [packet]})
            self.assertEqual(packets.refresh(project)["status"], "fail")

    def test_visual_adverse_inspections_cannot_be_discarded_by_a_later_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            packet = visual_fixture(project)
            packets.refresh(project)
            checks = {key: True for key in packet["artifacts"][0]["checklist"]}
            value = {"rater_id": "reviewer-b", "independent": True, "independence_note": "Independent final PDF inspection",
                     "inspections": [{"artifact_id": "main-pdf", "checks": {**checks, "math_symbols": False}, "note": "Symbol needs correction"}]}
            path, receipt = packets.create_confirmation(project, "visual-one", "Owner", value)
            write(path, receipt)
            value["inspections"][0]["checks"] = checks
            path, receipt = packets.create_confirmation(project, "visual-one", "Owner", value)
            write(path, receipt)
            report = packets.audit(project)
            self.assertEqual(report["status"], "pass")
            self.assertFalse(report["packets"][0]["visual_checklist_passed_by_human"])
            self.assertEqual(len(report["packets"][0]["confirmations"][0]["attempts"]), 2)


if __name__ == "__main__":
    unittest.main()
