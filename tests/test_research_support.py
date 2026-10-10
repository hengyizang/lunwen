"""Synthetic source-bound controls; no real scientific results or provider calls."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from scripts import research_support as support, source_scope, cloud_checkpoint
from scripts.research_artifacts import sha, write


class ResearchSupportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        for name in ("program", "evidence", "data"):
            (self.project / name).mkdir()
        self.primary = self.project / "evidence/method.txt"
        self.primary.write_text("The method uses paired means. A difference is illustrated by 3 - 1 = 2.\n", encoding="utf-8")

    def put(self, **sections):
        write(self.project / support.INPUT, {"schema_version": "1.0", **sections})

    def anchor(self, path="evidence/method.txt", quote="The method uses paired means."):
        return {"path": path, "sha256": sha(self.project / path), "locator": "L1", "quote": quote}

    def clarification(self):
        return {"id": "Q1", "question": "What synthetic estimand should the plan evaluate?",
                "estimand": {key: "Provisional explicit " + key for key in support.ESTIMAND},
                "assumptions": [{"status": "proposed", "statement": "The example units are independent.",
                                 "failure_consequence": "The variance calculation must change."}],
                "boundaries": {"included": ["Synthetic benchmark units"], "excluded": ["Causal conclusions"],
                               "inference_ceiling": "Illustration only; no observed experimental claim."},
                "pending_owner_questions": [{"id": "O1", "question": "Which population is intended?",
                    "choices": ["Benchmark population", "External population"], "status": "pending_owner"}]}

    def method(self, full=True, documented=True):
        primary = {"path": "evidence/method.txt", "sha256": sha(self.primary)}
        row = {"id": "M1", "primary_source": primary, "source_scope": "full_text" if full else "abstract",
               "methods_assessed": full, "fields": {key: {"status": "source_statement",
                   "value": "Provisional interpretation of " + key, "boundary": "Source presence does not establish validity.",
                   "evidence": [self.anchor()]} for key in support.METHOD_FIELDS},
               "worked_example": {"status": "pending", "reason": "No calculation record supplied yet."}}
        if full:
            receipt = source_scope.record(self.project, primary["path"], "full_text", "Named Human Reviewer")
            row["scope_record"] = {"path": receipt.relative_to(self.project).as_posix(), "sha256": sha(receipt)}
        if documented:
            target = self.project / "evidence/illustration.json"
            write(target, {"schema_version": "1.0", "problem": "Synthetic subtraction illustration.",
                "input_origin": "synthetic_illustration", "scientific_limit": "Not experimental evidence.",
                "inputs": {"a": 3, "b": 1}, "steps": [{"name": "difference", "expression": "a - b",
                    "result": 2, "reason": "Subtract the second toy value from the first."}]})
            row["worked_example"] = {"status": "documented", "record": {"path": "evidence/illustration.json", "sha256": sha(target)},
                                      "method_anchor": self.anchor()}
        return row

    def metadata(self, count=1, mime="text/plain", now=None):
        now = now or datetime.now(timezone.utc)
        urls = ["https://repo.example/records/demo" + str(i) for i in range(count)]
        plan = [{"url": url, "purpose": "public_metadata", "official_domains": ["repo.example"]} for url in urls]
        self.put(metadata_sources=plan)
        calls = []
        payload = b"Identifier: demo0. Version: v1. Access: restricted. License: CC-BY-4.0. Metadata uses JSON-LD."
        def fetch(url, **kwargs):
            calls.append((url, kwargs))
            return payload, url, 200, mime
        ledger = support.fetch_sources(self.project, fetcher=fetch, now=now)
        return plan, ledger, calls, now

    def availability(self, receipt):
        manifest = {"schema_version": "1.0", "dataset_id": "d1", "title": "Synthetic manifest fixture", "provider": "Fixture",
            "source_url": "https://repo.example/records/demo0", "version": "v1", "accessed_at": "2026-10-10",
            "license": {"name": "CC-BY-4.0", "url": "https://repo.example/license", "research_use_allowed": True,
                        "redistribution_allowed": False, "confirmed_by_human": True},
            "download": {"url": "https://repo.example/data", "sha256": "pending", "expected_bytes": None},
            "provenance": {"collection_method": "Synthetic test fixture", "transformations": []},
            "unit_of_analysis": "Synthetic unit", "split_strategy": "Not executed", "known_limitations": ["Not real data"]}
        (self.project / "data/datasets.jsonl").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        anchor = lambda quote: self.anchor(receipt["path"], quote)
        return {"dataset_id": "d1", "version": "v1", "access_mode": "restricted",
            "fair": {key: {"status": "source_statement", "value": "Provisional metadata assessment: " + key,
                "boundary": "Metadata only; no data-content verification.", "evidence": [anchor("Metadata uses JSON-LD.")]} for key in support.FAIR},
            "deposit": {"status": "record_observed", "url": receipt["url"], "identifier": "demo0", "version": "v1",
                "access_label": "restricted", "identifier_anchor": anchor("Identifier: demo0."),
                "version_anchor": anchor("Version: v1."), "access_anchor": anchor("Access: restricted."),
                "license_anchor": anchor("License: CC-BY-4.0.")}}

    def test_absent_inputs_remain_pending(self):
        result = support.refresh(self.project)
        self.assertEqual(result["status"], "pending_inputs")
        self.assertFalse(result["scientific_completion_verified"])
        self.assertFalse(result["publishing_authorized"])
        self.assertEqual(result["paid_calls"], 0)

    def test_clarification_preserves_pending_owner_questions(self):
        self.put(clarifications=[self.clarification()])
        result = support.audit(self.project)
        self.assertEqual(result["status"], "pending_inputs", result)
        self.assertFalse(result["clarifications"][0]["owner_approval_inferred"])
        self.assertTrue(any("owner question O1" in item for item in result["pending_inputs"]))

    def test_clarification_rejects_missing_estimand_and_inferred_approval(self):
        for mutation in ("missing", "answered", "approved", "conflict"):
            with self.subTest(mutation=mutation):
                row = self.clarification()
                if mutation == "missing":
                    row["estimand"].pop("population")
                elif mutation == "answered":
                    row["pending_owner_questions"][0]["status"] = "answered"
                elif mutation == "approved":
                    row["assumptions"][0]["status"] = "owner_confirmed"
                else:
                    row["boundaries"]["excluded"] = list(row["boundaries"]["included"])
                self.put(clarifications=[row])
                self.assertEqual(support.audit(self.project)["status"], "blocked")

    def test_full_text_and_arithmetic_are_bound_without_certification(self):
        self.put(method_dissections=[self.method()])
        result = support.refresh(self.project)
        self.assertEqual(result["status"], "needs_scientific_review", result)
        row = result["method_dissections"][0]
        self.assertTrue(row["supplied_scope_confirmed"])
        self.assertEqual(row["human_read_scope"], "not_declared")
        self.assertTrue(row["worked_example"]["arithmetic_checked"])
        self.assertFalse(row["worked_example"]["method_validated"])
        self.assertFalse(row["worked_example"]["experiment_result"])
        self.assertEqual(support.validate_saved_report(self.project), [])

    def test_partial_text_cannot_establish_assessed_methods_or_forged_scope(self):
        row = self.method(full=False, documented=False)
        row["methods_assessed"] = True
        self.put(method_dissections=[row])
        self.assertEqual(support.audit(self.project)["status"], "blocked")
        row["methods_assessed"] = False
        self.put(method_dissections=[row])
        self.assertEqual(support.audit(self.project)["status"], "pending_inputs")
        row["source_scope"] = "full_text"
        self.put(method_dissections=[row])
        self.assertEqual(support.audit(self.project)["status"], "blocked")

    def test_method_requires_actual_primary_locations_and_hashes(self):
        for mutation in ("line", "quote", "hash", "primary"):
            row = self.method()
            anchor = row["fields"]["analysis"]["evidence"][0]
            if mutation == "line":
                anchor["locator"] = "L9"
            elif mutation == "quote":
                anchor["quote"] = "Invented source statement."
            elif mutation == "hash":
                anchor["sha256"] = "0" * 64
            else:
                other = self.project / "evidence/other.txt"
                other.write_text("The method uses paired means.\n")
                anchor.update(path="evidence/other.txt", sha256=sha(other))
            self.put(method_dissections=[row])
            self.assertEqual(support.audit(self.project)["status"], "blocked", mutation)

    def test_bad_arithmetic_and_code_expressions_fail(self):
        row = self.method()
        target = self.project / "evidence/illustration.json"
        value = json.loads(target.read_text())
        value["steps"][0]["result"] = 9
        write(target, value)
        row["worked_example"]["record"]["sha256"] = sha(target)
        self.put(method_dissections=[row])
        self.assertEqual(support.audit(self.project)["status"], "blocked")
        for expression in ('__import__("os")', "a.__class__", "a[0]", "a ** 999", "a / 0", "True + a"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                support._arithmetic(expression, {"a": support._number(3)})

    def test_metadata_fetch_bounded_cached_and_checkpoint_safe(self):
        plan, ledger, calls, now = self.metadata(count=11)
        self.assertEqual(len(calls), 10)
        self.assertEqual(len(ledger["pending_urls"]), 1)
        self.assertEqual(ledger["paid_calls"], 0)
        self.assertFalse(ledger["publishing_authorized"])
        self.assertTrue(all(Path(item["path"]).suffix in cloud_checkpoint.GIT_SUFFIXES for item in cloud_checkpoint.inventory(self.project)))
        self.put(metadata_sources=[plan[0]])
        def forbidden(*args, **kwargs):
            raise AssertionError("Fresh cached metadata must not make another request")
        cached = support.fetch_sources(self.project, fetcher=forbidden, now=now + timedelta(hours=1))
        self.assertEqual(cached["fetched_this_operation"], 0)

    def test_binary_fetch_cooldown_and_unsafe_urls(self):
        plan, ledger, calls, now = self.metadata(mime="application/octet-stream")
        self.assertEqual(ledger["sources"][plan[0]["url"]]["status"], "unavailable")
        def forbidden(*args, **kwargs):
            raise AssertionError("Failure cooldown must not make another request")
        self.assertEqual(support.fetch_sources(self.project, fetcher=forbidden, now=now + timedelta(hours=1))["fetched_this_operation"], 0)
        for url in ("http://repo.example/m", "https://127.0.0.1/m", "https://localhost/m", "https://repo.example/m?api_key=secret", "https://repo.example/data.csv", "https://api.openai.com/v1/responses"):
            with self.subTest(url=url), self.assertRaises((ValueError, RuntimeError)):
                support._url(url)

    def test_restricted_fair_metadata_is_not_upload_or_open_certification(self):
        plan, ledger, calls, now = self.metadata()
        row = self.availability(ledger["sources"][plan[0]["url"]])
        self.put(metadata_sources=plan, data_availability=[row])
        result = support.refresh(self.project)
        self.assertEqual(result["status"], "needs_scientific_review", result)
        observed = result["data_availability"][0]
        self.assertTrue(observed["metadata_record_observed"])
        for key in ("fair_requires_unrestricted_open_access", "fair_certified", "upload_ownership_verified", "data_files_retrieved_or_verified", "publishing_authorized"):
            self.assertFalse(observed[key])
        self.assertEqual(support.validate_saved_report(self.project), [])
        for mutation in ("version", "identifier", "quote", "uploaded", "access"):
            altered = copy.deepcopy(row)
            if mutation == "version":
                altered["deposit"]["version"] = "v2"
            elif mutation == "identifier":
                altered["deposit"]["identifier"] = "invented"
            elif mutation == "quote":
                altered["deposit"]["license_anchor"]["quote"] = "Invented permission."
            elif mutation == "uploaded":
                altered["deposit"]["uploaded"] = True
            else:
                altered["access_mode"] = "open"
            self.put(metadata_sources=plan, data_availability=[altered])
            self.assertEqual(support.audit(self.project)["status"], "blocked", mutation)
        self.put(metadata_sources=plan, data_availability=[row])
        self.assertEqual(support.audit(self.project, now=now + timedelta(days=8))["status"], "blocked")

    def test_planned_deposits_and_source_changes_stay_pending_or_fail(self):
        plan, ledger, calls, now = self.metadata()
        row = self.availability(ledger["sources"][plan[0]["url"]])
        row["deposit"] = {"status": "planned", "reason": "No real repository record deposited."}
        self.put(data_availability=[row])
        self.assertEqual(support.audit(self.project)["status"], "pending_inputs")
        self.put(method_dissections=[self.method()])
        support.refresh(self.project)
        self.primary.write_text("Changed source.\n")
        self.assertTrue(support.validate_saved_report(self.project))


if __name__ == "__main__":
    unittest.main()
