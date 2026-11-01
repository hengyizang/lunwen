import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ai_providers, literature_evidence as evidence, literature_model_screening as screening
from scripts.research_artifacts import write
from scripts import source_scope
from scripts import literaturectl
from scripts.research_artifacts import record, sha


class ModelScreeningTests(unittest.TestCase):
    def fixture(self, root):
        project = Path(root)
        raw = project / "evidence/raw.json"; raw.parent.mkdir(parents=True); raw.write_text('{}', encoding="utf-8")
        normalized = project / "evidence/normalized.json"
        write(normalized, {"works": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]})
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        receipt = {"receipt_id": "search1", "status": "success", "result_count": 2,
                   "raw_response_path": "evidence/raw.json", "response_sha256": digest(raw),
                   "normalized_results_path": "evidence/normalized.json", "normalized_results_sha256": digest(normalized)}
        (project / "evidence/literature-api-ledger.jsonl").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
        (project / "evidence/search-log.jsonl").write_text(json.dumps({"evidence_receipt_id": "search1"}) + "\n", encoding="utf-8")
        return project

    def test_standalone_screening_cannot_start_a_paid_call(self):
        with tempfile.TemporaryDirectory() as temp:
            project = self.fixture(temp); ledger = []
            response = json.dumps({"decisions": [{"id": "a", "decision": "include", "reason": "related"},
                                                 {"id": "b", "decision": "uncertain", "reason": "abstract missing"}]})
            def model_call(project, **kwargs):
                ledger.append({"run_id": kwargs["run_id"], "prompt_sha256": screening._digest(kwargs["prompt"]),
                               "request_id": "req-1", "model": "writer-model", "completion_status": "completed"})
                return ai_providers.ModelResult(provider="openai", model="writer-model", reported_model="writer-model",
                                                text=response, usage={}, request_id="req-1", completion_status="completed")
            with patch.object(screening.model_runtime, "call", side_effect=model_call), patch.object(screening.model_runtime, "ledger_entries", return_value=ledger):
                with self.assertRaisesRegex(ValueError, "normal|run_cycle"):
                    screening.execute(project, "search1", "Relevant to the topic?", provider="openai")
                self.assertEqual(ledger, [])

    def test_incomplete_decisions_block(self):
        with tempfile.TemporaryDirectory() as temp:
            project = self.fixture(temp); _, packet = screening.prepare(project, "search1", "Question?")
            with self.assertRaises(ValueError):
                screening.validate_decisions('{"decisions":[{"id":"a","decision":"include","reason":"yes"}]}', packet)

    def test_existing_writer_cycle_binds_full_packet_without_extra_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            project = self.fixture(temp)
            selected = screening.cycle_input(project, "Question?")
            prompt = "Writer instructions\n" + selected["packet_prompt"]
            content = json.dumps({"decisions": [{"id": "a", "decision": "include", "reason": "related"},
                                                  {"id": "b", "decision": "uncertain", "reason": "unknown"}]})
            bundle = {"artifacts": [{"path": selected["artifact_path"], "content": content}]}
            result = ai_providers.ModelResult(provider="openai", model="writer", reported_model="writer", text=json.dumps(bundle),
                                             usage={}, request_id="req", completion_status="completed")
            ledger = [{"run_id": "cycle1", "prompt_sha256": screening._digest(prompt), "request_id": "req",
                       "model": "writer", "completion_status": "completed"}]
            with patch.object(screening.model_runtime, "ledger_entries", return_value=ledger), patch.object(screening.model_runtime, "call") as call:
                screening.accept_cycle_result(project, selected, prompt, result, "cycle1", bundle)
                row = evidence.read_jsonl(project / "evidence/search-log.jsonl")[0]
                self.assertEqual(screening.verify(project, row), [])
                call.assert_not_called()
                self.assertIsNone(screening.cycle_input(project, "Question?"))
                (project / "api_runs/cycle1/screening-writer-prompt.txt").write_text("wrong", encoding="utf-8")
                self.assertTrue(screening.verify(project, row))

    def test_cloud_preparation_marks_every_unscreened_result_uncertain(self):
        with tempfile.TemporaryDirectory() as temp:
            project = self.fixture(temp)
            with patch.object(literaturectl, "require_cloud"):
                result = literaturectl.execute_operation(project, {"action": "literature_screening_prepare", "receipt_id": "search1", "question": "Question?"})
            packet = json.loads((project / result["path"]).read_text(encoding="utf-8"))
            self.assertFalse(result["screening_completed"])
            self.assertEqual([r["decision"] for r in packet["decisions"]], ["uncertain", "uncertain"])
            self.assertNotIn("screened_by", evidence.read_jsonl(project / "evidence/search-log.jsonl")[0])

    def test_registered_supplied_scope_is_bound_to_acquisition_and_not_human_reading(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp); pdf = project / "data/raw/paper.pdf"; pdf.parent.mkdir(parents=True); pdf.write_bytes(b"%PDF synthetic")
            manifest = project / "data/manifests/paper.json"; write(manifest, {})
            primary = {"path": "data/raw/paper.pdf", "sha256": sha(pdf)}
            acquired = project / "evidence/literature/assets/receipt.json"
            write(acquired, {"pdfs": [primary]}); record(project, [acquired], "scripts/literature_assets.py")
            metadata = project / "literature/metadata/paper-a.json"
            write(metadata, {"acquisition_receipt": {"path": acquired.relative_to(project).as_posix(), "sha256": sha(acquired)}})
            config = project / "program/literature-workbench.json"
            write(config, {"papers": [{"id": "paper-a", "source_scope": "full_text", "source": primary, "manifest": "data/manifests/paper.json"}]})
            record(project, [metadata, config], "scripts/literature_registration.py")
            with patch("scripts.literaturectl.approved_pdf", return_value=pdf):
                output = source_scope.record_registered(project, "paper-a")
                binding = {"path": output.relative_to(project).as_posix(), "sha256": sha(output)}
                self.assertEqual(source_scope.verify(project, primary, binding, "full_text"), [])
                self.assertFalse(json.loads(output.read_text())["semantic_verification"])
                acquired.write_text('{}', encoding="utf-8")
                self.assertTrue(source_scope.verify(project, primary, binding, "full_text"))


if __name__ == "__main__":
    unittest.main()
