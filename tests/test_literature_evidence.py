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
    parse_conditions,
    filter_results,
    screen_receipt,
    validate_search_evidence,
)


class LiteratureEvidenceTests(unittest.TestCase):
    def test_structured_dates_are_requested_and_returned_metadata_is_postchecked(self):
        captured = []
        def fetch(url, **_kwargs):
            captured.append(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))
            rows = [{"id": "old", "display_name": "Old result", "publication_year": 2019},
                    {"id": "current", "display_name": "Current result", "publication_year": 2025},
                    {"id": "unknown", "display_name": "Undated result"}]
            return json.dumps({"results": rows}).encode(), url, 200, "application/json"
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(Path(directory))
            receipt = execute_search(project, "openalex", "machinery", query_family="core",
                date_range="2024-2026", filters="none", limit=10, fetcher=fetch)
            self.assertIn("from_publication_date:2024-01-01", captured[0]["filter"][0])
            self.assertEqual(receipt["result_count"], 1)
            self.assertEqual(receipt["filtered_out_count"], 1)
            self.assertEqual(receipt["unresolved_filter_count"], 1)
            normalized = json.loads((project / receipt["normalized_results_path"]).read_text())
            self.assertEqual(normalized["works"][0]["title"], "Current result")
            self.assertEqual(normalized["filter_audit"]["unresolved"][0]["work"]["title"], "Undated result")
            record = json.loads((project / "evidence/search-log.jsonl").read_text().strip())
            self.assertIn("postfilter_checked", record["filters"])
            record["filters"] = "Claimed complete filtering without an execution receipt"
            self.assertTrue(any("search conditions" in error for error in validate_search_evidence(project, [record])))

    def test_legacy_descriptions_are_explicitly_unapplied_and_unknown_structured_filters_fail(self):
        parsed = parse_conditions("all indexed years; inspect dates", "journal and conference papers")
        self.assertEqual(parsed["status"], "unfiltered_declared_only")
        self.assertEqual(len(parsed["unapplied_declarations"]), 2)
        rows = [{"id": "1", "publication_year": None, "title": "Unfiltered"}]
        result, audit = filter_results("arxiv", rows, parsed)
        self.assertEqual(result, rows)
        self.assertEqual(audit["postfilter_checked"], [])
        with self.assertRaises(LiteratureEvidenceError):
            build_search_url("openalex", "query", 10, filters={"unsupported_filter": True})
        with self.assertRaises(LiteratureEvidenceError):
            parse_conditions("2026-2020", {})

    def test_dblp_conference_enumeration_binds_official_stream_year_and_page(self):
        url = build_search_url("dblp", "*", 100, date_range="2025", filters={"venue": "conf/icml", "year": 2025, "offset": 100})
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["query"][0]
        self.assertIn("<https://dblp.org/streams/conf/icml>", query)
        self.assertIn('FILTER(STR(?year) = "2025")', query)
        self.assertIn("dblp:Inproceedings", query)
        self.assertIn("OFFSET 100", query)
        self.assertNotIn("CONTAINS", query)
        with self.assertRaises(LiteratureEvidenceError):
            build_search_url("dblp", "*", 10, filters={"venue": "ICML> injected"})
        with self.assertRaises(LiteratureEvidenceError):
            build_search_url("dblp", "*", 10)

    def test_exact_dates_and_document_types_distinguish_missing_from_nonmatching(self):
        parsed = parse_conditions({"from": "2025-03-01", "to": "2025-05-31"}, {"document_types": ["conference-paper"]})
        rows = [{"id": "1", "publication_date": "2025-04-02", "document_types": ["Conference"]},
                {"id": "2", "publication_date": "2025-08-01", "document_types": ["Conference"]},
                {"id": "3", "publication_year": 2025, "document_types": ["Conference"]}]
        result, audit = filter_results("hal", rows, parsed)
        self.assertEqual([row["id"] for row in result], ["1"])
        self.assertEqual(audit["postfilter_only"], ["document_types", "publication_date"])
        self.assertEqual(audit["unresolved"][0]["reasons"], ["exact_publication_date_missing"])

    def test_s2_canonical_lookup_retains_enrichment_fields_and_checks_returned_identity(self):
        url = build_search_url("semantic-scholar", "ignored title", 5, filters={"identity": "DOI:10.1000/example"})
        self.assertIn("/paper/DOI%3A10.1000%2Fexample?", url)
        self.assertIn("citationCount", urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["fields"][0])
        row = {"paperId": "S2", "title": "A paper", "year": 2025, "externalIds": {"DOI": "10.1000/example", "ArXiv": "2501.00001v2"},
               "citationCount": 7, "abstract": "We propose a method.", "publicationTypes": ["Conference"]}
        works = normalize_search("semantic-scholar", json.dumps(row).encode())
        self.assertEqual(works[0]["citation_count"], 7)
        self.assertEqual(works[0]["arxiv_id"], "2501.00001v2")
        matched, _ = filter_results("semantic-scholar", works, parse_conditions(None, {"identity": "DOI:10.1000/example"}))
        self.assertEqual(len(matched), 1)
        rejected, audit = filter_results("semantic-scholar", works, parse_conditions(None, {"identity": "DOI:10.1000/other"}))
        self.assertEqual(rejected, [])
        self.assertEqual(audit["rejected"][0]["reasons"], ["identity_mismatch"])

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
        self.assertTrue(all("application/atom+xml" in item["Accept"] for item in calls))
        self.assertEqual([item.args[0] for item in sleep.call_args_list], [5, 20])

    def test_openalex_key_stays_in_header_and_is_redacted_on_error(self) -> None:
        url = build_search_url("openalex", "robot learning", 1)
        self.assertNotIn("api_key", url)
        captured = {}

        def fetcher(request_url: str, **kwargs):
            captured["url"] = request_url
            captured["headers"] = kwargs["headers"]
            raise OSError("upstream included test-openalex-secret in an error")

        with patch.dict("os.environ", {"OPENALEX_API_KEY": "test-openalex-secret"}):
            with self.assertRaises(LiteratureEvidenceError) as raised:
                fetch_provider_bytes(fetcher, url, "openalex")
        self.assertEqual(captured["url"], url)
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-openalex-secret")
        self.assertNotIn("test-openalex-secret", str(raised.exception))

    def test_openalex_does_not_persist_response_echoing_key(self) -> None:
        def fetcher(url: str, **_kwargs):
            return b'{"echo":"test-openalex-secret"}', url, 200, "application/json"

        with patch.dict("os.environ", {"OPENALEX_API_KEY": "test-openalex-secret"}):
            with self.assertRaisesRegex(LiteratureEvidenceError, "refusing to persist"):
                fetch_provider_bytes(fetcher, build_search_url("openalex", "x", 1), "openalex")

    def test_openalex_does_not_send_obsolete_mailto_parameter(self) -> None:
        with patch.dict("os.environ", {"OPENALEX_MAILTO": "person@example.org"}):
            self.assertNotIn("mailto=", build_search_url("openalex", "robot learning", 1))

    def test_arxiv_identifier_uses_official_id_list_probe(self) -> None:
        url = build_search_url("arxiv", "arxiv-id:1706.03762", 1)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["id_list"], ["1706.03762"])
        self.assertEqual(query["max_results"], ["1"])
        self.assertNotIn("search_query", query)

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

    def test_serpapi_google_scholar_is_normalized_without_persisting_key(self) -> None:
        captured: dict[str, object] = {}

        def fetcher(url: str, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            payload = json.dumps(
                {
                    "search_metadata": {"status": "Success"},
                    "organic_results": [
                        {
                            "result_id": "scholar-result-1",
                            "title": "Auditable machine learning for science",
                            "link": "https://doi.org/10.1000/scholar-example",
                            "snippet": "A result snippet returned by Google Scholar.",
                            "publication_info": {
                                "summary": "A Researcher, B Scientist - Example Journal, 2025",
                                "authors": [
                                    {"name": "A Researcher"},
                                    {"name": "B Scientist"},
                                ],
                            },
                        }
                    ],
                }
            ).encode()
            return payload, url, 200, "application/json"

        secret = "serpapi-test-secret"
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"SERPAPI_API_KEY": secret}, clear=True
        ):
            project = self.project(Path(directory))
            receipt = execute_search(
                project,
                "serpapi-google-scholar",
                "auditable machine learning",
                query_family="supplemental-discovery",
                date_range="all years",
                filters="Google Scholar supplemental discovery",
                limit=50,
                fetcher=fetcher,
            )
            ledger = (project / "evidence" / "literature-api-ledger.jsonl").read_text()
            normalized = json.loads(
                (project / receipt["normalized_results_path"]).read_text()
            )["works"]

        transport_query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(str(captured["url"])).query
        )
        audit_query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(receipt["request_url"]).query
        )
        final_query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(receipt["final_url"]).query
        )
        self.assertEqual(transport_query["api_key"], [secret])
        self.assertEqual(transport_query["num"], ["20"])
        self.assertNotIn("api_key", audit_query)
        self.assertNotIn("api_key", final_query)
        self.assertNotIn(secret, ledger)
        self.assertNotIn("api_key", captured["headers"])
        self.assertEqual(receipt["result_count"], 1)
        self.assertEqual(normalized[0]["doi"], "10.1000/scholar-example")
        self.assertEqual(normalized[0]["publication_year"], 2025)
        self.assertEqual(normalized[0]["authors"], ["A Researcher", "B Scientist"])

    def test_serpapi_transport_errors_are_redacted_before_receipt(self) -> None:
        secret = "serpapi-secret-that-must-not-leak"

        def fetcher(url: str, **_kwargs):
            raise OSError(f"HTTP Error 400 for {url}")

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"SERPAPI_API_KEY": secret}, clear=True
        ):
            project = self.project(Path(directory))
            with self.assertRaises(LiteratureEvidenceError) as raised:
                execute_search(
                    project,
                    "serpapi-google-scholar",
                    "machine learning",
                    query_family="supplemental-discovery",
                    date_range="all years",
                    filters="Google Scholar supplemental discovery",
                    limit=1,
                    fetcher=fetcher,
                )
            ledger = (project / "evidence" / "literature-api-ledger.jsonl").read_text()
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, ledger)


if __name__ == "__main__":
    unittest.main()
