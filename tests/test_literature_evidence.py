from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

from scripts.literature_evidence import (
    LiteratureEvidenceError,
    build_search_url,
    execute_citation_graph,
    execute_import,
    execute_search,
    fetch_provider_bytes,
    normalize_search,
    screen_receipt,
    validate_search_evidence,
)


class LiteratureEvidenceTests(unittest.TestCase):
    def project(self, root: Path) -> Path:
        project = root / "projects" / "demo"
        (project / "evidence").mkdir(parents=True)
        (project / "evidence" / "search-log.jsonl").write_text("", encoding="utf-8")
        return project

    @staticmethod
    def openalex_response(_url: str, **_kwargs):
        payload = json.dumps(
            {
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "display_name": "Auditable AI for rotating machinery",
                        "publication_year": 2026,
                        "doi": "https://doi.org/10.1000/example",
                        "authorships": [{"author": {"display_name": "A. Researcher"}}],
                        "primary_location": {"source": {"display_name": "Example Journal"}},
                    }
                ]
            }
        ).encode()
        return payload, _url, 200, "application/json"

    def test_live_search_is_hash_bound_and_requires_screening(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(Path(directory))
            receipt = execute_search(
                project,
                "openalex",
                "rotating machinery AI",
                query_family="core-method",
                date_range="2021-2026",
                filters="journal and conference papers",
                limit=10,
                fetcher=self.openalex_response,
            )
            records = [json.loads(line) for line in (project / "evidence" / "search-log.jsonl").read_text().splitlines()]
            self.assertTrue(any("named human" in item for item in validate_search_evidence(project, records)))
            record = screen_receipt(
                project,
                receipt["receipt_id"],
                ["doi:10.1000/example"],
                ["Excluded records outside the registered task and mechanism."],
                "Hengyi Zang",
            )
            self.assertEqual(record["included_work_ids"], ["doi:10.1000/example"])
            records = [json.loads(line) for line in (project / "evidence" / "search-log.jsonl").read_text().splitlines()]
            self.assertEqual(validate_search_evidence(project, records), [])
            raw = project / receipt["raw_response_path"]
            raw.write_text("tampered", encoding="utf-8")
            self.assertTrue(any("hash-mismatched" in item for item in validate_search_evidence(project, records)))

    def test_local_wos_export_is_not_treated_as_a_live_api_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(Path(directory))
            export = project / "private" / "wos.csv"
            export.parent.mkdir()
            export.write_text(
                "Article Title,Publication Year,DOI,Authors,UT\n"
                "Verified title,2025,10.1000/wos,A. Author,WOS:1\n",
                encoding="utf-8",
            )
            receipt = execute_import(
                project,
                "wos",
                "private/wos.csv",
                query="verified query",
                query_family="adjacent-field",
                date_range="2020-2026",
                filters="document types: article",
                actor="Hengyi Zang",
            )
            self.assertEqual(receipt["mode"], "licensed_local_export")
            self.assertEqual(receipt["result_count"], 1)
            self.assertEqual(receipt["response_sha256"], __import__("hashlib").sha256(export.read_bytes()).hexdigest())

    def test_screen_rejects_identifier_not_returned_by_provider(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(Path(directory))
            receipt = execute_search(
                project,
                "openalex",
                "query",
                query_family="core",
                date_range="all years",
                filters="none",
                limit=5,
                fetcher=self.openalex_response,
            )
            with self.assertRaises(LiteratureEvidenceError):
                screen_receipt(
                    project,
                    receipt["receipt_id"],
                    ["doi:10.9999/not-returned"],
                    ["Reviewed all records."],
                    "Reviewer",
                )

    def test_opencitations_uses_prefixed_identifier_and_never_records_token(self) -> None:
        captured: dict[str, object] = {}

        def fetcher(url: str, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            payload = json.dumps(
                [
                    {
                        "oci": "1-2",
                        "citing": "omid:br/1 doi:10.1000/citing pmid:1",
                        "cited": "omid:br/2 doi:10.1038/s41586-021-03819-2",
                        "creation": "2026-01-01",
                    }
                ]
            ).encode()
            return payload, url, 200, "application/json"

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"OPENCITATIONS_ACCESS_TOKEN": "secret-token"}
        ):
            project = self.project(Path(directory))
            receipt = execute_citation_graph(
                project,
                "10.1038/s41586-021-03819-2",
                "citations",
                date_range="all years",
                filters="acceptance",
                fetcher=fetcher,
            )
            ledger = (project / "evidence" / "literature-api-ledger.jsonl").read_text()
        self.assertEqual(receipt["result_count"], 1)
        self.assertTrue(
            str(captured["url"]).endswith(
                "/citations/doi:10.1038/s41586-021-03819-2"
            )
        )
        self.assertEqual(captured["headers"]["authorization"], "secret-token")
        self.assertNotIn("secret-token", ledger)

    def test_transient_rate_limit_is_retried_with_provider_headers(self) -> None:
        calls: list[dict[str, str]] = []

        def fetcher(url: str, **kwargs):
            calls.append(kwargs["headers"])
            if len(calls) < 3:
                raise OSError("HTTP Error 429: Too Many Requests")
            return b"{}", url, 200, "application/json"

        with patch("scripts.literature_evidence.time.sleep") as sleep:
            payload, _, status, _ = fetch_provider_bytes(
                fetcher, "https://example.org/api", "arxiv"
            )
        self.assertEqual(payload, b"{}")
        self.assertEqual(status, 200)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(item["Accept"] == "application/atom+xml" for item in calls))
        self.assertEqual([item.args[0] for item in sleep.call_args_list], [2, 5])

    def test_failed_normalization_preserves_returned_raw_response(self) -> None:
        def fetcher(url: str, **_kwargs):
            return b"<html>upstream block</html>", url, 200, "text/html"

        with tempfile.TemporaryDirectory() as directory:
            project = self.project(Path(directory))
            with self.assertRaises(LiteratureEvidenceError):
                execute_search(
                    project,
                    "dblp",
                    "machine learning",
                    query_family="acceptance",
                    date_range="all years",
                    filters="public API",
                    limit=1,
                    fetcher=fetcher,
                )
            ledger = json.loads(
                (project / "evidence" / "literature-api-ledger.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            raw = project / ledger["raw_response_path"]
            self.assertEqual(raw.read_bytes(), b"<html>upstream block</html>")
            self.assertEqual(ledger["http_status"], 200)

    def test_arxiv_uses_explicit_boolean_terms(self) -> None:
        url = build_search_url("arxiv", "machine learning research", 3)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(
            query["search_query"],
            ["all:machine AND all:learning AND all:research"],
        )

    def test_dblp_uses_official_sparql_endpoint_and_normalizes_bindings(self) -> None:
        url = build_search_url("dblp", "machine learning research", 2)
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)["query"][0]
        self.assertEqual(parsed.hostname, "sparql.dblp.org")
        self.assertIn('CONTAINS(LCASE(STR(?title)), "machine learning")', query)
        self.assertIn("LIMIT 2", query)
        payload = json.dumps(
            {
                "results": {
                    "bindings": [
                        {
                            "publ": {"type": "uri", "value": "https://dblp.org/rec/x"},
                            "title": {"type": "literal", "value": "Machine learning"},
                            "year": {"type": "literal", "value": "2026"},
                            "doi": {
                                "type": "uri",
                                "value": "https://doi.org/10.1000/example",
                            },
                        }
                    ]
                }
            }
        ).encode()
        works = normalize_search("dblp", payload)
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0]["doi"], "10.1000/example")
        self.assertEqual(works[0]["publication_year"], 2026)


if __name__ == "__main__":
    unittest.main()
