"""Synthetic row-provenance contracts; run only on the cloud test runner."""
import json
import unittest
from unittest.mock import patch

from scripts import data_row_provenance as provenance
from scripts.research_artifacts import read, sha, write
import tests.test_data_contracts as data_contract_tests


class DataRowProvenanceTests(unittest.TestCase):
    binding = data_contract_tests.DataContractTests.binding
    save = data_contract_tests.DataContractTests.save
    replace_source = data_contract_tests.DataContractTests.replace_source

    def setUp(self):
        data_contract_tests.DataContractTests.setUp(self)
        self.authorize()
        self.declaration = provenance.prepare(self.project, self.dataset, ["id", "year"])

    def authorize(self):
        write(self.project / "state/data-authorizations.json", {"schema_version": "1.0", "manifests": {
            self.spec["manifest"]["path"]: {"sha256": self.spec["manifest"]["sha256"], "actor": "Synthetic owner fixture",
                "source_run_id": "synthetic-no-acquisition", "cloud_use_confirmed": True}}})

    def source_record(self, **changes):
        value = {"url": "https://example.org/statistical-report", "published_at": None,
            "collected_at": "2026-10-26T10:00:00+08:00", "fields": ["value"], "material": {"kind": "dataset_row"}}
        value.update(changes)
        return value

    def located(self):
        for row in self.declaration["records"]:
            row.update(status="located", sources=[self.source_record()])

    def request(self):
        write(self.project / provenance.REQUEST, self.declaration)

    def test_pending_template_covers_all_rows_without_copying_values(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("no acquisition")), patch("scripts.model_runtime.call", side_effect=AssertionError("no paid calls")):
            result = provenance.build(self.project, self.declaration)
        self.assertEqual(result["row_count"], 4)
        self.assertTrue(result["complete_original_row_coverage"])
        self.assertTrue(all(row["status"] == "pending" and not row["sources"] for row in result["rows"]))
        self.assertTrue(all(row["row_sha256"] for row in result["rows"]))
        self.assertNotIn('"value": "100"', json.dumps(result))
        self.assertNotIn("id", result["rows"][0])
        self.assertFalse(result["raw_values_exported"])
        self.assertFalse(result["human_verified"])
        self.assertFalse(result["gate_approved"])
        self.assertTrue(result["digests_are_not_anonymization"])

    def test_located_original_rows_remain_semantically_pending(self):
        self.located()
        original = self.source.read_bytes()
        result = provenance.build(self.project, self.declaration)
        row = result["rows"][0]
        self.assertEqual(row["sources"][0]["material"]["start_line"], 2)
        self.assertEqual(row["sources"][0]["material"]["row_sha256"], row["row_sha256"])
        self.assertFalse(row["sources"][0]["source_semantics_verified"])
        self.assertFalse(row["sources"][0]["source_url_resolved"])
        self.assertEqual(row["fields_without_declared_row_source"], ["id", "year", "treated"])
        self.assertFalse(row["all_fields_have_declared_row_source"])
        self.assertIsNone(row["sources"][0]["published_at"])
        self.assertEqual(self.source.read_bytes(), original)

    def test_no_automatic_human_verified_status(self):
        self.declaration["records"][0]["status"] = "human_verified"
        with self.assertRaisesRegex(ValueError, "no automatic verified"):
            provenance.build(self.project, self.declaration)

    def test_missing_row_cannot_be_silently_omitted(self):
        self.declaration["records"].pop()
        with self.assertRaisesRegex(ValueError, "every original data row"):
            provenance.build(self.project, self.declaration)

    def test_duplicate_row_number_is_rejected_instead_of_replacing_another_row(self):
        self.declaration["records"][1]["row_number"] = 1
        with self.assertRaisesRegex(ValueError, "exactly once"):
            provenance.build(self.project, self.declaration)

    def test_row_hash_cannot_be_swapped_between_same_key_rows(self):
        self.declaration["records"][0]["row_sha256"] = self.declaration["records"][1]["row_sha256"]
        with self.assertRaisesRegex(ValueError, "row fingerprint"):
            provenance.build(self.project, self.declaration)

    def test_duplicate_keys_are_flagged_and_every_row_keeps_a_distinct_identity(self):
        self.declaration["key_columns"] = ["id"]
        result = provenance.build(self.project, self.declaration)
        self.assertEqual(result["duplicate_key_rows"], 4)
        self.assertEqual(len({r["row_id"] for r in result["rows"]}), 4)
        self.assertEqual(result["row_count"], 4)

    def test_no_keys_uses_explicit_version_row_fingerprint_fallback(self):
        self.declaration["key_columns"] = []
        result = provenance.build(self.project, self.declaration)
        self.assertEqual(result["duplicate_key_rows"], 0)
        self.assertTrue(all(r["key_sha256"] is None for r in result["rows"]))
        self.assertEqual(result["row_identity_method"], "source_version_row_number_fingerprint")

    def test_unknown_collection_is_not_inferred_from_dataset_access_date(self):
        self.declaration["records"][0]["sources"] = [self.source_record(collected_at=None)]
        result = provenance.build(self.project, self.declaration)
        self.assertIsNone(result["rows"][0]["sources"][0]["collected_at"])
        self.assertTrue(result["inherited_dataset_source"]["accessed_at"])
        self.declaration["records"][0]["status"] = "located"
        with self.assertRaisesRegex(ValueError, "collection time"):
            provenance.build(self.project, self.declaration)

    def test_publication_date_and_collection_timestamp_are_distinct(self):
        for source in (self.source_record(collected_at="2026-10-26"),
                       self.source_record(published_at="2026-10-27", collected_at="2026-10-26T00:00:00Z")):
            self.declaration["records"][0]["sources"] = [source]
            with self.assertRaises(ValueError):
                provenance.build(self.project, self.declaration)
        self.declaration["records"][0]["sources"] = [self.source_record(published_at="2026-10-26")]
        self.assertEqual(provenance.build(self.project, self.declaration)["rows"][0]["sources"][0]["published_at"], "2026-10-26")

    def test_credentials_and_nonpublic_urls_are_rejected_without_network(self):
        for url in ("http://example.org/report", "https://user:password@example.org/report", "https://example.org/report?token=private", "https://127.0.0.1/report"):
            self.declaration["records"][0]["sources"] = [self.source_record(url=url)]
            with self.subTest(url=url), self.assertRaises((ValueError, RuntimeError)):
                provenance.build(self.project, self.declaration)

    def test_missing_values_require_explicit_reason_and_zero_stays_observed(self):
        self.replace_source("id,year,value,treated\na,2019,,0\na,2020,0,1\n")
        self.authorize()
        self.declaration = provenance.prepare(self.project, self.dataset, ["id", "year"])
        report = provenance.build(self.project, self.declaration)
        self.assertEqual(report["rows"][0]["missing_fields"], ["value"])
        self.assertEqual(report["rows"][1]["missing_fields"], [])
        self.assertEqual(report["rows"][0]["issues"][0]["state"], "unexplained_missing")
        self.declaration["records"][0]["issues"] = []
        with self.assertRaisesRegex(ValueError, "every missing cell"):
            provenance.build(self.project, self.declaration)

    def test_not_accessible_not_published_and_not_applicable_remain_distinct(self):
        for number, state in enumerate(("not_accessible", "not_published", "not_applicable")):
            self.declaration["records"][number]["issues"] = [{"field": "value", "state": state, "reason": "Needs a source-bound explanation."}]
        result = provenance.build(self.project, self.declaration)
        self.assertEqual([r["issues"][0]["state"] for r in result["rows"][:3]], ["not_accessible", "not_published", "not_applicable"])

    def test_conflicting_sources_are_retained_instead_of_becoming_verified(self):
        row = self.declaration["records"][0]
        row.update(status="disputed", sources=[self.source_record(), self.source_record(url="https://example.org/second-report")],
            issues=[{"field": "value", "state": "conflict", "reason": "The source definitions differ and need review."}])
        result = provenance.build(self.project, self.declaration)
        self.assertEqual(len(result["rows"][0]["sources"]), 2)
        self.assertEqual(result["rows"][0]["status"], "disputed")
        self.assertFalse(result["rows"][0]["human_verified"])
        row["status"] = "located"
        with self.assertRaisesRegex(ValueError, "unresolved ambiguity"):
            provenance.build(self.project, self.declaration)

    def test_current_owner_rights_required_before_raw_row_processing(self):
        write(self.project / "state/data-authorizations.json", {"manifests": {}})
        with self.assertRaisesRegex(ValueError, "owner-authorized"):
            provenance.build(self.project, self.declaration)

    def test_raw_bytes_and_manifest_version_changes_block_reuse(self):
        self.request()
        provenance.refresh(self.project)
        self.source.write_text(self.source.read_text() + "c,2020,0,0\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source hash changed"):
            provenance.validate_saved_report(self.project)

    def test_report_is_bound_to_dictionary_and_request(self):
        self.request()
        provenance.refresh(self.project)
        self.assertTrue(provenance.validate_saved_report(self.project)["valid"])
        self.spec["variables"][0]["definition"] = "Changed variable meaning"
        self.save()
        with self.assertRaisesRegex(ValueError, "dictionary"):
            provenance.validate_saved_report(self.project)

    def test_unrelated_owner_authorization_does_not_invalidate_exact_permission(self):
        self.request()
        provenance.refresh(self.project)
        value = read(self.project / "state/data-authorizations.json")
        value["manifests"]["data/manifests/other.json"] = {"sha256": "f" * 64}
        write(self.project / "state/data-authorizations.json", value)
        self.assertTrue(provenance.validate_saved_report(self.project)["valid"])

    def test_saved_csv_tampering_is_detected(self):
        self.request()
        result = provenance.refresh(self.project)
        (self.project / result["csv"]).write_text("forged row\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source hash changed"):
            provenance.validate_saved_report(self.project)

    def test_csv_is_formula_safe(self):
        for value in ("=1+1", "+1", "-1", "@SUM(A1)", " \t=2"):
            self.assertTrue(provenance._csv_cell(value).startswith("'"))
        self.assertEqual(provenance._csv_cell("https://example.org"), "https://example.org")

    def literature_source(self, *, note=False):
        from scripts import literature_workbench
        source = self.project / "evidence/original/report.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("The source reported a positive change under fixed conditions.\n", encoding="utf-8")
        paper = {"id": "report", "source": self.binding(source), "title": "Synthetic source report"}
        target = source
        if note:
            target = self.project / "evidence/notes/report.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Generated interpretation is not original evidence.\n", encoding="utf-8")
            paper["notes"] = [self.binding(target)]
        write(self.project / "program/literature-workbench.json", {"schema_version": "1.0", "papers": [paper]})
        literature_workbench.build(self.project)
        return {"kind": "literature", "paper_id": "report", "anchor": {**self.binding(target),
            "start_line": 1, "end_line": 1, "quote": target.read_text(encoding="utf-8").strip()}}, target

    def test_original_literature_location_is_bound_without_republishing_its_quote(self):
        material, target = self.literature_source()
        self.declaration["records"][0].update(status="located", sources=[self.source_record(material=material)])
        report = provenance.build(self.project, self.declaration)
        bound = report["rows"][0]["sources"][0]["material"]
        self.assertIn("quote_sha256", bound)
        self.assertNotIn("quote", bound)
        self.assertFalse(bound["source_semantics_verified"])
        target.write_text("Changed scientific source.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            provenance.build(self.project, self.declaration)

    def test_generated_notes_cannot_substitute_for_original_source_material(self):
        material, _ = self.literature_source(note=True)
        self.declaration["records"][0]["sources"] = [self.source_record(material=material)]
        with self.assertRaisesRegex(ValueError, "original material"):
            provenance.build(self.project, self.declaration)

    def test_multiline_csv_retains_physical_line_ranges(self):
        self.replace_source('id,year,value,treated\n"a\nA",2019,100,0\nb,2020,0,0\n')
        self.authorize()
        report = provenance.build(self.project, provenance.prepare(self.project, self.dataset, []))
        self.assertEqual((report["rows"][0]["csv_line_start"], report["rows"][0]["csv_line_end"]), (2, 3))
        self.assertEqual((report["rows"][1]["csv_line_start"], report["rows"][1]["csv_line_end"]), (4, 4))

    def test_request_paths_cannot_read_private_control_files(self):
        with self.assertRaisesRegex(ValueError, "belongs"):
            provenance.refresh(self.project, "state/data-authorizations.json")
