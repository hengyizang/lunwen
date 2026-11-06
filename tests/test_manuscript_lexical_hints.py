"""Lexical advice remains advisory and never stands in for scientific review."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts import manuscript_audit


class ManuscriptLexicalHintsTests(unittest.TestCase):
    def audit(self, claim, evidence):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / "source.txt"
            source.write_text(evidence, encoding="utf-8")
            manuscript = project / "paper.tex"
            manuscript.write_text("\\title{Scope}\n\\begin{abstract}Scope. " + claim +
                "\\end{abstract}\n\\section{Introduction}Scope.\n\\section{Results}Scope. " + claim +
                "\n\\section{Conclusion}Scope. " + claim, encoding="utf-8")
            spec = project / "facts.json"
            spec.write_text(json.dumps({"schema_version": "1.0", "facts": [{
                "id": "F1", "statement": "Synthetic recorded source excerpt", "source_path": "source.txt",
                "source_sha256": manuscript_audit.sha256_file(source), "location": "line 1", "verbatim_evidence": evidence}],
                "claim_alignment": [{"claim_id": "C1", "research_question": "What is supported?", "canonical_claim": claim,
                    "allowed_inference": "descriptive", "claim_strength": "descriptive", "result_status": "supported",
                    "evidence_ids": ["F1"], "sections": {key: "Scope" for key in manuscript_audit.SECTION}}],
                "measurement": [], "measurement_not_applicable_reason": "Synthetic wording fixture; no construct measurement.",
                "argument_ledger": [{"paragraph_id": "P1", "section": "results", "function": "report", "claim_id": "C1",
                    "evidence_ids": ["F1"], "inference_boundary": "Synthetic wording only", "transition": "Conclusion"}],
                "glossary": [], "symbols": []}), encoding="utf-8")
            return manuscript_audit.audit(project, manuscript, spec)

    def test_wherever_claim_against_bounded_excerpt_warns_without_blocking(self):
        result = self.audit("The method applies wherever measurements are available.",
                            "The method applies to many qualitatively different samples.")
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["pass"])
        self.assertTrue(any("lexical overclaim hint" in warning and "wherever" in warning
                            and "advisory only" in warning for warning in result["warnings"]))

    def test_corresponding_scope_and_comparison_wording_is_not_flagged(self):
        for claim, evidence in (
            ("Every measured sample has a recorded response.", "Every measured sample has a recorded response."),
            ("The comparator performed better on the measured task.", "The comparator outperformed the baseline on the measured task.")):
            with self.subTest(claim=claim):
                result = self.audit(claim, evidence)
                self.assertTrue(result["pass"])
                self.assertFalse(any("lexical overclaim hint" in warning for warning in result["warnings"]))

    def test_nonlexical_overclaim_is_not_claimed_to_be_detected(self):
        result = self.audit("We establish reproducible workflows.", "We provide a notebook example for analysis.")
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["pass"])
        self.assertFalse(any("lexical overclaim hint" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
