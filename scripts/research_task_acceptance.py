"""Render generated Mermaid in actual cloud Chromium using a pinned local bundle."""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess

from scripts import diagram_mermaid
from scripts.literaturectl import require_cloud
from scripts.research_artifacts import write


class Rendered(HTMLParser):
    def __init__(self):
        super().__init__()
        self.status, self.nodes, self.edges, self.error = None, None, None, None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "body":
            self.status, self.nodes, self.edges, self.error = (attrs.get("data-" + k) for k in ("status", "nodes", "edges", "error"))


def exercise(directory: Path, mermaid_package: Path) -> dict:
    require_cloud()
    package = json.loads((mermaid_package / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != "mermaid" or package.get("version") != "12.2.0":
        raise ValueError("Mermaid acceptance requires the exact declared 12.2.0 package")
    entry = mermaid_package / "dist/mermaid.esm.min.mjs"
    if not entry.is_file():
        raise ValueError("installed Mermaid browser bundle is missing")
    browser = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if browser is None:
        raise ValueError("actual Chromium is required for Mermaid acceptance")
    directory.mkdir(parents=True, exist_ok=True)
    base = {"schema_version": "1.0", "type": "mechanism", "title": "Proposed software fixture",
        "caption": "Proposed connections; no observed scientific result.", "alt_text": "Synthetic diagram fixture.",
        "claim_ids": ["software-fixture"], "output_stem": "papers/P01/figures/synthetic",
        "nodes": [{"id": "end", "label": 'Input "A" < B', "kind": "construct"},
            {"id": "middle", "label": "Method block", "kind": "process"},
            {"id": "output", "label": "Measured output", "kind": "output"}],
        "edges": [{"from": "end", "to": "middle", "kind": "association", "label": "Conditional relation"},
            {"from": "middle", "to": "output", "kind": "causal", "label": "Proposed effect"}]}
    cases = []
    for number, changed in enumerate((False, True), 1):
        if changed:
            base["nodes"][0]["label"] = 'Input "] --> injected["extra'
        code = diagram_mermaid.text(base)
        source = json.dumps(code).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        page = directory / f"mermaid-{number}.html"
        page.write_text('<!doctype html><meta charset="utf-8">' +
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\' file:; style-src \'unsafe-inline\'; img-src data: file:; font-src data: file:">' +
            '<body data-status="pending"><div id="rendered"></div><script id="source" type="application/json">' + source + '</script>' +
            '<script type="module">try { document.body.dataset.status="importing"; const {default:mermaid}=await import(' + json.dumps(entry.resolve().as_uri()) + ');' +
            'document.body.dataset.status="rendering"; mermaid.initialize({startOnLoad:false,securityLevel:"strict",fontFamily:"Arial",flowchart:{htmlLabels:false}});' +
            'const code=JSON.parse(document.getElementById("source").textContent);await mermaid.parse(code);' +
            'const result=await mermaid.render("diagram",code);document.getElementById("rendered").innerHTML=result.svg;' +
            'document.body.dataset.nodes=String(document.querySelectorAll("g.node").length);' +
            'document.body.dataset.edges=String(document.querySelectorAll(".edgePaths path").length);' +
            'document.body.dataset.status="passed";' +
            '}catch(error){document.body.dataset.status="failed";document.body.dataset.error=String(error);}</script></body>', encoding="utf-8")
        run = subprocess.run([browser, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--enable-logging=stderr",
            "--allow-file-access-from-files", "--dump-dom", "--virtual-time-budget=8000", page.resolve().as_uri()],
            capture_output=True, text=True, timeout=60, check=True)
        parsed = Rendered()
        parsed.feed(run.stdout)
        (directory / f"mermaid-{number}.rendered.html").write_text(run.stdout, encoding="utf-8")
        (directory / f"mermaid-{number}.stderr.log").write_text(run.stderr, encoding="utf-8")
        if parsed.status != "passed" or parsed.nodes != "3" or parsed.edges != "2":
            raise ValueError("actual Mermaid render failed: " + json.dumps({"status": parsed.status,
                "nodes": parsed.nodes, "edges": parsed.edges, "error": parsed.error,
                "browser_diagnostics": run.stderr[-3000:]}))
        cases.append({"case": number, "actual_nodes": int(parsed.nodes), "actual_edges": int(parsed.edges),
                      "status": "passed", "untrusted_label_test": changed})
    report = {"status": "pass", "runtime": "actual_headless_chromium", "mermaid_version": package["version"],
        "cases": cases, "paid_model_calls": 0, "scientific_validity_verified": False}
    write(directory / "mermaid-acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--mermaid-package", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.directory, args.mermaid_package), indent=2))
