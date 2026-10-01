from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import output_provenance
from scripts.local_library import obsidian_graph, zotero_local
from scripts.manuscript_audit import audit
from scripts.manuscript_docx import approve_visual_review, build, validate_saved_report
from scripts.publication_figures import render, sha256_file
from scripts.requirements_trace import validate as validate_requirements
from scripts.research_diagrams import render as render_diagram
from scripts import research_mcp
from scripts.research_mcp import context, handle, route_request
from scripts.skill_catalog import apply_operation, lint_skill, mcp_inventory, plan_operation
from scripts.systematic_review import validate_completed_checklist
from scripts.task_router import plan as route_plan


class _Response:
    def __init__(self, value: object):
        self.payload = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.payload


class P0P1CompletionTests(unittest.TestCase):
    def test_chat_mcp_routes_without_paid_or_submission_actions(self):
        routed = route_request("demo-study", "请检查 P03 的引用和 DOI")
        self.assertEqual((routed["paper"], routed["skill"]), ("P03", "citations"))
        self.assertFalse(routed["paid_call_started"])
        response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual({row["name"] for row in response["result"]["tools"]},
                         {"research_context", "research_projects", "research_route", "research_status"})

    def test_chat_context_discovers_project_and_stops_at_human_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "projects" / "doctoral-study" / "state"
            state.mkdir(parents=True)
            (state / "run.json").write_text(json.dumps({
                "stage": "topic-intelligence", "gate": "G1", "status": "awaiting_approval",
                "active_paper": "P01"
            }), encoding="utf-8")
            with patch.object(research_mcp, "ROOT", root):
                value = context("继续当前工作")
                self.assertEqual(value["project"], "doctoral-study")
                self.assertEqual(value["project_resolution"], "automatic-single-project")
                self.assertEqual(value["skill"], "continue")
                self.assertTrue(value["must_stop"])
                self.assertEqual(value["human_action"], "approve-or-reopen-gate")
                self.assertFalse(value["paid_call_started"])
                self.assertFalse(value["paid_call_authorized"])

    def test_chat_context_requires_selection_or_initialization_without_guessing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(research_mcp, "ROOT", root):
                self.assertTrue(context("开始研究")["initialization_required"])
                for slug in ("study-one", "study-two"):
                    state = root / "projects" / slug / "state"
                    state.mkdir(parents=True)
                    (state / "run.json").write_text(json.dumps({"stage": "intake", "gate": "G0", "status": "awaiting_work", "active_paper": "P01"}), encoding="utf-8")
                value = context("继续")
                self.assertTrue(value["selection_required"])
                self.assertEqual(value["candidates"], ["study-one", "study-two"])

    def test_windows_installer_normalizes_wsl_names_from_powershell_51(self):
        installer = (Path(__file__).parents[1] / "scripts" / "install-d-drive.ps1").read_text(encoding="utf-8")
        self.assertIn('([string]$_ -replace "`0", \'\').Trim()', installer)
        self.assertIn("$wslNames -notcontains $Distribution", installer)
        self.assertNotIn("$wslList -notmatch", installer)

    def test_windows_installer_avoids_forwarding_backslash_path_to_wslpath(self):
        installer = (Path(__file__).parents[1] / "scripts" / "install-d-drive.ps1").read_text(encoding="utf-8")
        self.assertNotIn("wslpath -a $actual", installer)
        self.assertIn("--cd $requiredWslRoot -- pwd -P", installer)
        self.assertIn('($wslOutput -join "`n") -replace "`0", \'\'', installer)

    def test_windows_installer_uses_nonmutating_lf_bootstrap_copy(self):
        root = Path(__file__).parents[1]
        installer = (root / "scripts" / "install-d-drive.ps1").read_text(encoding="utf-8")
        bootstrap = (root / "scripts" / "bootstrap-d-drive.sh").read_text(encoding="utf-8")
        attributes = (root / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn('Replace("`r`n", "`n").Replace("`r", "`n")', installer)
        self.assertIn("[Text.UTF8Encoding]::new($false)", installer)
        self.assertIn("WriteAllText($runtimeBootstrapPath", installer)
        self.assertNotIn("WriteAllText($bootstrapPath", installer)
        self.assertIn('env "DR_OS_REPO_ROOT=$requiredWslRoot" bash $runtimeBootstrapWslPath', installer)
        self.assertIn('repo_root="${DR_OS_REPO_ROOT:-', bootstrap)
        self.assertIn("*.sh text eol=lf", attributes)

    def test_windows_installer_provisions_venv_and_repairs_missing_pip(self):
        root = Path(__file__).parents[1]
        installer = (root / "scripts" / "install-d-drive.ps1").read_text(encoding="utf-8")
        bootstrap = (root / "scripts" / "bootstrap-d-drive.sh").read_text(encoding="utf-8")
        self.assertIn("dpkg-query -W python3-venv", installer)
        self.assertIn("-u root -- sh -lc $prerequisiteCommand", installer)
        self.assertLess(installer.index("dpkg-query -W python3-venv"), installer.index("bash $runtimeBootstrapWslPath"))
        self.assertIn(".venv/bin/python -m pip --version", bootstrap)
        self.assertIn("python3 -m venv --clear .venv", bootstrap)

    def test_genuine_docx_requires_non_claude_sources_and_named_visual_review(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "study"
            manuscript = project / "papers" / "P01" / "manuscript"
            manuscript.mkdir(parents=True)
            source = manuscript / "source.md"
            source.write_text("# Introduction\n\nMeasured evidence supports the bounded claim.\n")
            metadata = manuscript / "metadata.json"
            metadata.write_text(json.dumps({"schema_version": "1.0", "title": "Bounded evidence",
                "abstract": "This study evaluates a prespecified claim.",
                "authors": [{"name": "Researcher"}],
                "keywords": ["evidence", "audit", "reproducibility"]}))
            output_provenance.record_model_writes(project, [source, metadata], family="openai",
                provider="gateway", model="gpt", role="manuscript", run_id="writer-1")
            output = manuscript / "main.docx"
            report = build(project, source, metadata, output, prefer_pandoc=False)
            self.assertEqual(report["engine"], "python-docx")
            self.assertTrue(output.is_file())
            paper = project / "papers" / "P01"
            self.assertIn("named, completed visual", " ".join(validate_saved_report(paper)))
            approve_visual_review(project, paper, "Researcher")
            self.assertEqual(validate_saved_report(paper), [])
            source.write_text(source.read_text() + "\nA later unbuilt edit.\n")
            self.assertIn("changed after the build", " ".join(validate_saved_report(paper)))

    def test_manuscript_audit_requires_declared_math_symbols_and_all_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "study"; paper = project / "papers" / "P01"; paper.mkdir(parents=True)
            manuscript = paper / "draft.tex"
            manuscript.write_text("\\title{Measured reliability}\\begin{abstract}Reliability is measured.\\end{abstract}"
                "\\section{Research Question}Reliability is evaluated."
                "\\section{Results}Reliability increased and $x=2$."
                "\\section{Conclusion}Reliability increased in this sample.")
            source = paper / "result.csv"; source.write_text("reliability,2\n")
            facts = {"schema_version": "1.0",
                "facts": [{"id": "F1", "statement": "Reliability increased", "source_path": "papers/P01/result.csv",
                    "source_sha256": sha256_file(source), "location": "row 1", "verbatim_evidence": "reliability,2"}],
                "claim_alignment": [{"claim_id": "C1", "research_question": "Reliability?",
                    "canonical_claim": "Reliability increased in this sample.", "allowed_inference": "descriptive",
                    "claim_strength": "descriptive", "result_status": "supported", "evidence_ids": ["F1"],
                    "sections": {"title": "reliability", "abstract": "Reliability", "question": "Reliability", "results": "Reliability", "conclusion": "Reliability"}}],
                "measurement": [], "measurement_not_applicable_reason": "Directly reported outcome.",
                "argument_ledger": [{"paragraph_id": "P1", "section": "results", "function": "report",
                    "claim_id": "C1", "inference_boundary": "descriptive", "transition": "conclusion",
                    "evidence_ids": ["F1"], "text_anchor": "Reliability increased"}],
                "glossary": [], "symbols": [], "ignored_symbols": []}
            spec = paper / "facts.json"; spec.write_text(json.dumps(facts))
            self.assertIn("undeclared mathematical symbols: x", audit(project, manuscript, spec)["errors"])
            facts["symbols"] = [{"symbol": "x", "definition": "Reliability change", "first_use": "x", "unit": "units", "forbidden_variants": []}]
            spec.write_text(json.dumps(facts))
            self.assertTrue(audit(project, manuscript, spec)["pass"])

    def test_all_eight_extended_scientific_recipes_render_vector_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "study"; data = project / "results"; figures = project / "papers" / "P01" / "figures"
            data.mkdir(parents=True); figures.mkdir(parents=True)
            tables = {
                "ba.csv": "x,y\n1,-.1\n2,.2\n",
                "km.csv": "group,x,y,risk\nA,0,1,20\nA,1,.8,14\nA,2,.6,8\n",
                "shap.csv": "x,y,value\n-.2,age,.1\n.3,age,.8\n.1,size,.4\n",
                "nom.csv": "x,y,end\nage,0,40\nsize,10,80\n",
                "decision.csv": "x,y\n0,.1\n.5,.2\n1,.05\n",
                "graph.csv": "x,y,value\nA,B,2\nB,C,1\n",
                "geo.csv": "x,y,value\n10,20,2\n30,40,4\n"}
            for name, body in tables.items(): (data / name).write_text(body)
            base = {"schema_version": "1.0", "data": "results/ba.csv", "style": "high-impact",
                "formats": ["svg", "pdf"], "dpi": 300, "caption": "Precomputed scientific summaries.",
                "alt_text": "Panels display prespecified analyses.", "claim_ids": ["C1"]}
            panels = [
                {"kind": "bland_altman", "data": "results/ba.csv", "x": "x", "y": "y", "xlabel": "Mean", "ylabel": "Difference", "mean_difference": 0, "loa_lower": -.5, "loa_upper": .5},
                {"kind": "kaplan_meier", "data": "results/km.csv", "x": "x", "y": "y", "risk": "risk", "hue": "group", "xlabel": "Time", "ylabel": "Survival"},
                {"kind": "shap_summary", "data": "results/shap.csv", "x": "x", "y": "y", "value": "value", "xlabel": "SHAP value", "ylabel": "Feature"},
                {"kind": "nomogram", "data": "results/nom.csv", "x": "x", "y": "y", "end": "end", "xlabel": "Points", "ylabel": "Variable"},
                {"kind": "decision_curve", "data": "results/decision.csv", "x": "x", "y": "y", "xlabel": "Threshold", "ylabel": "Net benefit"}]
            first = figures / "clinical.spec.json"; first.write_text(json.dumps({**base, "output_stem": "papers/P01/figures/clinical", "panels": panels}))
            self.assertEqual(len(render(project, first)["outputs"]), 2)
            second_panels = [{"kind": kind, "data": "results/graph.csv", "x": "x", "y": "y", "value": "value", "xlabel": "Node", "ylabel": "Node"} for kind in ("network", "chord")]
            second_panels.append({"kind": "geospatial", "data": "results/geo.csv", "x": "x", "y": "y", "value": "value", "xlabel": "Longitude", "ylabel": "Latitude"})
            second = figures / "systems.spec.json"; second.write_text(json.dumps({**base, "output_stem": "papers/P01/figures/systems", "panels": second_panels}))
            self.assertEqual(len(render(project, second)["outputs"]), 2)

    def test_typed_research_diagram_renders_cycle_and_edge_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "study"; figures = project / "papers" / "P01" / "figures"; figures.mkdir(parents=True)
            spec = {"schema_version": "1.0", "type": "mechanism", "title": "Mechanism loop", "caption": "A bounded conceptual cycle.",
                "alt_text": "Intervention and outcome form a feedback loop.", "claim_ids": ["C1"], "output_stem": "papers/P01/figures/mechanism",
                "nodes": [{"id": "a", "label": "Intervention", "kind": "construct"}, {"id": "b", "label": "Outcome", "kind": "output"}],
                "edges": [{"from": "a", "to": "b", "label": "changes", "kind": "causal"}, {"from": "b", "to": "a", "label": "feedback", "kind": "feedback"}]}
            path = figures / "mechanism.json"; path.write_text(json.dumps(spec))
            result = render_diagram(project, path)
            self.assertEqual(len(result["outputs"]), 3)
            positions = json.loads((figures / "mechanism.layout.json").read_text())["node_positions"]
            self.assertGreater(positions["a"][0], 0)
            self.assertLess(positions["b"][0], 0)

    def test_local_zotero_obsidian_and_token_gated_skill_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = root / "study"; vault = root / "vault"; vault.mkdir()
            (vault / "One.md").write_text("# One\n[[Two]] #method")
            (vault / "Two.md").write_text("# Two\nDOI 10.1234/demo")
            indexed = obsidian_graph(vault, project, "Researcher", project / "evidence" / "local-library" / "index.json")
            self.assertEqual((indexed["notes"], indexed["links"]), (2, 1))
            items = [{"key": "A", "data": {"itemType": "journalArticle", "title": "Paper", "DOI": "10.1234/demo", "creators": []}}]
            zotero = zotero_local(project, "Researcher", project / "evidence" / "local-library" / "zotero.json", opener=lambda *_args, **_kwargs: _Response(items))
            self.assertEqual(zotero["item_count"], 1)
            roots = root / "skills"; skill = roots / "sample"; skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: sample\ndescription: Audit evidence safely.\n---\n# Sample\n")
            self.assertFalse(lint_skill(skill)["blocked"])
            catalog = root / "catalog"; install = root / "installed"
            planned = plan_operation(skill, [roots], catalog, "install", install)
            installed = Path(apply_operation(catalog, planned["token"])["installed"])
            self.assertTrue((installed / "SKILL.md").is_file())
            config = root / "mcp.json"; config.write_text(json.dumps({"mcpServers": {"local": {"type": "stdio", "command": "python3", "args": ["server.py"]}}}))
            self.assertTrue(mcp_inventory([config])[0]["safe"])

    def test_router_avoids_recently_failed_model_and_completed_prisma_is_strict(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "study"; (project / "state").mkdir(parents=True)
            stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            (project / "state" / "model-health.jsonl").write_text(json.dumps({"provider": "openai", "model": "fast", "checked_at": stamp, "status": "failed"}) + "\n")
            candidates = {"metadata-extraction": [{"provider": "openai", "model": "standard2", "tier": "standard", "priority": 1}]}
            rates = {name: {"input_per_million": price, "output_per_million": price} for name, price in (("fast", 1), ("standard2", 2), ("premium", 10))}
            with patch("scripts.task_router.ai_providers.configuration", return_value={"model": "premium"}), patch.dict("os.environ", {
                "DR_OS_FAST_OPENAI_MODEL": "fast", "DR_OS_ROUTING_CANDIDATES_JSON": json.dumps(candidates),
                "DR_OS_MODEL_PRICING_JSON": json.dumps(rates)}, clear=False):
                selected = route_plan(project, "metadata-extraction", "openai", "extract metadata")
            self.assertEqual(selected["model"], "standard2")
            checklist = {"signed_by": "Researcher", "signed_at": "2026-09-27",
                "PRISMA_2020": [{"item_number": str(n), "status": "complete", "manuscript_location": f"p. {n}"} for n in range(1, 28)],
                "PRISMA_S": [{"item_number": str(n), "status": "not_applicable", "manuscript_location": "Protocol rationale"} for n in range(1, 17)]}
            path = project / "checklist.json"; path.write_text(json.dumps(checklist))
            self.assertEqual(validate_completed_checklist(path), [])

    def test_requirement_trace_is_closed_without_claiming_research_completion(self):
        self.assertEqual(validate_requirements(), [])
        matrix = json.loads((Path(__file__).parents[1] / "config" / "requirements-traceability.json").read_text())
        final = next(row for row in matrix["requirements"] if row["id"] == "R24")
        self.assertEqual((final["implementation"], final["acceptance"]), ("not-started", "research-not-yet-executed"))


if __name__ == "__main__":
    unittest.main()
