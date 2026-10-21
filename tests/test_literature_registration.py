import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from scripts import literature_evidence as evidence, literature_intelligence as intelligence
from scripts.literature_registration import register
from scripts.research_artifacts import read, sha, write


class LiteratureRegistrationTests(unittest.TestCase):
    def test_metadata_registers_real_candidate_and_rejects_tampered_leads_without_paid_calls(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            write(project / intelligence.PLAN, {"schema_version":"1.0", "doctoral_question":"How can fixture evidence be revisited?",
                "topic_keywords":["fixture"], "searches":[{"provider":"semantic-scholar","query":"fixture","limit":2}]})
            def fetch(url, **kwargs):
                body = {"data":[{"paperId":"one","title":"Fixture literature source","year":2025,
                    "authors":[{"name":"Fixture Author"}],"externalIds":{"DOI":"10.1000/fixture"},
                    "abstract":"A synthetic metadata response; not a real scientific paper."}]}
                return json.dumps(body).encode(), url, 200, "application/json"
            report = intelligence.discover(project, fetcher=fetch)
            digest = sha(project / intelligence.OUTPUT)
            with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
                result = register(project, report["candidates"][0]["canonical_id"], expected_leads_sha256=digest)
            self.assertEqual(result["attachment_status"], "metadata_only")
            self.assertFalse(result["human_screening_approved"])
            config = read(project / "program/literature-workbench.json")
            self.assertEqual(config["papers"][0]["source_scope"], "metadata_only")
            with self.assertRaisesRegex(ValueError, "exact current"):
                register(project, report["candidates"][0]["canonical_id"], expected_leads_sha256="0"*64)
            with self.assertRaisesRegex(ValueError, "does not occur"):
                register(project, "invented", expected_leads_sha256=digest)
            source = project / report["source_receipts"][0]["raw_response_path"]
            source.write_text("tampered")
            with self.assertRaisesRegex(ValueError, "stale"):
                register(project, report["candidates"][0]["canonical_id"], expected_leads_sha256=digest)

    def test_arxiv_keeps_boolean_field_query_and_applies_recent_submission_window(self):
        query = 'ti:"machine learning" OR abs:"distribution shift"'
        url = evidence.build_search_url("arxiv", query, 10, date_range="2025-2026")
        params = parse_qs(urlsplit(url).query)
        self.assertIn(query, params["search_query"][0])
        self.assertIn("submittedDate:[202501010000 TO 202612312359]", params["search_query"][0])
        self.assertEqual(params["sortBy"], ["submittedDate"])
        for query in ['ti:"unfinished', "unsupported:query", "a (" ]:
            with self.assertRaises(evidence.LiteratureEvidenceError):
                evidence.build_search_url("arxiv", query, 10)
        basic = parse_qs(urlsplit(evidence.build_search_url("arxiv", "graph OR neural", 2)).query)
        self.assertEqual(basic["search_query"], ["all:graph OR all:neural"])

    def test_dblp_search_enumeration_preserves_real_identity_year_and_authors(self):
        url = evidence.build_search_url("dblp", "*", 20, date_range="2025",
            filters={"venue":"conf/icml","year":2025,"offset":20,"transport":"search"})
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(urlsplit(url).hostname, "dblp.org")
        self.assertEqual(params["q"], ["venue:ICML year:2025"])
        self.assertEqual(params["f"], ["20"])
        body = {"result":{"hits":{"hit":[{"@id":"1","info":{"key":"conf/icml/Fixture2025",
            "url":"https://dblp.org/rec/conf/icml/Fixture2025","title":"Synthetic conference metadata",
            "year":"2025","authors":{"author":[{"text":"Fixture Author"}]},
            "ee":"https://doi.org/10.1000/fixture","type":"Conference and Workshop Papers"}}]}}}
        with tempfile.TemporaryDirectory() as directory:
            receipt = evidence.execute_search(Path(directory), "dblp", "*", query_family="fixture",
                date_range="2025", filters={"venue":"conf/icml","year":2025,"transport":"search"}, limit=20,
                fetcher=lambda url, **kwargs: (json.dumps(body).encode(),url,200,"application/json"))
            normalized = read(Path(directory) / receipt["normalized_results_path"])
            self.assertEqual(len(normalized["works"]), 1)
            self.assertEqual(normalized["works"][0]["authors"], ["Fixture Author"])
            self.assertEqual(normalized["works"][0]["document_types"], ["conference-paper"])
            self.assertEqual(normalized["works"][0]["doi"], "10.1000/fixture")
