import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from scripts import figure_output_qa as qa
from scripts.publication_figures import actual_figure_labels


class FigureAccessibilityTests(unittest.TestCase):
    def drawing(self, project, math_label=False):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        with matplotlib.rc_context({"svg.fonttype": "none", "pdf.fonttype": 42, "font.family": "DejaVu Sans"}):
            fig, ax = plt.subplots(figsize=(4, 3))
            ax.plot([0, 1], [0, 1], label="Comparator")
            ax.set_xlabel(r"$\alpha_i$" if math_label else "Recorded exposure")
            ax.set_ylabel("Measured outcome")
            ax.set_title("Verified panel", loc="left")
            ax.legend(title="Method")
            labels = actual_figure_labels(fig)
            outputs = []
            for ext in ("svg", "pdf"):
                target = project / f"figure.{ext}"
                fig.savefig(target, bbox_inches="tight")
                outputs.append({"path": target.name, "sha256": qa.sha(target)})
            plt.close(fig)
        return outputs, labels

    def test_actual_labels_and_absent_titles_checked_in_both_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            outputs, labels = self.drawing(project)
            roles = {item["role"] for item in labels}
            self.assertTrue({"xlabel", "ylabel", "title.left", "legend.label", "legend.title"}.issubset(roles))
            self.assertTrue(any("tick" in role for role in roles))
            result = qa.audit_outputs(project, outputs, expected_text=labels)
            self.assertEqual(result["errors"], [])
            result = qa.audit_outputs(project, outputs, expected_text=[*labels, {"text": "Absent required title", "role": "title.left"}])
            self.assertEqual(result["status"], "fail")

    def test_previews_are_separate_and_originals_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            outputs, labels = self.drawing(project)
            originals = {item["path"]: (project / item["path"]).read_bytes() for item in outputs}
            result = qa.audit_outputs(project, outputs, expected_text=labels)
            pdf = next(row for row in result["outputs"] if row["path"].endswith("pdf"))
            self.assertEqual({p["mode"] for p in pdf["color_vision_previews"]}, {"protan", "deutan", "tritan"})
            for preview in pdf["grayscale_previews"] + pdf["color_vision_previews"]:
                self.assertTrue(preview["path"].startswith("reports/figure-output-qa/"))
                self.assertEqual(preview["source_pdf_sha256"], pdf["sha256"])
                self.assertEqual(qa.sha(project / preview["path"]), preview["sha256"])
                with Image.open(project / preview["path"]) as image:
                    image.verify()
            for name, content in originals.items():
                self.assertEqual((project / name).read_bytes(), content)
            self.assertFalse(result["accessibility_verified"])
            self.assertTrue(result["visual_review_required"])

    def test_linear_srgb_transform_preserves_black_white_and_input(self):
        rgb = np.asarray([[0, 0, 0], [255, 255, 255], [255, 0, 0]], dtype=np.uint8)
        original = rgb.copy()
        for mode in qa.MACHADO_100:
            actual = qa.simulate_rgb(rgb, mode)
            np.testing.assert_array_equal(actual[:2], rgb[:2])
            self.assertFalse(np.array_equal(actual[2], rgb[2]))
        expected = round((1.055 * (0.114503 ** (1 / 2.4)) - 0.055) * 255)
        self.assertEqual(int(qa.simulate_rgb(rgb, "protan")[2, 1]), expected)
        np.testing.assert_array_equal(rgb, original)

    def test_final_size_uses_actual_pdf_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            outputs, labels = self.drawing(project)
            result = qa.audit_outputs(project, outputs, expected_text=labels)
            initial = next(row for row in result["outputs"] if row["path"].endswith("pdf"))["final_size_qa"][0]
            resized = qa.audit_outputs(project, outputs, expected_text=labels, final_width_mm=initial["actual_pdf_size_mm"][0] / 2)
            final = next(row for row in resized["outputs"] if row["path"].endswith("pdf"))["final_size_qa"][0]
            self.assertAlmostEqual(final["minimum_final_text_points"], initial["minimum_final_text_points"] / 2)
            self.assertEqual(final["status"], "review_required")
            self.assertFalse(final["manuscript_placement_verified"])

    def test_unknown_tex_commands_remain_unverified(self):
        checks, errors, pending = qa.verify_labels(["x"], [{"text": r"$\unknown{x}$", "role": "ylabel"}])
        self.assertEqual(checks[0]["status"], "review_required")
        self.assertFalse(checks[0]["glyphs_verified"])
        self.assertTrue(pending)

    def test_actual_math_glyphs_survive_both_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            outputs, labels = self.drawing(project, math_label=True)
            result = qa.audit_outputs(project, outputs, expected_text=labels)
            self.assertEqual(result["errors"], [])
            for row in result["outputs"]:
                math_label = next(item for item in row["label_checks"] if item["role"] == "xlabel")
                self.assertTrue(math_label["glyphs_verified"])
                self.assertFalse(math_label["mathematical_layout_verified"])


if __name__ == "__main__":
    unittest.main()
