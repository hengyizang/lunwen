"""Closest-work location/identity regressions; all study content is synthetic.

Run on the cloud validation runner. These checks neither conduct experiments
nor verify the scientific interpretation, novelty or benefit of an approach.
"""
import copy
import tempfile
import unittest
from pathlib import Path

from scripts import research_extensions as extensions
from scripts.research_artifacts import read, sha, write


class ClosestWorkAxesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.own_path = "papers/P01/experiments/observations.txt"
        self.prior_path = "literature/sources/nearest.txt"
        self.text(self.own_path, "Synthetic population at Site A.\nFrozen synthetic classifier.\nObserved synthetic AUROC 0.78.\n")
        self.text(self.prior_path, "Synthetic population at Site A.\nFixed synthetic classifier.\nReported synthetic AUROC 0.75.\nDataset: cohort\nMetric: AUROC\nEvaluation: heldout-site-A\nVersion: v1\n")
        self.protocol_path = "papers/P01/experiment-evidence-plan.json"
        write(self.project / self.protocol_path, {"paper_id": "P01", "comparisons": [
            {"comparison_id": "synthetic-contrast", "claim_ids": ["C1"], "dataset_id": "cohort", "metric": "AUROC"}]})
        self.manifest_path = "data/manifests/cohort.json"
        write(self.project / self.manifest_path, {"dataset_id": "cohort", "version": "v1", "split_strategy": "heldout-site-A"})
        write(self.project / "program/novelty-claim-matrix.json", {"schema_version": "1.0", "claims": [
            {"claim_id": "C1", "paper_ids": ["P01"], "closest_work_ids": ["W1", "W2", "W3"]}]})
        write(self.project / "program/originality-audit.json", {"schema_version": "1.0", "closest_prior_work": [
            {"id": "W1", "title": "Synthetic nearest work", "primary_source_url": "https://example.org/nearest"}]})
        write(self.project / "program/literature-workbench.json", {"schema_version": "1.0", "papers": [
            {"id": "library-1", "title": "Synthetic nearest work", "url": "https://example.org/nearest",
             "source_scope": "full_text", "source": self.binding(self.prior_path)}]})

    def text(self, relative, value):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def binding(self, relative):
        return {"path": relative, "sha256": sha(self.project / relative), "locator": "synthetic fixture source"}

    def anchor(self, relative, number):
        return {**self.binding(relative), "start_line": number, "end_line": number,
                "quote": (self.project / relative).read_text(encoding="utf-8").splitlines()[number - 1]}

    def fixture(self):
        conditions = {key: "matched synthetic evaluation condition" for key in extensions.DIMENSIONS}
        row = {"id": "nearest-C1-W1", "question": "Which exact contribution differs from synthetic W1?",
               "disposition": "comparable", "left": {"conditions": copy.deepcopy(conditions),
                    "evidence": [{**self.binding(self.own_path), "quote": "Observed synthetic AUROC 0.78."}]},
               "right": {"conditions": copy.deepcopy(conditions),
                    "evidence": [{**self.binding(self.prior_path), "quote": "Reported synthetic AUROC 0.75."}]}}
        axes = {}
        for name, number in (("research_object", 1), ("method", 2), ("result", 3)):
            axes[name] = {"scope": "Synthetic cohort and protocol scope only",
                "comparison_basis": "Locate corresponding statements; scientist must assess their meaning",
                "disposition": "comparable", "conclusion_kind": "descriptive",
                "ours": {"status": "reported", "value": self.anchor(self.own_path, number)["quote"],
                         "scope": "Site A synthetic fixture", "evidence": [self.anchor(self.own_path, number)]},
                "prior": {"status": "reported", "value": self.anchor(self.prior_path, number)["quote"],
                          "scope": "Site A synthetic fixture", "evidence": [self.anchor(self.prior_path, number)]}}
        result = axes["result"]
        result["result_kind"] = "quantitative"
        protocol = read(self.project / self.protocol_path)["comparisons"][0]
        manifest = read(self.project / self.manifest_path)
        result["ours"]["evaluation"] = {
            "dataset_id": {**self.binding(self.protocol_path), "pointer": "/comparisons/0/dataset_id", "value": protocol["dataset_id"]},
            "dataset_version": {**self.binding(self.manifest_path), "pointer": "/version", "value": manifest["version"]},
            "metric_definition": {**self.binding(self.protocol_path), "pointer": "/comparisons/0/metric", "value": protocol["metric"]},
            "evaluation_basis": {**self.binding(self.manifest_path), "pointer": "/split_strategy", "value": manifest["split_strategy"]}}
        result["prior"]["evaluation"] = {key: {**self.anchor(self.prior_path, number), "value": value}
            for key, number, value in (("dataset_id", 4, "cohort"), ("dataset_version", 7, "v1"), ("metric_definition", 5, "AUROC"),
                                       ("evaluation_basis", 6, "heldout-site-A"))}
        row["closest_work"] = {"paper_id": "P01", "claim_id": "C1", "work_id": "W1",
            "library_work_id": "library-1", "context": {
                name: self.binding(relative) for name, relative in extensions.CLOSEST_CONTEXT.items()}, "axes": axes}
        return row

    def update_context(self, row, key, value):
        relative = extensions.CLOSEST_CONTEXT[key]
        write(self.project / relative, value)
        row["closest_work"]["context"][key] = self.binding(relative)

    def test_legacy_comparison_is_retained_but_axes_are_not_assessed(self):
        row = self.fixture()
        row.pop("closest_work")
        result = extensions.comparison(self.project, row)
        self.assertEqual(result["closest_work_axis_check"], "not_assessed")
        self.assertFalse(result["comparability_verified"])

    def test_source_bound_three_axes_keep_all_scientific_decisions_unverified(self):
        result = extensions.comparison(self.project, self.fixture())
        closest = result["closest_work"]
        self.assertEqual(result["closest_work_axis_check"], "source_bound")
        self.assertTrue(closest["record_complete"])
        self.assertEqual(closest["pending_axes"], [])
        self.assertEqual(closest["claim_id"], "C1")
        self.assertEqual(closest["work_id"], "W1")
        self.assertFalse(closest["scientific_comparability_verified"])
        self.assertFalse(closest["novelty_verified"])
        self.assertTrue(closest["independent_review_required"])
        self.assertTrue(closest["axes"]["result"]["same_bound_evaluation_values"])
        for axis in closest["axes"].values():
            self.assertFalse(axis["semantic_support_verified"])
            self.assertFalse(axis["comparability_verified"])

    def test_missing_axis_cannot_pass_source_location_check(self):
        row = self.fixture()
        row["closest_work"]["axes"].pop("method")
        with self.assertRaisesRegex(ValueError, "cover research_object"):
            extensions.comparison(self.project, row)

    def test_unknown_and_not_reported_remain_honest_complete_records(self):
        for status in ("unknown", "not_reported"):
            row = self.fixture()
            axis = row["closest_work"]["axes"]["result"]
            axis.update(disposition="insufficient_evidence", conclusion_kind="none")
            axis["prior"] = {"status": status, "scope": "No directly matching result is located",
                "evidence": [], "missing_reason": "Need scientific review of full-text scope and omitted outcome"}
            checked = extensions.comparison(self.project, row)["closest_work"]
            self.assertTrue(checked["record_complete"])
            self.assertEqual(checked["source_location_check"], "needs_inputs")
            self.assertIn("result.prior", checked["pending_axes"])
            axis["conclusion_kind"] = "superiority"
            with self.assertRaisesRegex(ValueError, "unknown/not_reported"):
                extensions.comparison(self.project, row)

    def test_proposed_theory_does_not_need_an_invented_empirical_metric(self):
        row = self.fixture()
        axis = row["closest_work"]["axes"]["result"]
        axis.update(result_kind="theoretical", disposition="not_comparable")
        for arm in ("ours", "prior"):
            axis[arm].pop("evaluation")
        checked = extensions.comparison(self.project, row)["closest_work"]
        self.assertEqual(checked["axes"]["result"]["result_kind"], "theoretical")
        self.assertIsNone(checked["axes"]["result"]["same_bound_evaluation_values"])
        self.assertFalse(checked["novelty_verified"])

    def test_planned_own_result_cannot_be_claimed_observed(self):
        row = self.fixture()
        axis = row["closest_work"]["axes"]["result"]
        axis.update(disposition="insufficient_evidence", conclusion_kind="none")
        axis["ours"].pop("evaluation")
        axis["ours"]["status"] = "planned"
        axis["ours"]["evidence"] = [self.anchor(self.protocol_path, 2)]
        checked = extensions.comparison(self.project, row)["closest_work"]
        self.assertEqual(checked["source_location_check"], "needs_inputs")
        axis["ours"]["status"] = "reported"
        with self.assertRaisesRegex(ValueError, "not an observed result"):
            extensions.comparison(self.project, row)

    def test_changed_matrix_library_and_originality_bindings_are_invalidated(self):
        for key, relative in extensions.CLOSEST_CONTEXT.items():
            row = self.fixture()
            original = (self.project / relative).read_bytes()
            (self.project / relative).write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "hash"):
                extensions.comparison(self.project, row)
            (self.project / relative).write_bytes(original)

    def test_fresh_hash_cannot_rebind_to_an_unrelated_claim_work_or_paper(self):
        for field, bad in (("claim_id", "C-missing"), ("work_id", "W-missing"), ("paper_id", "P02")):
            row = self.fixture()
            row["closest_work"][field] = bad
            with self.assertRaisesRegex(ValueError, "relationship"):
                extensions.comparison(self.project, row)

    def test_library_primary_url_and_full_text_scope_are_required(self):
        for field, value in (("url", "https://example.org/unrelated"), ("source_scope", "metadata_only")):
            row = self.fixture()
            library = read(self.project / extensions.CLOSEST_CONTEXT["literature_library"])
            library["papers"][0][field] = value
            self.update_context(row, "literature_library", library)
            with self.assertRaisesRegex(ValueError, "primary-source|full_text"):
                extensions.comparison(self.project, row)
            library["papers"][0][field] = "https://example.org/nearest" if field == "url" else "full_text"
            self.update_context(row, "literature_library", library)

    def test_an_unread_metadata_lead_can_only_preserve_explicit_unknowns(self):
        row = self.fixture()
        library = read(self.project / extensions.CLOSEST_CONTEXT["literature_library"])
        library["papers"][0]["source_scope"] = "metadata_only"
        self.update_context(row, "literature_library", library)
        for axis in row["closest_work"]["axes"].values():
            axis.update(disposition="insufficient_evidence", conclusion_kind="none")
            axis["prior"] = {"status": "unknown", "scope": "Only a metadata lead is available",
                "evidence": [], "missing_reason": "Authorized full text has not yet been acquired"}
        checked = extensions.comparison(self.project, row)["closest_work"]
        self.assertTrue(checked["record_complete"])
        self.assertEqual(checked["source_location_check"], "needs_inputs")
        self.assertEqual(len(checked["pending_axes"]), 3)

    def test_prior_notes_and_own_reviews_cannot_replace_original_evidence(self):
        row = self.fixture()
        self.text("literature/notes/nearest.txt", "Convenient unsupported interpretation.")
        row["closest_work"]["axes"]["method"]["prior"]["evidence"] = [self.anchor("literature/notes/nearest.txt", 1)]
        with self.assertRaisesRegex(ValueError, "original source"):
            extensions.comparison(self.project, row)
        row = self.fixture()
        self.text("papers/P01/reviews/self.txt", "Convenient self-review verdict.")
        row["closest_work"]["axes"]["method"]["ours"]["evidence"] = [self.anchor("papers/P01/reviews/self.txt", 1)]
        with self.assertRaisesRegex(ValueError, "not its manuscript/review"):
            extensions.comparison(self.project, row)

    def test_quotes_must_be_at_the_actual_lines_and_sources_must_be_current(self):
        row = self.fixture()
        row["closest_work"]["axes"]["method"]["ours"]["evidence"][0]["start_line"] = 1
        row["closest_work"]["axes"]["method"]["ours"]["evidence"][0]["end_line"] = 1
        with self.assertRaisesRegex(ValueError, "specified source lines"):
            extensions.comparison(self.project, row)
        row = self.fixture()
        self.text(self.own_path, "Changed source after review.")
        with self.assertRaisesRegex(ValueError, "hash"):
            extensions.comparison(self.project, row)

    def test_changed_protocol_hash_and_invented_evaluation_values_fail(self):
        row = self.fixture()
        protocol = read(self.project / self.protocol_path)
        protocol["comparisons"][0]["metric"] = "accuracy"
        write(self.project / self.protocol_path, protocol)
        with self.assertRaisesRegex(ValueError, "hash"):
            extensions.comparison(self.project, row)
        for field, item in row["closest_work"]["axes"]["result"]["ours"]["evaluation"].items():
            if item["path"] == self.protocol_path:
                item.update(self.binding(self.protocol_path))
        with self.assertRaisesRegex(ValueError, "differs from its actual"):
            extensions.comparison(self.project, row)

    def test_evaluation_requires_actual_named_protocol_fields_not_a_freestanding_claim(self):
        row = self.fixture()
        fake = "papers/P01/reviews/evaluation.json"
        write(self.project / fake, read(self.project / self.protocol_path))
        item = row["closest_work"]["axes"]["result"]["ours"]["evaluation"]["metric_definition"]
        item.update(self.binding(fake))
        with self.assertRaisesRegex(ValueError, "actual paper protocol/result"):
            extensions.comparison(self.project, row)
        item.update(self.binding(self.protocol_path))
        item["pointer"] = "/paper_id"
        item["value"] = "P01"
        with self.assertRaisesRegex(ValueError, "actual dataset, metric or evaluation field"):
            extensions.comparison(self.project, row)

    def test_two_numbers_cannot_establish_cross_dataset_or_cross_metric_benefit(self):
        for field, changed in (("dataset_id", "different-cohort"), ("dataset_version", "v2"), ("metric_definition", "accuracy"),
                               ("evaluation_basis", "training-set")):
            row = self.fixture()
            protocol = read(self.project / self.protocol_path)
            manifest = read(self.project / self.manifest_path)
            original_protocol, original_manifest = copy.deepcopy(protocol), copy.deepcopy(manifest)
            if field == "dataset_id":
                protocol["comparisons"][0]["dataset_id"] = changed
                manifest["dataset_id"] = changed
            elif field == "metric_definition":
                protocol["comparisons"][0]["metric"] = changed
            else:
                manifest["version" if field == "dataset_version" else "split_strategy"] = changed
            write(self.project / self.protocol_path, protocol)
            write(self.project / self.manifest_path, manifest)
            result = row["closest_work"]["axes"]["result"]
            result["conclusion_kind"] = "superiority"
            for name, item in result["ours"]["evaluation"].items():
                item.update(self.binding(item["path"]))
                if name == field:
                    item["value"] = changed
            with self.assertRaisesRegex(ValueError, "different source-bound"):
                extensions.comparison(self.project, row)
            result.update(disposition="not_comparable", conclusion_kind="descriptive")
            self.assertFalse(extensions.comparison(self.project, row)["closest_work"]["axes"]["result"]["same_bound_evaluation_values"])
            write(self.project / self.protocol_path, original_protocol)
            write(self.project / self.manifest_path, original_manifest)

    def test_dataset_manifest_and_protocol_claim_must_actually_match(self):
        row = self.fixture()
        manifest = read(self.project / self.manifest_path)
        manifest["dataset_id"] = "another-cohort"
        write(self.project / self.manifest_path, manifest)
        for item in row["closest_work"]["axes"]["result"]["ours"]["evaluation"].values():
            if item["path"] == self.manifest_path:
                item.update(self.binding(self.manifest_path))
        with self.assertRaisesRegex(ValueError, "protocol's bound dataset ID"):
            extensions.comparison(self.project, row)
        manifest["dataset_id"] = "cohort"
        write(self.project / self.manifest_path, manifest)
        row = self.fixture()
        protocol = read(self.project / self.protocol_path)
        protocol["comparisons"][0]["claim_ids"] = ["an-unrelated-claim"]
        write(self.project / self.protocol_path, protocol)
        for item in row["closest_work"]["axes"]["result"]["ours"]["evaluation"].values():
            if item["path"] == self.protocol_path:
                item.update(self.binding(self.protocol_path))
        with self.assertRaisesRegex(ValueError, "belong to this actual claim"):
            extensions.comparison(self.project, row)

    def test_matched_source_values_do_not_override_changed_conditions_or_certify_superiority(self):
        row = self.fixture()
        result = row["closest_work"]["axes"]["result"]
        result["conclusion_kind"] = "superiority"
        checked = extensions.comparison(self.project, row)
        self.assertFalse(checked["comparability_verified"])
        self.assertFalse(checked["closest_work"]["scientific_comparability_verified"])
        row["right"]["conditions"]["tuning_budget"] = "Unmatched synthetic tuning budget"
        row["difference_explanations"] = {"tuning_budget": "The reported search budgets differ."}
        with self.assertRaisesRegex(ValueError, "matched declared conditions"):
            extensions.comparison(self.project, row)

    def test_equal_unknown_conditions_do_not_establish_a_comparative_benefit(self):
        for conclusion in ("superiority", "equivalence"):
            row = self.fixture()
            row["disposition"] = "insufficient_evidence"
            for arm in ("left", "right"):
                row[arm]["conditions"]["assumptions"] = "unknown"
            result = row["closest_work"]["axes"]["result"]
            result["conclusion_kind"] = conclusion
            with self.subTest(conclusion=conclusion), self.assertRaisesRegex(ValueError, "matched declared conditions"):
                extensions.comparison(self.project, row)
            result["conclusion_kind"] = "descriptive"
            checked = extensions.comparison(self.project, row)
            self.assertEqual(checked["different_conditions"], [])
            self.assertEqual(len(checked["unknown_conditions"]), 2)
            self.assertFalse(checked["comparability_verified"])

    def test_parent_comparison_must_be_comparable_for_benefit_claim(self):
        for parent in ("insufficient_evidence", "not_comparable"):
            row = self.fixture()
            row["disposition"] = parent
            row["closest_work"]["axes"]["result"]["conclusion_kind"] = "superiority"
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, "matched declared conditions"):
                extensions.comparison(self.project, row)

    def test_comparison_is_recomputed_inside_the_existing_extension_audit(self):
        row = self.fixture()
        write(self.project / extensions.INPUT, {"schema_version": "1.0", "comparisons": [row]})
        audit = extensions.audit(self.project)
        self.assertEqual(audit["errors"], [])
        self.assertEqual(audit["sections"]["comparisons"][0]["closest_work_axis_check"], "source_bound")
        self.assertFalse(audit["scientific_completion_verified"])
        self.text(self.own_path, "Changed own source must invalidate the same audit.")
        self.assertTrue(extensions.audit(self.project)["errors"])

    def test_pdf_anchor_reuses_the_real_controlled_reader_page_and_source_bindings(self):
        try:
            import fitz
            from scripts import paper_reader
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("controlled reader dependencies are installed on the cloud reader job")
        pdf = self.project / "literature/sources/nearest.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), (self.project / self.prior_path).read_text(encoding="utf-8"))
            document.save(pdf)
        reader_path = "literature/readers/nearest.md"
        paper_reader.build(self.project, pdf, self.project / reader_path)
        row = self.fixture()
        library = read(self.project / extensions.CLOSEST_CONTEXT["literature_library"])
        library["papers"][0].update(source=self.binding("literature/sources/nearest.pdf"),
                                    reader=self.binding(reader_path))
        self.update_context(row, "literature_library", library)
        text = (self.project / reader_path).read_text(encoding="utf-8").splitlines()
        for axis in row["closest_work"]["axes"].values():
            side = axis["prior"]
            old = side["evidence"][0]
            number = text.index(old["quote"]) + 1
            side["evidence"] = [{**self.anchor(reader_path, number), "pdf_page": 1}]
            for item in side.get("evaluation", {}).values():
                number = text.index(item["quote"]) + 1
                item.update(self.anchor(reader_path, number), pdf_page=1)
        checked = extensions.comparison(self.project, row)["closest_work"]
        self.assertEqual(checked["axes"]["method"]["prior"]["evidence"][0]["pdf_page"], 1)
        row["closest_work"]["axes"]["method"]["prior"]["evidence"][0]["pdf_page"] = 2
        with self.assertRaisesRegex(ValueError, "exact PDF page"):
            extensions.comparison(self.project, row)


if __name__ == "__main__":
    unittest.main()
