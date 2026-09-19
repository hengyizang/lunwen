from __future__ import annotations

import copy
import json
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from scripts.research_quality import (
    create_data_quality_report,
    create_data_quality_confirmation,
    create_power_report,
    create_preregistration,
    create_reproduction_confirmation,
    create_simulation_power_report,
    refresh_runtime_evidence_catalog,
    registry_environment_digest,
    sha256_file,
    ResearchQualityError,
    validate_baseline_reproduction,
    validate_clean_room_reproduction,
    validate_data_quality_report,
    validate_data_quality_confirmation,
    validate_novelty_claim_matrix,
    validate_power_report,
    validate_preregistration,
    validate_reproduction_confirmation,
)


class ResearchQualityTests(unittest.TestCase):
    def novelty_inputs(self) -> tuple[dict, dict]:
        originality = {
            "closest_prior_work": [{"id": f"W{index}"} for index in range(1, 6)],
            "novelty_claims": [{"claim_id": "N1"}],
        }
        matrix = {
            "schema_version": "1.0",
            "status": "ready_for_review",
            "claims": [
                {
                    "claim_id": "N1",
                    "paper_ids": ["P01"],
                    "claim": "A falsifiable reliability mechanism.",
                    "closest_work_ids": ["W1", "W2", "W3"],
                    "already_known": "Prior work detects failures after onset.",
                    "precise_difference": "The proposed mechanism tests pre-onset transfer.",
                    "mechanism_or_rationale": "Invariant degradation features should transfer.",
                    "falsification_test": "Evaluate on a locked cross-machine cohort.",
                    "expected_if_false": "The interval overlaps the strong baseline.",
                    "boundary_conditions": "Rotating machinery with comparable sensors.",
                    "residual_risk": "Unindexed industrial deployments may overlap.",
                }
            ],
            "search_saturation": {
                "exact_query_rounds": 2,
                "adjacent_field_rounds": 2,
                "backward_chaining_complete": True,
                "forward_chaining_complete": True,
                "supporting_search_ids": ["S1", "S2", "S3", "S4"],
                "backward_chaining_search_ids": ["S1"],
                "forward_chaining_search_ids": ["S2"],
                "consecutive_no_material_new_work_rounds": 2,
                "no_material_new_work_rounds": [
                    {"round_id": "R1", "search_ids": ["S3"], "material_new_closest_work_count": 0, "stopping_reason": "No closer work after adjacent-field expansion."},
                    {"round_id": "R2", "search_ids": ["S4"], "material_new_closest_work_count": 0, "stopping_reason": "No closer work after citation-chain update."},
                ],
                "unresolved_search_gaps": [],
                "saturation_rationale": "Two query and chaining rounds yielded no closer work.",
            },
            "human_review_required": True,
        }
        return originality, matrix

    def test_novelty_matrix_requires_three_known_works_and_saturation(self) -> None:
        originality, matrix = self.novelty_inputs()
        searches = [{"search_id": f"S{index}"} for index in range(1, 5)]
        self.assertEqual(validate_novelty_claim_matrix(matrix, originality, searches), [])
        invalid = copy.deepcopy(matrix)
        invalid["claims"][0]["closest_work_ids"] = ["W1", "W2", "UNKNOWN"]
        invalid["search_saturation"]["consecutive_no_material_new_work_rounds"] = 1
        errors = validate_novelty_claim_matrix(invalid, originality, searches)
        self.assertTrue(any("unknown work" in error for error in errors))
        self.assertTrue(any("must be >= 2" in error for error in errors))

    def make_project(self, root: Path) -> Path:
        project = root / "demo"
        for relative in (
            "data/raw",
            "data/quality",
            "experiments",
            "papers/P01/experiments",
        ):
            (project / relative).mkdir(parents=True, exist_ok=True)
        data = project / "data" / "raw" / "dataset.csv"
        data.write_text(
            "machine,split,label,value\nA,train,ok,1\nB,train,fault,2\nC,test,ok,3\n",
            encoding="utf-8",
        )
        manifest = {
            "dataset_id": "d1",
            "download": {"sha256": sha256_file(data)},
            "provenance": {"transformations": []},
        }
        (project / "data" / "datasets.jsonl").write_text(
            json.dumps(manifest) + "\n", encoding="utf-8"
        )
        contract = {
            "paper_id": "P01",
            "datasets": ["d1"],
            "hypotheses": [{"id": "H1"}],
        }
        (project / "papers" / "P01" / "paper-contract.json").write_text(
            json.dumps(contract), encoding="utf-8"
        )
        design = {
            "paper_id": "P01",
            "design_id": "D1",
            "baselines": [
                {"id": "B1", "class": "domain_standard", "primary_source_url": "https://example.org/b1"},
                {"id": "B2", "class": "strong_recent", "primary_source_url": "https://example.org/b2"},
            ],
            "reproduction_plan": {
                "baseline_runs": {
                    "domain_standard": ["base-domain"],
                    "strong_recent": ["base-recent"],
                },
                "original_run_ids": ["original"],
                "clean_room_run_ids": ["reproduction"],
                "metric_tolerances": [
                    {"metric": "F1", "absolute_tolerance": 0.02, "rationale": "Locked equivalence margin."}
                ],
            },
        }
        (project / "papers" / "P01" / "experiments" / "primary.json").write_text(
            json.dumps(design), encoding="utf-8"
        )
        (project / "experiments" / "plan.json").write_text(
            json.dumps({"status": "ready_for_review", "runs": []}), encoding="utf-8"
        )
        (project / "experiments" / "budget.json").write_text(
            json.dumps({"status": "ready_for_review", "hard_ceiling_usd": 10}),
            encoding="utf-8",
        )
        return project

    def test_data_quality_report_is_local_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            report = create_data_quality_report(
                project,
                "d1",
                "data/raw/dataset.csv",
                actor="Researcher",
                label_column="label",
                split_column="split",
                group_column="machine",
            )
            self.assertEqual(report["status"], "pass")
            self.assertEqual(validate_data_quality_report(report, "d1", project), [])
            report_path = project / "data" / "quality" / "d1.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            confirmation = create_data_quality_confirmation(
                project, "d1", "Researcher"
            )
            self.assertEqual(
                validate_data_quality_confirmation(confirmation, "d1", project), []
            )
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.assertTrue(
                any(
                    "stale" in error
                    for error in validate_data_quality_confirmation(
                        confirmation, "d1", project
                    )
                )
            )
            report_path.write_text(json.dumps(report), encoding="utf-8")
            (project / "data" / "raw" / "dataset.csv").write_text(
                "machine,split,label,value\nA,train,ok,9\n", encoding="utf-8"
            )
            self.assertTrue(
                any("changed" in error for error in validate_data_quality_report(report, "d1", project))
            )

    def test_non_tabular_wav_is_content_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            audio = project / "data" / "raw" / "signal.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(b"\x00\x00" * 800)
            manifest = {
                "dataset_id": "audio",
                "download": {"sha256": sha256_file(audio)},
                "provenance": {"transformations": []},
            }
            with (project / "data" / "datasets.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(manifest) + "\n")
            report = create_data_quality_report(
                project, "audio", "data/raw/signal.wav", actor="Researcher"
            )
            self.assertEqual(report["status"], "pass")
            profile = report["non_tabular_profile"]
            self.assertEqual(profile["profiles"][0]["kind"], "wav_audio")
            self.assertEqual(profile["profiles"][0]["sample_rates"], {"8000": 1})

    def test_unknown_non_tabular_format_blocks_instead_of_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            blob = project / "data" / "raw" / "opaque.bin"
            blob.write_bytes(b"opaque")
            manifest = {
                "dataset_id": "opaque",
                "download": {"sha256": sha256_file(blob)},
                "provenance": {"transformations": []},
            }
            with (project / "data" / "datasets.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(manifest) + "\n")
            report = create_data_quality_report(
                project, "opaque", "data/raw/opaque.bin", actor="Researcher"
            )
            self.assertEqual(report["status"], "block")
            self.assertTrue(any("no reviewed content handler" in item for item in report["blockers"]))

    def test_mixed_audio_and_tabular_directory_scans_both_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            mixed = project / "data" / "raw" / "mixed"
            mixed.mkdir()
            audio = mixed / "signal.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(8000)
                handle.writeframes(b"\x00\x00" * 80)
            (mixed / "labels.csv").write_text("file,label\nsignal.wav,normal\n", encoding="utf-8")
            manifest = {
                "dataset_id": "mixed",
                "download": {"sha256": "not-applicable-to-derived-directory"},
                "provenance": {"transformations": ["Extracted authorized source archive."]},
            }
            with (project / "data" / "datasets.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(manifest) + "\n")
            report = create_data_quality_report(
                project, "mixed", "data/raw/mixed", actor="Researcher", derived=True
            )

            self.assertEqual(report["status"], "pass")
            kinds = {item["kind"] for item in report["non_tabular_profile"]["profiles"]}
            self.assertEqual(kinds, {"tabular_files", "wav_audio"})

    def test_preregistration_detects_post_freeze_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            data_report = create_data_quality_report(
                project, "d1", "data/raw/dataset.csv", actor="Researcher"
            )
            (project / "data" / "quality" / "d1.json").write_text(
                json.dumps(data_report), encoding="utf-8"
            )
            confirmation = create_data_quality_confirmation(
                project, "d1", "Researcher"
            )
            (project / "data" / "quality" / "d1-confirmation.json").write_text(
                json.dumps(confirmation), encoding="utf-8"
            )
            contract = project / "papers" / "P01" / "paper-contract.json"
            design = project / "papers" / "P01" / "experiments" / "primary.json"
            power = {
                "schema_version": "1.0",
                "paper_id": "P01",
                "status": "ready_for_review",
                "human_review_required": True,
                "generated_by": "statsmodels",
                "engine_version": "0.15.0",
                "method": "ttest_ind",
                "effect_size": 0.5,
                "effect_size_basis": "Minimum practically important difference from prior work.",
                "alpha": 0.05,
                "target_power": 0.8,
                "required_sample_size": {"group_1": 64, "group_2": 64},
                "bound_files": [
                    {"path": contract.relative_to(project).as_posix(), "sha256": sha256_file(contract)},
                    {"path": design.relative_to(project).as_posix(), "sha256": sha256_file(design)},
                ],
            }
            (project / "papers" / "P01" / "power-analysis.json").write_text(
                json.dumps(power), encoding="utf-8"
            )
            prereg = create_preregistration(project, "P01", "Researcher")
            self.assertEqual(validate_preregistration(prereg, "P01", project), [])
            design.write_text(json.dumps({"paper_id": "P01", "design_id": "CHANGED"}), encoding="utf-8")
            self.assertTrue(
                any("changed" in error for error in validate_preregistration(prereg, "P01", project))
            )

    def test_analytical_power_uses_statsmodels_and_binds_design(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            class FakePower:
                def solve_power(self, **_kwargs):
                    return 63.2
            statsmodels = types.ModuleType("statsmodels")
            statsmodels.__version__ = "0.15.0"
            stats = types.ModuleType("statsmodels.stats")
            power_module = types.ModuleType("statsmodels.stats.power")
            power_module.FTestAnovaPower = FakePower
            power_module.NormalIndPower = FakePower
            power_module.TTestIndPower = FakePower
            power_module.TTestPower = FakePower
            with patch.dict(
                "sys.modules",
                {
                    "statsmodels": statsmodels,
                    "statsmodels.stats": stats,
                    "statsmodels.stats.power": power_module,
                },
            ):
                report = create_power_report(
                    project, "P01", "ttest_ind", 0.5, 0.05, 0.8, 1.0,
                    "Prior registered study DOI 10.1000/example."
                )
            self.assertEqual(report["required_sample_size"], {"group_1": 64, "group_2": 64})
            self.assertEqual(report["generated_by"], "statsmodels")
            self.assertEqual(len(report["bound_files"]), 2)

    def test_simulation_power_cross_checks_executable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            script = project / "papers" / "P01" / "experiments" / "power.py"
            evidence = project / "papers" / "P01" / "experiments" / "power.json"
            script.write_text(
                "import hashlib, json, os\n"
                "from pathlib import Path\n"
                "script = Path(__file__)\n"
                "payload = {\n"
                "  'schema_version': '1.0',\n"
                "  'simulation_count': int(os.environ['RESEARCH_OS_SIMULATION_COUNT']),\n"
                "  'rejection_count': 800,\n"
                "  'achieved_power': 0.8,\n"
                "  'effect_size': float(os.environ['RESEARCH_OS_EFFECT_SIZE']),\n"
                "  'alpha': float(os.environ['RESEARCH_OS_ALPHA']),\n"
                "  'random_seeds': json.loads(os.environ['RESEARCH_OS_RANDOM_SEEDS']),\n"
                "  'decision_rule': 'Reject when the corrected lower interval exceeds zero.',\n"
                "  'data_generating_process': 'Cluster bootstrap over machines.',\n"
                "  'generated_by_script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),\n"
                "}\n"
                "Path(os.environ['RESEARCH_OS_POWER_OUTPUT']).write_text(json.dumps(payload))\n",
                encoding="utf-8",
            )
            payload = {
                "schema_version": "1.0",
                "simulation_count": 1000,
                "rejection_count": 800,
                "achieved_power": 0.8,
                "effect_size": 0.02,
                "alpha": 0.05,
                "random_seeds": [104729],
                "decision_rule": "Reject when the corrected lower interval exceeds zero.",
                "data_generating_process": "Cluster bootstrap over machines.",
                "generated_by_script_sha256": sha256_file(script),
            }
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            report = create_simulation_power_report(
                project,
                "P01",
                0.02,
                0.05,
                0.8,
                1000,
                0.8,
                script.relative_to(project).as_posix(),
                evidence.relative_to(project).as_posix(),
                "Cluster bootstrap with a locked rejection rule.",
                "Minimum practically important difference.",
            )
            self.assertEqual(report["rejection_count"], 800)
            self.assertEqual(report["generated_by"], "simulation_rerun")
            self.assertEqual(len(report["rerun_receipts"]), 2)
            self.assertEqual(validate_power_report(report, "P01", project), [])
            tampered_report = copy.deepcopy(report)
            tampered_report["rerun_receipts"][0]["output_sha256"] = "f" * 64
            self.assertTrue(
                any("bound evidence" in item for item in validate_power_report(tampered_report, "P01", project))
            )
            payload["rejection_count"] = 700
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ResearchQualityError, "reproduce"):
                create_simulation_power_report(
                    project,
                    "P01",
                    0.02,
                    0.05,
                    0.8,
                    1000,
                    0.8,
                    script.relative_to(project).as_posix(),
                    evidence.relative_to(project).as_posix(),
                    "Cluster bootstrap with a locked rejection rule.",
                    "Minimum practically important difference.",
                )

    def test_g4_reports_require_successful_runs_hashes_and_registry_environments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.make_project(Path(directory))
            data_report = create_data_quality_report(
                project, "d1", "data/raw/dataset.csv", actor="Researcher"
            )
            (project / "data" / "quality" / "d1.json").write_text(
                json.dumps(data_report), encoding="utf-8"
            )
            data_confirmation = create_data_quality_confirmation(
                project, "d1", "Researcher"
            )
            (project / "data" / "quality" / "d1-confirmation.json").write_text(
                json.dumps(data_confirmation), encoding="utf-8"
            )
            contract = project / "papers" / "P01" / "paper-contract.json"
            design = project / "papers" / "P01" / "experiments" / "primary.json"
            power = {
                "schema_version": "1.0",
                "paper_id": "P01",
                "status": "ready_for_review",
                "human_review_required": True,
                "generated_by": "statsmodels",
                "engine_version": "0.15.0",
                "method": "ttest_ind",
                "effect_size": 0.5,
                "effect_size_basis": "Minimum practical difference fixed before results.",
                "alpha": 0.05,
                "target_power": 0.8,
                "required_sample_size": {"group_1": 64, "group_2": 64},
                "bound_files": [
                    {"path": contract.relative_to(project).as_posix(), "sha256": sha256_file(contract)},
                    {"path": design.relative_to(project).as_posix(), "sha256": sha256_file(design)},
                ],
            }
            (project / "papers" / "P01" / "power-analysis.json").write_text(
                json.dumps(power), encoding="utf-8"
            )
            preregistration = create_preregistration(project, "P01", "Researcher")
            (project / "papers" / "P01" / "preregistration.json").write_text(
                json.dumps(preregistration), encoding="utf-8"
            )
            evidence = project / "experiments" / "metrics.json"
            evidence.write_text('{"metric": 0.8}', encoding="utf-8")
            registry = [
                {"run_id": "base-domain", "attempt_id": "a1", "paper_id": "P01", "status": "succeeded", "cwd": "env-a", "git_commit": "a" * 40, "runtime": {"python": "3.12", "platform": "linux-a"}},
                {"run_id": "base-recent", "attempt_id": "a2", "paper_id": "P01", "status": "succeeded", "cwd": "env-a", "git_commit": "a" * 40, "runtime": {"python": "3.12", "platform": "linux-a"}},
                {"run_id": "original", "attempt_id": "a3", "paper_id": "P01", "status": "succeeded", "cwd": "env-a", "git_commit": "a" * 40, "runtime": {"python": "3.12", "platform": "linux-a"}},
                {"run_id": "reproduction", "attempt_id": "b1", "paper_id": "P01", "status": "succeeded", "cwd": "env-b", "git_commit": "a" * 40, "runtime": {"python": "3.12", "platform": "linux-b"}},
            ]
            for record in registry:
                record["executor_isolation"] = {
                    "kind": "host",
                    "instance_id": record["attempt_id"],
                    "isolated_executor": False,
                    "network_disabled": False,
                    "read_only_root": False,
                    "fingerprint": "c" * 64,
                }
            registry[-1]["executor_isolation"] = {
                "kind": "container",
                "instance_id": "b1",
                "isolated_executor": True,
                "network_disabled": True,
                "read_only_root": True,
                "image_digest": "d" * 64,
                "fingerprint": "e" * 64,
            }
            evidence_files = [{"path": "experiments/metrics.json", "sha256": sha256_file(evidence)}]
            for record in registry:
                record["outputs"] = evidence_files
            (project / "experiments" / "registry.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in registry),
                encoding="utf-8",
            )
            catalog_path = refresh_runtime_evidence_catalog(project)
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(len(catalog["runs"]), 4)
            self.assertTrue(catalog["runs"][0]["outputs"][0]["current_hash_match"])
            baseline = {
                "schema_version": "1.0", "paper_id": "P01", "status": "pass", "human_review_required": True,
                "baselines": [
                    {"baseline_id": "B1", "class": "domain_standard", "metric": "F1", "reference_source_url": "https://example.org/b1", "reference_value": 0.80, "observed_value": 0.79, "absolute_tolerance": 0.02, "comparable_protocol": True, "within_tolerance": True, "run_ids": ["base-domain"], "attempt_ids": ["a1"], "evidence_files": evidence_files, "comparison_notes": "Locked split."},
                    {"baseline_id": "B2", "class": "strong_recent", "metric": "F1", "reference_source_url": "https://example.org/b2", "reference_value": 0.82, "observed_value": 0.81, "absolute_tolerance": 0.02, "comparable_protocol": True, "within_tolerance": True, "run_ids": ["base-recent"], "attempt_ids": ["a2"], "evidence_files": evidence_files, "comparison_notes": "Locked split."},
                ],
            }
            self.assertEqual(validate_baseline_reproduction(baseline, "P01", project, registry), [])
            clean = {
                "schema_version": "1.0", "paper_id": "P01", "status": "pass", "human_review_required": True,
                "independent_operator": "Independent researcher",
                "original_run_ids": ["original"], "reproduction_run_ids": ["reproduction"],
                "original_attempt_ids": ["a3"], "reproduction_attempt_ids": ["b1"],
                "isolation": {
                    "isolated_executor": True,
                    "reproduction_kind": "container",
                    "original_isolation_ids": ["a3"],
                    "reproduction_isolation_ids": ["b1"],
                    "original_environment_digest": registry_environment_digest(registry, ["a3"]),
                    "reproduction_environment_digest": registry_environment_digest(registry, ["b1"]),
                    "source_commit": "a" * 40,
                },
                "metric_comparisons": [{"metric": "F1", "original_value": 0.80, "reproduction_value": 0.79, "absolute_tolerance": 0.02, "within_tolerance": True}],
                "evidence_files": evidence_files,
            }
            self.assertEqual(validate_clean_room_reproduction(clean, "P01", project, registry), [])
            same_environment = copy.deepcopy(registry)
            same_environment[-1]["cwd"] = "env-a"
            same_environment[-1]["runtime"] = {"python": "3.12", "platform": "linux-a"}
            self.assertNotEqual(
                registry_environment_digest(same_environment, ["a3"]),
                registry_environment_digest(same_environment, ["b1"]),
            )
            same_environment[-1]["executor_isolation"] = {
                **same_environment[2]["executor_isolation"],
                "instance_id": "b1",
            }
            self.assertEqual(
                registry_environment_digest(same_environment, ["a3"]),
                registry_environment_digest(same_environment, ["b1"]),
            )
            wrong_tolerance = copy.deepcopy(clean)
            wrong_tolerance["metric_comparisons"][0]["absolute_tolerance"] = 0.30
            self.assertTrue(
                any("G3 preregistration" in error for error in validate_clean_room_reproduction(wrong_tolerance, "P01", project, registry))
            )
            baseline_path = project / "papers" / "P01" / "baseline-reproduction.json"
            clean_path = project / "papers" / "P01" / "clean-room-reproduction.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            clean_path.write_text(json.dumps(clean), encoding="utf-8")
            confirmation = create_reproduction_confirmation(project, "P01", "Researcher")
            self.assertEqual(validate_reproduction_confirmation(confirmation, "P01", project), [])
            clean_path.write_text(json.dumps({**clean, "status": "changed"}), encoding="utf-8")
            self.assertTrue(any("stale" in error for error in validate_reproduction_confirmation(confirmation, "P01", project)))
            clean["metric_comparisons"][0]["reproduction_value"] = 0.50
            self.assertTrue(any("exceed" in error for error in validate_clean_room_reproduction(clean, "P01", project, registry)))


if __name__ == "__main__":
    unittest.main()
