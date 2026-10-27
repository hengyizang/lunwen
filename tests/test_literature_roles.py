"""Receipt, query-family and source-work bindings for discovery-only roles."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import literature_roles as roles, literature_intelligence as intelligence
from scripts.research_artifacts import write, read, record, sha


class LiteratureRoleBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        write(self.project / intelligence.PLAN, {"schema_version": "1.0",
            "doctoral_question": "Which transfer protocol works?", "topic_keywords": ["transfer"],
            "searches": [{"provider": "semantic-scholar", "query": family, "query_family": family, "limit": 2}
                for family in ("direct", "adjacent", "counterevidence")]})
        def fetch(url, **kwargs):
            return json.dumps({"data": [{"paperId": key, "title": title, "year": 2021,
                "authors": [{"name": "Fixture Author " + key}]} for key, title in
                (("one", "Transfer protocol one"), ("two", "Different method two"))]}).encode(), url, 200, "application/json"
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            intelligence.discover(self.project, fetcher=fetch)
        self.leads = self.project / intelligence.OUTPUT
        self.ledger = self.project / "evidence/literature-api-ledger.jsonl"
        self.search_log = self.project / "evidence/search-log.jsonl"

    def spec(self):
        return {"schema_version": "1.0", "leads": {"path": intelligence.OUTPUT, "sha256": sha(self.leads)}}

    def mutate_leads(self, change):
        value = read(self.leads)
        change(value)
        write(self.leads, value)
        # A fixture of a controlled-but-inconsistent producer; source identity
        # checks must still block it rather than relying only on this marker.
        record(self.project, [self.leads], "scripts/literature_intelligence.py")

    def jsonl(self, path, values):
        path.write_text("".join(json.dumps(v) + "\n" for v in values), encoding="utf-8")

    def test_actual_receipts_preserve_all_overlapping_query_roles(self):
        result = roles.build(self.project, self.spec())
        self.assertEqual(len(result["items"]), 2)
        for item in result["items"]:
            self.assertEqual(set(item["roles"]), {"core_candidate", "adjacent_candidate", "counterevidence_candidate"})
            self.assertIsNone(item["inclusion_decision"])
        self.assertFalse(result["automatic_scientific_exclusion"])

    def test_duplicate_ledger_receipt_is_rejected_instead_of_last_row_wins(self):
        rows = intelligence.evidence.read_jsonl(self.ledger)
        self.jsonl(self.ledger, rows + [rows[0]])
        with self.assertRaisesRegex(ValueError, "unique actual"):
            roles.build(self.project, self.spec())

    def test_lead_receipt_old_hash_cannot_bind_a_replaced_actual_receipt(self):
        self.mutate_leads(lambda value: value["source_receipts"][0].update(response_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "receipt binding differs"):
            roles.build(self.project, self.spec())

    def test_repeated_lead_receipt_is_not_a_second_route(self):
        self.mutate_leads(lambda value: value["source_receipts"].append(copy.deepcopy(value["source_receipts"][0])))
        with self.assertRaisesRegex(ValueError, "repeated"):
            roles.build(self.project, self.spec())

    def test_candidate_locator_must_exist_in_exact_normalized_receipt(self):
        self.mutate_leads(lambda value: value["candidates"][0]["source_refs"][0].update(locator="works[999]"))
        with self.assertRaisesRegex(ValueError, "source locator/hash"):
            roles.build(self.project, self.spec())

    def test_candidate_ref_hash_cannot_be_replaced_by_valid_receipt_id_only(self):
        self.mutate_leads(lambda value: value["candidates"][0]["source_refs"][0].update(normalized_results_sha256="f" * 64))
        with self.assertRaisesRegex(ValueError, "source locator/hash"):
            roles.build(self.project, self.spec())

    def test_actual_locator_for_different_work_cannot_lend_query_roles(self):
        def substitute(value):
            candidate = value["candidates"][0]
            other = value["candidates"][1]
            candidate["source_refs"] = copy.deepcopy(other["source_refs"])
        self.mutate_leads(substitute)
        with self.assertRaisesRegex(ValueError, "candidate identity differs"):
            roles.build(self.project, self.spec())

    def test_duplicate_candidate_refs_are_not_counted_as_more_evidence(self):
        self.mutate_leads(lambda value: value["candidates"][0]["source_refs"].append(copy.deepcopy(value["candidates"][0]["source_refs"][0])))
        with self.assertRaisesRegex(ValueError, "source locator/hash"):
            roles.build(self.project, self.spec())

    def test_same_query_text_with_other_receipt_cannot_supply_family(self):
        rows = intelligence.evidence.read_jsonl(self.search_log)
        for row in rows:
            row["evidence_receipt_id"] = "not-the-actual-receipt"
        self.jsonl(self.search_log, rows)
        result = roles.build(self.project, self.spec())
        self.assertTrue(all(item["roles"] == ["unclassified_candidate"] for item in result["items"]))

    def test_search_log_hash_mismatch_cannot_supply_family(self):
        rows = intelligence.evidence.read_jsonl(self.search_log)
        for row in rows:
            row["response_sha256"] = "0" * 64
        self.jsonl(self.search_log, rows)
        result = roles.build(self.project, self.spec())
        self.assertTrue(all(item["roles"] == ["unclassified_candidate"] for item in result["items"]))

    def test_conflicting_families_for_identical_receipt_remain_unclassified(self):
        rows = intelligence.evidence.read_jsonl(self.search_log)
        extra = copy.deepcopy(rows[0])
        extra["query_family"] = "counterevidence" if rows[0]["query_family"] != "counterevidence" else "direct"
        self.jsonl(self.search_log, rows + [extra])
        result = roles.build(self.project, self.spec())
        target = rows[0]["evidence_receipt_id"]
        self.assertTrue(all(next(r for r in item["routes"] if r["receipt_id"] == target)["role"] == "unclassified_candidate"
            for item in result["items"]))


if __name__ == "__main__":
    unittest.main()
