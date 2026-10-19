from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import concept_illustrations, paper_qa, paper_reader


class ProductionOptionalTests(unittest.TestCase):
    def test_unmetered_image_generation_is_unavailable_even_with_execute(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with patch("urllib.request.urlopen") as transport:
                preview = concept_illustrations.prepare(project,"P01","concept","Concept only.","gpt-image-api","gpt-image")
                self.assertTrue(preview["dry_run"])
                self.assertFalse(preview["available"])
                with self.assertRaisesRegex(ValueError,"disabled"):
                    concept_illustrations.prepare(project,"P01","concept","Concept only.","gpt-image-api","gpt-image",execute=True)
                transport.assert_not_called()
            self.assertEqual(list(project.iterdir()), [])

    def test_qa_retrieval_is_free_and_preserves_source_anchor_and_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project/"evidence"/"reader.md";source.parent.mkdir()
            source.write_text("## PDF page 7\nA randomized pilot measured 120 adults.\nMissing effect estimates require review.\n",encoding="utf-8")
            with patch.object(paper_qa.model_runtime,"call") as call:
                report = paper_qa.answer(project,["evidence/reader.md"],"How many adults were measured?","evidence/qa/pilot.json")
                call.assert_not_called()
            result = json.loads((project/report["output"]).read_text())
            self.assertEqual(result["status"],"retrieval_only_no_model_call")
            self.assertTrue(result["not_paperqa2_sdk"])
            self.assertTrue(result["not_scientific_evidence"])
            self.assertIn("PDF page 7",result["retrieval"]["blocks"][0]["locator"])
            self.assertEqual(result["retrieval"]["sources"][0]["sha256"],paper_qa.sha256_file(source))
            with self.assertRaisesRegex(ValueError,"overwrite"):
                paper_qa.answer(project,["evidence/reader.md"],"adults?","evidence/qa/pilot.json")

    def test_qa_absence_abstains_without_paid_call_and_rejects_private_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary);(project/"evidence").mkdir()
            (project/"evidence"/"one.txt").write_text("A pilot measured adults.")
            with patch.object(paper_qa.model_runtime,"call") as call:
                report=paper_qa.answer(project,["evidence/one.txt"],"volcanology eruptions", "evidence/qa/none.json",execute=True)
                call.assert_not_called()
            self.assertEqual(report["status"],"no_lexical_match_abstained_without_model_call")
            with self.assertRaisesRegex(ValueError,"private/control/raw"):
                paper_qa.retrieve(project,["state/model-spend.json"],"budget")
            with self.assertRaises(ValueError):
                paper_qa.retrieve(project,["../outside.txt"],"outside")

    def test_qa_rejects_fabricated_quotes_unknown_anchors_and_duplicate_json(self):
        blocks=[{"source_id":"SRC001","locator":"PDF page 2","text":"The sample included 120 adults."}]
        valid={"answer":"The sample included 120 adults.","abstain":False,
               "citations":[{"source_id":"SRC001","locator":"PDF page 2","quote":"120 adults"}]}
        self.assertEqual(paper_qa.validate_response(json.dumps(valid),blocks),valid)
        valid["citations"][0]["quote"]="999 adults"
        with self.assertRaisesRegex(ValueError,"non-verbatim"):
            paper_qa.validate_response(json.dumps(valid),blocks)
        valid["citations"][0].update(quote="120 adults",locator="PDF page 8")
        with self.assertRaisesRegex(ValueError,"absent source/anchor"):
            paper_qa.validate_response(json.dumps(valid),blocks)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            paper_qa.validate_response('{"answer":"one","answer":"two","abstain":true,"citations":[]}',blocks)
        with self.assertRaisesRegex(ValueError,"must abstain"):
            paper_qa.validate_response('{"answer":"Proven globally.","abstain":false,"citations":[]}',blocks)

    def test_production_qa_uses_central_reader_role_and_preserves_rejected_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary);(project/"evidence").mkdir()
            (project/"evidence"/"pilot.txt").write_text("Pilot sample included 120 adults.")
            fake=SimpleNamespace(provider="cheapai-gpt-pro",model="gpt-6.1-sol",reported_model="gpt-6.1-sol",
                request_id="fake-receipt",cache_hit=False,text='{"answer":"Invented result.","abstain":false,"citations":[]}')
            with patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"production"}), \
                 patch.object(paper_qa.model_runtime,"call",return_value=fake) as call:
                report=paper_qa.answer(project,["evidence/pilot.txt"],"Pilot sample?","evidence/qa/rejected.json",execute=True)
            kwargs=call.call_args.kwargs
            self.assertEqual((kwargs["role"],kwargs["reasoning_effort"]),("reader-qa","high"))
            self.assertIn("untrusted source data",kwargs["prompt"])
            self.assertEqual(report["status"],"model_response_rejected_do_not_use")
            saved=json.loads((project/report["output"]).read_text())
            self.assertNotIn("response",saved)
            self.assertIn("response_sha256",saved)
            self.assertTrue(saved["human_source_review_required"])

    def test_translation_production_passes_high_effort_and_records_actual_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary);pdf=project/"source.pdf";pdf.write_bytes(b"synthetic-reader-fixture")
            fake_reader=SimpleNamespace(is_encrypted=False,pages=[SimpleNamespace(extract_text=lambda:"The sample comprised 120 adults.")])
            fake_result=SimpleNamespace(text="样本包括120名成年人。",provider="cheapai-gpt-pro",model="gpt-6.1-sol",
                reported_model="gpt-6.1-sol",request_id="fake-translation",cache_hit=False)
            with patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"production"}), \
                 patch.dict("sys.modules",{"pypdf":SimpleNamespace(PdfReader=lambda *args,**kwargs:fake_reader)}), \
                 patch.object(paper_reader.model_runtime,"call",return_value=fake_result) as call:
                report=paper_reader.build(project,pdf,project/"evidence"/"readers"/"reader.md",translate=True)
            self.assertEqual(call.call_args.kwargs["role"],"reader-translation")
            self.assertEqual(call.call_args.kwargs["reasoning_effort"],"high")
            receipt=json.loads((project/report["receipt"]).read_text())
            self.assertEqual(receipt["translation_calls"][0]["provider"],"cheapai-gpt-pro")
            self.assertEqual(receipt["translation_calls"][0]["reported_model"],"gpt-6.1-sol")


if __name__=="__main__":
    unittest.main()
