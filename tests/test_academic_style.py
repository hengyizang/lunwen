from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.academic_style import (
    analyze_text,
    find_harper,
    find_proselint,
    run_harper,
    run_proselint,
    validate_saved_audit,
    write_audit,
)


MARKERS = " ".join((
    "adaptive archival asymmetric Bayesian calibrated comparative conditional",
    "constrained contextual diagnostic distributed dynamic empirical external",
    "federated granular hierarchical industrial longitudinal mechanical multivariate",
    "operational predictive probabilistic prospective randomized reproducible robust",
    "sequential sparse statistical structural temporal transferable transparent",
)).split()


def varied_manuscript() -> str:
    sentences = []
    for index, marker in enumerate(MARKERS):
        tail = " ".join(["under documented operating conditions"] * (index % 4))
        sentences.append(
            f"{marker.capitalize()} evaluation compared held-out measurements with "
            f"the preregistered baseline and reported uncertainty for each machine group {tail}."
        )
    return "\n\n".join(
        " ".join(sentences[index:index + 6])
        for index in range(0, len(sentences), 6)
    )


class AcademicStyleTests(unittest.TestCase):
    def test_repository_virtualenv_proselint_is_discovered_without_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / ".venv" / "bin" / "proselint"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            with patch("scripts.academic_style.ROOT", root), patch(
                "scripts.academic_style.shutil.which", return_value=None
            ):
                self.assertEqual(find_proselint(), str(executable))

    def test_repository_virtualenv_harper_is_discovered_without_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / ".venv" / "bin" / "harper-cli"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            with patch("scripts.academic_style.ROOT", root), patch(
                "scripts.academic_style.shutil.which", return_value=None
            ):
                self.assertEqual(find_harper(), str(executable))

    def test_varied_evidence_led_manuscript_passes(self) -> None:
        result = analyze_text(varied_manuscript())
        self.assertGreaterEqual(result["word_count"], 500)
        self.assertEqual(result["errors"], [])

    def test_template_repetition_requires_revision(self) -> None:
        sentence = (
            "It is important to note that this method plays a crucial role in the "
            "rapidly evolving field and provides a comprehensive understanding of results."
        )
        result = analyze_text(" ".join([sentence] * 30))
        self.assertTrue(result["errors"])
        self.assertTrue(result["duplicate_sentences"])
        self.assertGreater(len(result["stock_phrase_hits"]), 1)

    def test_github_informed_rules_produce_line_level_findings(self) -> None:
        filler = " ".join(
            f"Measurement {index} compared the registered baseline with held-out observations."
            for index in range(90)
        )
        result = analyze_text(
            "Certainly!\nIn today's rapidly evolving field, this is a game-changing "
            "framework. Experts agree that it could potentially improve performance.\n"
            + filler
        )
        findings = result["formulaic_pattern_findings"]
        self.assertTrue(any(item["rule_id"] == "chatbot-artifact" for item in findings))
        self.assertTrue(any(item["line"] == 1 for item in findings))
        self.assertTrue(result["errors"])

    def test_proselint_json_is_normalized_as_local_advice(self) -> None:
        payload = {
            "result": {
                "file:///tmp/manuscript.txt": {
                    "diagnostics": [
                        {
                            "check_path": "redundancy.misc",
                            "message": "Remove a redundant phrase.",
                            "pos": [4, 9],
                            "span": [51, 63],
                            "replacements": ["shorter"],
                        }
                    ]
                }
            }
        }

        def fake_runner(command: list[str], **kwargs: object) -> SimpleNamespace:
            self.assertIn("--config", command)
            self.assertFalse(kwargs.get("shell", False))
            return SimpleNamespace(stdout=__import__("json").dumps(payload), returncode=1)

        result = run_proselint(
            "This is sufficiently long source text.",
            executable="proselint",
            runner=fake_runner,
        )
        self.assertEqual(result["status"], "advisory")
        self.assertEqual(result["diagnostic_count"], 1)
        self.assertTrue(result["local_only"])
        self.assertFalse(result["detector"])
        self.assertEqual(result["diagnostics"][0]["line"], 4)

    def test_harper_json_is_normalized_as_local_advice(self) -> None:
        payload = [
            {
                "file": "/tmp/manuscript.txt",
                "lint_count": 1,
                "lints": [
                    {
                        "rule": "AnA",
                        "kind": "Grammar",
                        "span": {"char_start": 8, "char_end": 10},
                        "line": 1,
                        "column": 9,
                        "message": "Use 'a' instead.",
                        "suggestions": ["a"],
                        "matched_text": "an",
                    }
                ],
            }
        ]

        def fake_runner(command: list[str], **kwargs: object) -> SimpleNamespace:
            self.assertEqual(command[1:5], ["--no-color", "lint", "--format", "json"])
            self.assertFalse(kwargs.get("shell", False))
            return SimpleNamespace(stdout=__import__("json").dumps(payload), returncode=1)

        result = run_harper(
            "This is an test.", executable="harper-cli", runner=fake_runner
        )
        self.assertEqual(result["status"], "advisory")
        self.assertEqual(result["diagnostic_count"], 1)
        self.assertTrue(result["local_only"])
        self.assertFalse(result["detector"])
        self.assertEqual(result["diagnostics"][0]["check"], "AnA")

    def test_saved_audit_is_bound_to_current_manuscript_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            manuscript = project / "papers" / "P01" / "manuscript" / "main.tex"
            manuscript.parent.mkdir(parents=True)
            manuscript.write_text(varied_manuscript(), encoding="utf-8")
            _, report = write_audit(project, "P01")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["schema_version"], "1.2")
            self.assertEqual(
                [item["name"] for item in report["external_linters"]],
                ["proselint", "harper"],
            )
            self.assertEqual(len(report["reviewed_rule_sources"]), 3)
            self.assertEqual(validate_saved_audit(project / "papers" / "P01"), [])
            manuscript.write_text(varied_manuscript() + "\nA documented limitation remains.", encoding="utf-8")
            errors = validate_saved_audit(project / "papers" / "P01")
            self.assertTrue(any("stale" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
