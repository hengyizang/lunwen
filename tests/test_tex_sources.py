from __future__ import annotations
import binascii
import json
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import unittest
import zipfile
import zlib
from scripts import manuscript_audit,tex_sources,citation_audit,manuscript_language,submission_package,researchctl
from scripts.research_artifacts import write,sha


class TexSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.project=Path(self.temp.name)/"fixture";self.paper=self.project/"papers/P01";self.source=self.paper/"manuscript"
        (self.source/"sections").mkdir(parents=True);(self.source/"bib").mkdir();(self.paper/"reviews").mkdir()
        self.main=self.source/"main.tex"

    def files(self):
        self.main.write_text("\\documentclass{local}\n\\usepackage{localstyle}\n\\usepackage{graphicx}\n\\graphicspath{{../figures/}}\n\\begin{document}\n"
            "\\input{sections/front}\n\\maketitle\n\\input{sections/introduction}\n\\input{sections/results}\n"
            "\\includegraphics{source-image.png}\n\\input{sections/conclusion}\n\\bibliographystyle{plain}\n\\bibliography{bib/works}\n\\end{document}\n")
        (self.source/"sections/front.tex").write_text("\\title{Measured reliability}\n\\begin{abstract}Reliability is measured.\\end{abstract}\n")
        (self.source/"sections/introduction.tex").write_text("\\section{Research Question}\nReliability is evaluated.\n")
        (self.source/"sections/results.tex").write_text("\\section{Results}\nReliability increased and $\\frac{x}{n}=2$.\n")
        (self.source/"sections/conclusion.tex").write_text("\\section{Conclusion}\nReliability increased in this sample.\n")
        (self.source/"local.cls").write_text("\\NeedsTeXFormat{LaTeX2e}\n\\ProvidesClass{local}\n\\LoadClass{article}\n")
        (self.source/"localstyle.sty").write_text("\\ProvidesPackage{localstyle}\n\\input{definitions.tex}\n")
        (self.source/"definitions.tex").write_text("\\newcommand{\\fixtureword}{Fixture}\n")
        (self.source/"bib/works.bib").write_text("@misc{fixture,title={Synthetic fixture}}\n")
        (self.source/"unused-internal.tex").write_text("Unrelated private working notes must not enter the source package.\n")
        def chunk(kind,payload):return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",binascii.crc32(kind+payload)&0xffffffff)
        figures=self.paper/"figures";figures.mkdir(exist_ok=True)
        (figures/"source-image.png").write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(b"\x00\xff\xff\xff"))+chunk(b"IEND",b""))
        license_path=self.source/"LICENSE-local.txt";license_path.write_text("Synthetic author-owned sources are released under CC0 for packaging tests.\n")
        write(self.paper/"reviews/tex-dependency-rights.json",{"schema_version":"1.0","files":[
            {"path":"manuscript/"+name,"sha256":sha(self.source/name),"license":"CC0 synthetic author-owned test fixture","redistribution_allowed":True,
             "confirmed_by":"Synthetic Fixture Owner","license_evidence":{"path":"manuscript/LICENSE-local.txt","sha256":sha(license_path)}}
            for name in ("local.cls","localstyle.sty")]})
        write(self.paper/"reviews/venue-compliance.json",{"compile":{"status":"skipped_tool_missing"}})

    def test_expands_at_actual_include_position_and_preserves_original_line_locations(self):
        self.files();result=tex_sources.expand(self.main)
        self.assertLess(result.text.index("Reliability is measured"),result.text.index("Reliability is evaluated"))
        self.assertLess(result.text.index("\\frac{x}{n}"),result.text.index("Reliability increased in this sample"))
        self.assertEqual(result.locate(result.text.index("Reliability increased and")),{"path":"sections/results.tex","line":2})
        extracted=manuscript_language.tex_text(self.main)
        self.assertLess(extracted.index("Reliability is evaluated"),extracted.index("Reliability increased and"))

    def test_included_sections_and_symbols_are_really_audited(self):
        self.files();evidence=self.project/"evidence/result.csv";evidence.parent.mkdir();evidence.write_text("Reliability,2\n")
        facts={"schema_version":"1.0","facts":[{"id":"F1","statement":"Reliability increased","source_path":"evidence/result.csv","source_sha256":sha(evidence),"location":"row 1","verbatim_evidence":"Reliability,2"}],
            "claim_alignment":[{"claim_id":"C1","research_question":"Reliability?","canonical_claim":"Reliability increased in this sample.","allowed_inference":"descriptive","claim_strength":"descriptive","result_status":"supported","evidence_ids":["F1"],
                "sections":{"title":"reliability","abstract":"Reliability is measured","question":"Reliability is evaluated","results":"Reliability increased and","conclusion":"Reliability increased in this sample"}}],
            "measurement":[],"measurement_not_applicable_reason":"Direct recorded quantity in an isolated fixture.","argument_ledger":[{"paragraph_id":"P1","section":"results","function":"report","claim_id":"C1","inference_boundary":"Synthetic fixture only","transition":"conclusion","evidence_ids":["F1"],"text_anchor":"Reliability increased"}],
            "glossary":[],"symbols":[{"symbol":"x","definition":"change","first_use":"x","unit":"units"},{"symbol":"n","definition":"count","first_use":"n","unit":"units"}],"ignored_symbols":[]}
        spec=self.paper/"reviews/paper-facts.json";write(spec,facts)
        result=manuscript_audit.audit(self.project,self.main,spec)
        self.assertTrue(result["pass"],result["errors"])
        self.assertEqual(result["used_math_symbols"],["n","x"])
        location=next(r for r in result["source_locations"] if r["section"]=="results")
        self.assertEqual((location["path"],location["line"]),("sections/results.tex",2))
        facts["symbols"].pop();write(spec,facts)
        self.assertIn("undeclared mathematical symbols: n",manuscript_audit.audit(self.project,self.main,spec)["errors"])

    def test_closure_contains_only_required_source_bibliography_styles_and_license(self):
        self.files();selected=submission_package.select_files(self.paper)
        names={p.relative_to(self.paper).as_posix() for p in selected}
        self.assertTrue({"manuscript/sections/results.tex","manuscript/bib/works.bib","manuscript/local.cls","manuscript/localstyle.sty","manuscript/definitions.tex","manuscript/LICENSE-local.txt","figures/source-image.png"}<=names)
        self.assertNotIn("manuscript/unused-internal.tex",names)
        (self.paper/"reviews/tex-dependency-rights.json").unlink()
        with self.assertRaisesRegex(researchctl.ResearchCtlError,"redistribution-rights"):
            submission_package.select_files(self.paper)

    def test_cycles_traversal_missing_sources_symlinks_and_comment_includes(self):
        self.main.write_text("% \\input{does-not-exist}\n\\section{Results}OK")
        self.assertIn("OK",tex_sources.expand(self.main).text)
        self.main.write_text("\\input{sections/loop}")
        (self.source/"sections/loop.tex").write_text("\\input{main}")
        with self.assertRaisesRegex(ValueError,"Cyclic"):
            tex_sources.expand(self.main)
        self.main.write_text("\\input{../reviews/private}")
        with self.assertRaisesRegex(ValueError,"traversal"):
            tex_sources.expand(self.main)
        self.main.write_text("\\input{missing}")
        with self.assertRaisesRegex(ValueError,"Missing"):
            tex_sources.expand(self.main)
        self.main.write_text("\\input{alias}")
        target=self.source/"sections/real.tex";target.write_text("safe")
        (self.source/"alias.tex").symlink_to(target)
        with self.assertRaisesRegex(ValueError,"symlink"):
            tex_sources.expand(self.main)

    def test_citations_in_includes_and_changes_in_includes_affect_current_digest(self):
        self.files();target=self.source/"sections/results.tex"
        target.write_text(target.read_text()+"\\cite{fixture}")
        self.assertEqual(citation_audit.tex_citation_keys(self.main),{"fixture"})
        before=citation_audit.manuscript_digest(self.main)
        target.write_text(target.read_text()+" Changed evidence.")
        self.assertNotEqual(before,citation_audit.manuscript_digest(self.main))

    def test_internal_review_file_cannot_be_smuggled_as_a_graphic_dependency(self):
        self.files();(self.paper/"reviews/secret.pdf").write_bytes(b"internal")
        self.main.write_text(self.main.read_text()+"\\includegraphics{../reviews/secret.pdf}")
        with self.assertRaisesRegex(researchctl.ResearchCtlError,"Internal review material"):
            submission_package.select_files(self.paper)

    @unittest.skipUnless(shutil.which("pdflatex"),"Actual TeX compilation is exercised on the cloud TeX toolchain job")
    def test_selected_zip_sources_build_after_original_tree_is_unavailable(self):
        self.files();files=submission_package.select_files(self.paper)
        archive=Path(self.temp.name)/"sources.zip"
        with zipfile.ZipFile(archive,"w") as output:
            for path in files:output.write(path,path.relative_to(self.paper).as_posix())
        isolated=Path(self.temp.name)/"isolated";isolated.mkdir()
        with zipfile.ZipFile(archive) as output:output.extractall(isolated)
        shutil.rmtree(self.project)
        result=subprocess.run([shutil.which("pdflatex"),"-no-shell-escape","-interaction=nonstopmode","-halt-on-error","main.tex"],cwd=isolated/"manuscript",capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout[-3000:])
        self.assertTrue((isolated/"manuscript/main.pdf").is_file())


if __name__=="__main__":unittest.main()
