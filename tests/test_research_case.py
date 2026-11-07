"""Local synthetic runner/source fixtures, not evidence of a publishable paper."""
from __future__ import annotations

import copy
import csv
from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import research_case as case
from scripts import experiment_evidence as evidence, experiment_evidence_acceptance as acceptance
from scripts import experiment_runner as runner
from scripts.research_artifacts import read, write, sha, record


def binding(project, relative, *, excerpt=None):
    result = {"path": relative, "sha256": sha(project / relative)}
    if excerpt is not None:
        result.update(locator="L1", excerpt=excerpt)
    return result


def text(project, relative, value):
    target = project / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value)
    record(project, [target], "synthetic-software-fixture")
    return binding(project, relative)


class ResearchCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        original = root / "original"
        acceptance.fixture(original, current_protocol=True)
        runner.execute(original.name, project_root=original)
        actual = evidence.build_report(original, "P01")
        if actual["status"] != "complete":
            raise AssertionError(actual)
        # The replay unit reconstructs a machine-readable table from previous
        # actual synthetic outputs. It is a table replay, not rerunning science.
        cls.base = root / "with-replay"
        acceptance.fixture(cls.base, current_protocol=True)
        environment = text(cls.base, "papers/P01/environment.lock", "python==" + ".".join(map(str, sys.version_info[:3])) + "\n")
        source = text(cls.base, "experiments/code/table-input.json", json.dumps(actual["comparisons"]))
        code = text(cls.base, "experiments/code/table.py", "import csv,json,os,pathlib\n"
                    "assert os.environ['RESEARCH_OS_RUN_ID']=='table-replay'\n"
                    "assert os.environ['RESEARCH_OS_SEED']==os.environ['PYTHONHASHSEED']=='0'\n"
                    "rows=json.loads(pathlib.Path('experiments/code/table-input.json').read_text())\n"
                    "with open('results/replayed-table.csv','w',newline='') as f:\n"
                    " w=csv.DictWriter(f,fieldnames=['comparison_id','estimate','ci_low','ci_high','decision'],extrasaction='ignore');w.writeheader();w.writerows(rows)\n")
        plan_path = cls.base / "experiments/plan.json"
        plan = read(plan_path)
        plan["runs"].append({"run_id": "table-replay", "paper_id": "P01", "cwd": ".", "seed": 0,
                             "argv": ["python3", "experiments/code/table.py"], "timeout_seconds": 60, "estimated_cost_usd": 0,
                             "isolation": {"kind": "host"}, "inputs": [source, code, environment],
                             "expected_outputs": ["results/replayed-table.csv"], "depends_on": [r["run_id"] for r in plan["runs"]]})
        write(plan_path, plan)
        acceptance.freeze_fixture(cls.base)
        runner.execute(cls.base.name, project_root=cls.base)
        cls.report = evidence.build_report(cls.base, "P01")
        if cls.report["status"] != "complete":
            raise AssertionError(cls.report)
        matrix = acceptance.claim_matrix(cls.base, cls.report)
        (cls.base / "claims").mkdir(exist_ok=True)
        shutil.copyfile(matrix, cls.base / "claims/claim-evidence.csv")
        cls.protocol = read(cls.base / "papers/P01/experiment-evidence-plan.json")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "project"
        shutil.copytree(self.base, self.project)
        self.spec = {"schema_version": "1.0", "paper_id": "P01"}
        self.save()

    def save(self):
        path = self.project / "papers/P01/research-case.json"
        write(path, self.spec)
        record(self.project, [path], "synthetic-software-fixture")

    def manuscript(self):
        source = text(self.project, "papers/P01/manuscript/main.tex", "Synthetic software fixture only. Adverse comparisons remain reported.\n")
        self.spec.update(variants=[{"id": "v1", "title": "Synthetic software fixture", "abstract": "A test of source bindings, not a scientific result.",
                                    "keywords": ["synthetic", "software"], "claim_ids": ["C1"], "reason": "Explicit fixture scope."}], selected_variant="v1")
        self.spec["preprint"] = {"manuscript_sources": [source]}
        self.save()
        return source

    def test_progressive_packet_reuses_existing_tests_and_does_not_invent_completion(self):
        packet = case.build_packet(self.project, "P01")
        self.assertEqual(packet["critical_tests"], self.protocol["critical_tests"])
        self.assertEqual(packet["status"], "preparation")
        self.assertIn("contribution.headline_claim", packet["missing_evidence"])
        self.assertFalse(packet["limits"]["scientific_validity_verified"])
        limited = case.build_packet(self.project, "P01", sections=["pre_mortem", "critical_tests"])
        self.assertNotIn("case", limited)
        self.assertNotIn("variants", limited)

    def test_paper_identity_and_symlink_sources_cannot_cross_scope(self):
        self.spec["paper_id"] = "P02"
        self.save()
        with self.assertRaisesRegex(ValueError, "identity"):
            case.build_packet(self.project, "P01")
        with self.assertRaisesRegex(ValueError, "exact paper"):
            case.build_packet(self.project, "../P01")
        self.spec["paper_id"] = "P01"
        self.save()
        source = self.project / "papers/P01/research-case.json"
        contents = source.read_bytes()
        source.unlink()
        actual = self.project / "elsewhere.json"
        actual.write_bytes(contents)
        source.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, "symlink"):
            case.build_packet(self.project, "P01")

    def test_contribution_and_figures_use_actual_claim_and_test_ids(self):
        self.spec["contribution"] = {"headline_claim": "Mechanism works under condition X.", "counterclaim": "Mechanism works under condition X.",
                                     "claim_ids": ["other-paper"], "test_ids": ["invented"],
                                     "reader_benefits": [{"reader": str(i), "benefit": "Know the boundary."} for i in range(3)]}
        self.spec["figure_first"] = [{"role": "negative_boundary", "claim_ids": ["C1"], "comparison_ids": ["weak"]}]
        self.save()
        findings = "; ".join(case.build_packet(self.project, "P01")["missing_evidence"])
        self.assertIn("distinguishable alternative", findings)
        self.assertIn("contracted claims", findings)
        self.assertIn("actual discriminating tests", findings)
        self.assertIn("adverse/control", findings)

    def test_preprint_uses_current_native_results_and_unknown_pid(self):
        self.manuscript()
        release = case.export(self.project, "P01", "preprint")
        root = self.project / release["path"]
        rows = list(csv.DictReader(io_text(root / "results.csv")))
        self.assertEqual({r["comparison_id"] for r in rows}, {r["comparison_id"] for r in self.report["comparisons"]})
        self.assertIn("does_not_establish_claim", {r["decision"] for r in rows})
        self.assertEqual(read(root / "persistent-identifier.json")["status"], "unknown")
        self.assertFalse(release["external_publication"])
        self.assertEqual(case.export(self.project, "P01", "preprint")["path"], release["path"])
        (root / "title-abstract.md").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "historical versions"):
            case.export(self.project, "P01", "preprint")

    def test_stale_actual_output_cannot_be_exported_by_refreshing_case(self):
        self.manuscript()
        (self.project / "results/recent-11.csv").write_text("unit,value\n0,999\n")
        self.save()
        with self.assertRaisesRegex(ValueError, "actual complete executor evidence"):
            case.export(self.project, "P01", "preprint")

    def test_pid_needs_actual_registration_evidence(self):
        self.manuscript()
        self.spec["preprint"]["persistent_identifier"] = {"status": "registered", "value": "10.1234/invented"}
        self.save()
        with self.assertRaisesRegex(ValueError, "binding"):
            case.export(self.project, "P01", "preprint")

    def test_registered_doi_requires_native_receipt_and_this_manuscript_title(self):
        from scripts import literature_evidence
        self.manuscript()
        doi = "10.1234/synthetic-software-fixture"
        receipt = literature_evidence.execute_search(self.project, "crossref", doi,
            query_family="identifier-verification", date_range="none", filters="none", limit=1,
            fetcher=lambda url, **_: (json.dumps({"message": {"items": [{"DOI": doi,
                "title": [self.spec["variants"][0]["title"]], "author": [{"given": "Synthetic", "family": "Fixture"}]}]}}).encode(),
                url, 200, "application/json"))
        source = binding(self.project, receipt["normalized_results_path"], excerpt=doi)
        self.spec["preprint"]["persistent_identifier"] = {"status": "registered", "value": doi,
            "receipt_id": receipt["receipt_id"], "source": source}
        self.save()
        release = case.export(self.project, "P01", "preprint")
        self.assertEqual(read(self.project / release["path"] / "persistent-identifier.json")["value"], doi)
        self.spec["variants"][0]["title"] = "A different paper without matching registration"
        self.save()
        with self.assertRaisesRegex(ValueError, "retained manuscript title"):
            case.export(self.project, "P01", "preprint")
        private_note = text(self.project, "papers/P01/manuscript/pid-note.txt", doi)
        self.spec["preprint"]["persistent_identifier"]["source"] = {**private_note, "locator": "L1", "excerpt": doi}
        self.save()
        with self.assertRaisesRegex(ValueError, "bibliographic retrieval receipt"):
            case.export(self.project, "P01", "preprint")

    def reproduction(self):
        license_source = text(self.project, "papers/P01/release-license.txt", "CC0 synthetic test material; redistribution permitted.\n")
        environment = binding(self.project, "papers/P01/environment.lock")
        rights = {**license_source, "locator": "L1", "excerpt": "CC0 synthetic test material; redistribution permitted."}
        self.spec["reproduction"] = {"replay_run_id": "table-replay", "result_table": "results/replayed-table.csv",
                                     "license": license_source, "environment": environment,
                                     "files": [{**binding(self.project, relative), "license": "CC0", "rights_source": rights}
                                               for relative in ("experiments/code/table.py", "experiments/code/table-input.json")]}
        self.save()

    def test_registered_table_replay_package_really_runs_outside_project(self):
        self.reproduction()
        release = case.export(self.project, "P01", "reproduction")
        root = self.project.parent / "portable-reproduction"
        shutil.copytree(self.project / release["path"], root)
        shutil.rmtree(self.project)  # This fixture's original inputs are no longer available.
        table = root / "sources/results/replayed-table.csv"
        expected = table.read_bytes()
        table.unlink()
        subprocess.run([sys.executable, str(root / "reproduce.py")], cwd=root, check=True, capture_output=True,
            env={**os.environ, "RESEARCH_OS_RUN_ID": "wrong-id", "RESEARCH_OS_SEED": "99", "PYTHONHASHSEED": "99"})
        self.assertEqual(table.read_bytes(), expected)
        self.assertEqual(len(list(csv.DictReader(io_text(root / "results.csv")))), len(self.report["comparisons"]))
        self.assertTrue((root / "README.md").is_file())
        runtime = read(root / "recorded-runtime.json")
        self.assertEqual(runtime["run_id"], "table-replay")
        self.assertEqual(runtime["runtime"]["python"], ".".join(map(str, sys.version_info[:3])))
        self.assertFalse(runtime["dependency_installation_verified"])

    def test_reproduction_rejects_unexecuted_environment_and_raw_or_other_paper_files(self):
        self.reproduction()
        self.spec["reproduction"]["environment"] = text(self.project, "papers/P01/replacement.lock", "python==0.0.0\n")
        self.save()
        with self.assertRaisesRegex(ValueError, "frozen input"):
            case.export(self.project, "P01", "reproduction")
        self.reproduction()
        for relative, message in (("data/raw/observations.csv", "private/control"),
                                  ("papers/P02/manuscript/private-notes.txt", "another paper")):
            with self.subTest(relative=relative):
                extra = {**text(self.project, relative, "Synthetic file should stay outside the release.\n"),
                         "license": "CC0", "rights_source": self.spec["reproduction"]["files"][0]["rights_source"]}
                self.spec["reproduction"]["files"].append(extra)
                self.save()
                with self.assertRaisesRegex(ValueError, message):
                    case.export(self.project, "P01", "reproduction")
                self.spec["reproduction"]["files"].pop()

    def test_preprint_versions_keep_original_content_and_preparation_time(self):
        self.manuscript()
        previous = case.export(self.project, "P01", "preprint")
        stamp = datetime.fromisoformat(previous["prepared_at"])
        self.assertIsNotNone(stamp.tzinfo)
        root = self.project / previous["path"]
        old = (root / "title-abstract.md").read_bytes()
        self.spec["variants"].append({**self.spec["variants"][0], "id": "v2", "title": "Refined synthetic software fixture"})
        self.spec["selected_variant"] = "v2"
        self.save()
        current = case.export(self.project, "P01", "preprint")
        self.assertNotEqual(current["path"], previous["path"])
        self.assertEqual((root / "title-abstract.md").read_bytes(), old)
        self.assertEqual(case.export(self.project, "P01", "preprint"), current)
        (self.project / current["path"] / "unlisted-secret.txt").write_text("not export material")
        with self.assertRaisesRegex(ValueError, "historical versions"):
            case.export(self.project, "P01", "preprint")

    def venue_fit(self):
        from scripts import journal_dossier
        url = "https://publisher.example/author-information"
        quote = "Synthetic journal scope, editorial interests, article types and desk rejection criteria."
        write(self.project / "program/journal-dossiers.json", {"journals": [{"venue_id": "synthetic-journal",
            "official_domains": ["publisher.example"], "fields": {"scope": {"url": url}}}]})
        ledger = journal_dossier.fetch_sources(self.project, fetcher=lambda value, **_: (
            ("<p>" + quote + "</p>").encode(), value, 200, "text/html"))
        receipt = ledger["sources"][url]
        source = binding(self.project, receipt["path"], excerpt=quote)
        self.spec["venue_fit"] = {"venue_id": "synthetic-journal", **{
            name: {"statement": "Synthetic demonstration; not real journal advice.", "url": url, "source": source}
            for name in case.VENUE_FIELDS}}
        self.spec["cover_letter"] = {"text": "This synthetic fixture tests provenance rather than a scientific claim.", "evidence_sources": [source]}
        self.save()
        return source

    def test_retarget_uses_official_receipts_and_preserves_previous_manuscript(self):
        manuscript = self.manuscript()
        previous = case.export(self.project, "P01", "preprint")
        retained = binding(self.project, previous["path"] + "/sources/" + manuscript["path"])
        self.venue_fit()
        self.spec["retarget"] = {"manuscript_sources": [manuscript], "previous_manuscript": [retained],
            "previous_venue_id": "previous-synthetic-journal", "target_venue_id": "synthetic-journal",
            "changes": ["Explain the source-bound software test scope to the new audience."]}
        self.save()
        release = case.export(self.project, "P01", "retarget")
        root = self.project / release["path"]
        self.assertTrue((root / "cover-letter.txt").is_file())
        self.assertEqual((root / "sources" / retained["path"]).read_bytes(), (self.project / retained["path"]).read_bytes())
        self.assertEqual(read(root / "venue-fit.json")["venue_id"], "synthetic-journal")
        self.spec["retarget"]["previous_manuscript"] = [text(self.project, "papers/P02/manuscript/main.tex", "Other paper\n")]
        self.save()
        with self.assertRaisesRegex(ValueError, "retained version of this paper"):
            case.export(self.project, "P01", "retarget")
        self.spec["retarget"]["previous_manuscript"] = [retained]
        self.spec["venue_fit"]["scope"]["url"] = "https://unverified.example/scope"
        self.save()
        with self.assertRaisesRegex(ValueError, "official retrieval evidence"):
            case.export(self.project, "P01", "retarget")

    def test_related_work_and_rebuttal_keep_actual_anchors_and_no_fake_review(self):
        manuscript = self.manuscript()
        source = binding(self.project, manuscript["path"], excerpt="Synthetic software fixture only. Adverse comparisons remain reported.")
        self.spec["positioning"] = [{"work_id": "synthetic-local-source", "shared": "Common test format.",
            "difference": "Different provenance behavior.", "prediction": "Changed sources invalidate the old packet.", "source": source}]
        self.spec["rebuttal"] = [{"id": "anticipated-1", "concern": "Does the fixture establish scientific merit?",
            "response": "No; it tests software behavior only.", "claim_ids": ["C1"], "evidence_sources": [source]}]
        self.save()
        packet = case.build_packet(self.project, "P01", sections=["positioning", "rebuttal"])
        self.assertEqual(packet["positioning"], self.spec["positioning"])
        self.assertNotIn("case", packet)
        release = case.export(self.project, "P01", "rebuttal")
        root = self.project / release["path"]
        self.assertTrue((root / "related-work.csv").is_file())
        self.assertIn("not received reviewer comments", (root / "rebuttal-preparation.md").read_text())
        self.spec["rebuttal"][0]["evidence_sources"][0]["excerpt"] = "Invented quoted evidence."
        self.save()
        with self.assertRaisesRegex(ValueError, "excerpt"):
            case.export(self.project, "P01", "rebuttal")

    def test_reproduction_cannot_substitute_an_unrelated_run_or_omit_rights(self):
        self.reproduction()
        self.spec["reproduction"]["replay_run_id"] = "invented"
        self.save()
        with self.assertRaisesRegex(ValueError, "actual approved replay"):
            case.export(self.project, "P01", "reproduction")
        self.spec["reproduction"]["replay_run_id"] = "table-replay"
        del self.spec["reproduction"]["files"][0]["rights_source"]
        self.save()
        with self.assertRaisesRegex(ValueError, "binding"):
            case.export(self.project, "P01", "reproduction")

    def test_reproduction_requires_the_original_executor_receipt_and_command(self):
        self.reproduction()
        registry_path = self.project / "experiments/registry.jsonl"
        original = registry_path.read_text()
        rows = [json.loads(line) for line in original.splitlines()]
        item = next(row for row in rows if row["run_id"] == "table-replay")
        receipt_path = self.project / "experiments/runs" / item["attempt_id"] / "run.json"
        original_receipt = read(receipt_path)
        for field, changed in (("argv", ["python3", "unexecuted.py"]), ("cwd", "experiments"),
                               ("executor_isolation", {"kind": "container", "engine": "docker", "image": "unexecuted:latest"})):
            with self.subTest(field=field):
                item.clear()
                item.update(copy.deepcopy(original_receipt))
                write(receipt_path, original_receipt)
                item[field] = changed
                registry_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
                with self.assertRaisesRegex(ValueError, "unchanged executor receipt|differs from the approved"):
                    case.export(self.project, "P01", "reproduction")
                write(receipt_path, item)
                with self.assertRaisesRegex(ValueError, "approved run|approved cwd|matching recorded"):
                    case.export(self.project, "P01", "reproduction")
                item.clear()
                item.update(copy.deepcopy(original_receipt))
                write(receipt_path, original_receipt)
        registry_path.write_text(original)

    def test_separately_mounted_runtime_cannot_be_exported_as_portable_python(self):
        self.reproduction()
        registry_path = self.project / "experiments/registry.jsonl"
        rows = [json.loads(line) for line in registry_path.read_text().splitlines()]
        item = next(row for row in rows if row["run_id"] == "table-replay")
        item["executor_isolation"]["reviewed_runtime"] = {"profile": "meta_analysis"}
        registry_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        write(self.project / "experiments/runs" / item["attempt_id"] / "run.json", item)
        with self.assertRaisesRegex(ValueError, "study_routes.export_results"):
            case.export(self.project, "P01", "reproduction")

    def test_host_replay_preserves_timeout_seed_and_frozen_inputs(self):
        self.reproduction()
        release = case.export(self.project, "P01", "reproduction")
        root = self.project / release["path"]
        hashes = {item["path"]: sha(root / "sources" / item["path"]) for item in self.spec["reproduction"]["files"]}
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["python3"], 60)) as invoke:
            with self.assertRaises(subprocess.TimeoutExpired):
                runpy.run_path(str(root / "reproduce.py"), run_name="__main__")
        self.assertEqual(invoke.call_args.kwargs["timeout"], 60)
        environment = invoke.call_args.kwargs["env"]
        self.assertEqual(environment["RESEARCH_OS_RUN_ID"], "table-replay")
        self.assertEqual(environment["RESEARCH_OS_SEED"], "0")
        self.assertEqual(environment["PYTHONHASHSEED"], "0")
        self.assertEqual(hashes, {path: sha(root / "sources" / path) for path in hashes})

    def test_docker_timeout_removes_only_its_own_container_and_keeps_inputs(self):
        # Unit-test the transport lifecycle only; the separate Docker acceptance
        # test establishes that real isolated execution and exported replay work.
        root = self.project / "wrapper-fixture"
        root.mkdir()
        source = text(root, "sources/script.py", "Synthetic transport lifecycle fixture.\n")
        source_hash = source["sha256"]
        write(root / "replay-run.json", {"image": "synthetic@sha256:" + "a" * 64,
            "argv": ["python3", "script.py"], "cwd": ".", "seed": 7, "run_id": "synthetic-replay",
            "timeout_seconds": 2, "resources": {"cpu": 1, "memory_gb": 1, "gpu": 0},
            "inputs": [{"path": "script.py", "sha256": source_hash}], "outputs": ["results/table.csv"],
            "result_table": {"path": "results/table.csv", "sha256": "b" * 64}})
        (root / "reproduce.py").write_text(case._DOCKER_REPLAY)
        name = None
        def transport(argv, **kwargs):
            nonlocal name
            if argv[1] == "run":
                name = argv[argv.index("--name") + 1]
                self.assertTrue(name.startswith("lunwen-replay-"))
                self.assertEqual(kwargs["timeout"], 2)
                raise subprocess.TimeoutExpired(argv, 2)
            self.assertEqual(argv, ["docker", "rm", "-f", name])
            self.assertEqual(kwargs["timeout"], 30)
            return subprocess.CompletedProcess(argv, 0, stderr="")
        with patch("subprocess.run", side_effect=transport) as invoke:
            with self.assertRaises(subprocess.TimeoutExpired):
                runpy.run_path(str(root / "reproduce.py"), run_name="__main__")
        self.assertEqual(invoke.call_count, 2)
        self.assertEqual(sha(root / "sources/script.py"), source_hash)

    def test_competition_is_receipt_bound_and_unknown_dates_are_not_zero_growth(self):
        works = [{"id": str(i), "doi": f"10.1234/work{i}", "title": f"Synthetic source {i}", "authors": ["Author " + str(i)],
                  "publication_date": value} for i, value in enumerate(["2026-10-01", "2026-02-01", "2025-10-01", None])]
        normalized = text(self.project, "evidence/literature/window.json", json.dumps({"works": works}))
        raw = text(self.project, "evidence/literature/window.raw", json.dumps(works))
        receipt = {"receipt_id": "synthetic-source", "provider": "openalex", "status": "success", "result_count": 4,
                   "raw_response_path": raw["path"], "response_sha256": raw["sha256"],
                   "normalized_results_path": normalized["path"], "normalized_results_sha256": normalized["sha256"]}
        text(self.project, "evidence/literature-api-ledger.jsonl", json.dumps(receipt) + "\n")
        spec = {"receipt_ids": ["synthetic-source"], "same_problem_ids": [f"doi:10.1234/work{i}" for i in range(4)], "closest_work_id": "doi:10.1234/work0"}
        report = case.competition(self.project, spec, today=date(2026, 11, 6))
        self.assertEqual(report["recent_12_months"], 2)
        self.assertEqual(report["previous_12_months"], 1)
        self.assertIsNone(report["growth_fraction"])
        self.assertIsNone(report["submission_growth"])
        self.assertIsNone(report["actual_competing_groups"])
        self.assertEqual(report["closest_age_days"], 36)
        (self.project / normalized["path"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "stale literature receipt"):
            case.competition(self.project, spec)


def io_text(path):
    import io
    return io.StringIO(path.read_text())
