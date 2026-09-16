from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.academic_style import (
    analyze_text,
    find_proselint,
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

    def test_saved_audit_is_bound_to_current_manuscript_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            manuscript = project / "papers" / "P01" / "manuscript" / "main.tex"
            manuscript.parent.mkdir(parents=True)
            manuscript.write_text(varied_manuscript(), encoding="utf-8")
            _, report = write_audit(project, "P01")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["schema_version"], "1.1")
            self.assertEqual(report["external_linters"][0]["name"], "proselint")
            self.assertEqual(validate_saved_audit(project / "papers" / "P01"), [])
            manuscript.write_text(varied_manuscript() + "\nA documented limitation remains.", encoding="utf-8")
            errors = validate_saved_audit(project / "papers" / "P01")
            self.assertTrue(any("stale" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
