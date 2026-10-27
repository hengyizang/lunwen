import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from scripts import literature_zotero as zotero, literature_roles as roles, literature_intelligence as intelligence
from scripts.research_artifacts import write, read, sha


def item(key="ABC12345", title="Fixture bibliography", version=1, **extra):
    return {"key": key, "version": version, "data": {"title": title, "itemType": "journalArticle",
        "date": "2021-03-04", "DOI": "10.1000/fixture", "creators": [{"firstName": "A", "lastName": "Researcher"}], **extra}}


class ZoteroCloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        self.spec = {"schema_version": "1.0", "id": "public", "mode": "web", "library_type": "groups", "library_id": 123, "max_items": 300}

    def test_readonly_web_incremental_deletions_and_private_fields_not_persisted(self):
        pages = [item(), item("DEF67890", "Removed later"), item("NOTE1234", itemType="note", note="PRIVATE NOTE BODY")]
        first = zotero.build(self.project, self.spec, fetch=lambda url, auth: (json.dumps(pages).encode(), 1, 3))
        self.assertEqual(len(first["items"]), 3)
        captured = []
        def updated(url, auth):
            captured.append(url)
            self.assertEqual(parse_qs(urlsplit(url).query)["since"], ["1"])
            if "/deleted?" in url:
                return json.dumps({"items": ["DEF67890"]}).encode(), 2, None
            return json.dumps([item(version=2, title="Changed title")]).encode(), 2, 1
        second = zotero.build(self.project, self.spec, fetch=updated)
        self.assertEqual(second["removed_keys"], ["DEF67890"])
        self.assertEqual(second["changed_keys"], ["ABC12345"])
        self.assertEqual(len(second["items"]), 2)
        self.assertTrue(second["read_only"])
        self.assertTrue(any("/deleted?" in u for u in captured))
        self.assertFalse(any("PRIVATE NOTE BODY" in p.read_text() for p in self.project.rglob("*.json")))
        self.assertEqual(second["paid_calls"], 0)

    def test_pagination_counts_and_concurrent_change_never_commit_partial_index(self):
        calls = []
        def fetch(url, auth):
            calls.append(url)
            rows = [item(f"A{i:07d}") for i in range(100)] if len(calls) == 1 else [item("B1234567")]
            return json.dumps(rows).encode(), len(calls), 101
        with self.assertRaisesRegex(ValueError, "changed during"):
            zotero.build(self.project, self.spec, fetch=fetch)
        self.assertFalse((self.project / zotero.OUTPUT / "public/index.json").exists())

    def test_actual_pagination_accepts_exact_total(self):
        def fetch(url, auth):
            offset = int(parse_qs(urlsplit(url).query)["start"][0])
            rows = [item(f"A{i:07d}") for i in range(offset, min(offset + 100, 101))]
            return json.dumps(rows).encode(), 4, 101
        result = zotero.build(self.project, self.spec, fetch=fetch)
        self.assertEqual(len(result["items"]), 101)
        self.assertEqual(len(result["receipts"]), 2)

    def test_export_import_hash_binding_and_tamper(self):
        path = self.project / "evidence/imports/zotero.json"
        write(path, {"items": [item()]})
        spec = {"schema_version": "1.0", "id": "exported", "mode": "export", "export": {"path": "evidence/imports/zotero.json", "sha256": sha(path)}}
        write(self.project / "program/literature-zotero.json", spec)
        result = zotero.refresh(self.project)
        self.assertIsNone(result["library_version"])
        zotero.validate_saved_report(self.project)
        path.write_text("[]")
        with self.assertRaisesRegex(ValueError, "changed"):
            zotero.validate_saved_report(self.project)

    def test_secret_header_only_and_failed_transport_is_redacted(self):
        class Response:
            headers = {"Last-Modified-Version": "9", "Total-Results": "0"}
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, _): return b"[]"
            def geturl(self): return "https://api.zotero.org/groups/123/items"
        url = "https://api.zotero.org/groups/123/items"
        with patch.dict(os.environ, {"ZOTERO_API_KEY": "private-key-fixture"}), patch.object(zotero, "build_opener") as opener:
            opener.return_value.open.return_value = Response()
            zotero._get(url, True)
            request = opener.return_value.open.call_args.args[0]
            self.assertNotIn("private-key-fixture", request.full_url)
            self.assertEqual(request.get_header("Zotero-api-key"), "private-key-fixture")
            opener.return_value.open.side_effect = OSError("private-key-fixture")
            with self.assertRaisesRegex(ValueError, "permission") as error:
                zotero._get(url, True)
            self.assertNotIn("private-key-fixture", str(error.exception))

    def test_duplicate_incomplete_oversize_and_unsupported_inputs_rejected(self):
        for rows, total in (([item(), item()], 2), ([], 1)):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                zotero.build(self.project, self.spec, fetch=lambda *a: (json.dumps(rows).encode(), 1, total))
        for change in ({"api_key": "do-not-accept"}, {"authenticated": "true"}, {"library_id": "../../elsewhere"}):
            with self.assertRaises(ValueError):
                zotero.build(self.project, {**self.spec, **change})

    def test_cloud_required_and_outputs_cannot_be_edited(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}), self.assertRaisesRegex(ValueError, "cloud"):
            zotero.build(self.project, self.spec)
        zotero.build(self.project, self.spec, fetch=lambda *a: (b"[]", 1, 0))
        (self.project / zotero.OUTPUT / "public/index.html").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            zotero.build(self.project, self.spec, fetch=lambda *a: (b"[]", 1, 0))

    def test_export_registers_metadata_in_actual_shared_search_without_scientific_approval(self):
        source = self.project / "evidence/imports/zotero.json"
        write(source, {"items": [item(title="Distinctive Zotero fixture calibration") ]})
        spec = {"schema_version": "1.0", "id": "registered", "mode": "export", "export": {"path": "evidence/imports/zotero.json", "sha256": sha(source)}}
        request = "program/literature-zotero.json"
        write(self.project / request, spec)
        zotero.refresh(self.project)
        first = zotero.register(self.project, request, "ABC12345")
        second = zotero.register(self.project, request, "ABC12345")
        self.assertTrue(second["reused"])
        self.assertEqual(first["attachment_status"], "metadata_only")
        from scripts import literature_workbench as wb
        found = wb.search(self.project, "Distinctive Zotero calibration")
        self.assertTrue(any(r.get("paper_id") == first["paper_id"] for r in found["results"]))
        self.assertFalse(first["human_screening_approved"])

    def test_changed_implementation_invalidates_incremental_cache(self):
        zotero.build(self.project, self.spec, fetch=lambda *a: (b"[]", 1, 0))
        manifest = self.project / zotero.OUTPUT / "public/manifest.json"
        value = read(manifest)
        value["implementation_sha256"] = "0" * 64
        write(manifest, value)
        from scripts.research_artifacts import record
        record(self.project, [manifest], "scripts/literature_zotero.py")
        with self.assertRaisesRegex(ValueError, "implementation changed"):
            zotero.build(self.project, self.spec, fetch=lambda *a: (b"[]", 1, 0))


class LiteratureRoleTests(unittest.TestCase):
    def test_classification_retains_overlapping_core_adjacent_and_counterevidence(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            write(project / intelligence.PLAN, {"schema_version": "1.0", "doctoral_question": "Which fixture methods transfer?",
                "topic_keywords": ["fixture"], "searches": [{"provider": "semantic-scholar", "query": q, "query_family": q, "limit": 1}
                for q in ("direct", "adjacent", "counterevidence")]})
            def fetch(url, **kwargs):
                return json.dumps({"data": [{"paperId": "one", "title": "Fixture methods", "year": 2021,
                    "authors": [{"name": "Fixture Author"}]}]}).encode(), url, 200, "application/json"
            intelligence.discover(project, fetcher=fetch)
            spec = {"schema_version": "1.0", "leads": {"path": intelligence.OUTPUT, "sha256": sha(project / intelligence.OUTPUT)}}
            write(project / "program/literature-roles.json", spec)
            result = roles.refresh(project)
            self.assertEqual(set(result["items"][0]["roles"]), {"core_candidate", "adjacent_candidate", "counterevidence_candidate"})
            self.assertFalse(result["automatic_scientific_exclusion"])
            roles.validate_saved_report(project)
            target = project / "reports/literature-roles/index.html"
            target.write_text("changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                roles.validate_saved_report(project)
