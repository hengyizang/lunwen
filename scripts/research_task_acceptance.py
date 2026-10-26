"""Render generated Mermaid in actual cloud Chromium using a pinned local bundle."""
from __future__ import annotations

import argparse
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Thread

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
    # Browser module imports from file: can remain pending when headless Chrome
    # dumps the page. Serve only the temporary pinned bundle and test fixtures
    # through loopback so network-idle accounting includes every module fetch.
    with tempfile.TemporaryDirectory(prefix="mermaid-acceptance-") as temporary:
        webroot = Path(temporary)
        shutil.copytree(mermaid_package / "dist", webroot / "mermaid")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(webroot)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root_url = "http://127.0.0.1:" + str(server.server_port)
        try:
            return _render_cases(directory, webroot, browser, root_url, package["version"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def _render_cases(directory, webroot, browser, root_url, version):
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
        page = webroot / f"mermaid-{number}.html"
        page.write_text('<!doctype html><meta charset="utf-8">' +
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\' \'self\'; style-src \'unsafe-inline\'; img-src data: \'self\'; font-src data: \'self\'">' +
            '<body data-status="pending"><div id="rendered"></div><script id="source" type="application/json">' + source + '</script>' +
            '<script type="module">try { document.body.dataset.status="importing"; const {default:mermaid}=await import(' + json.dumps(root_url + "/mermaid/mermaid.esm.min.mjs") + ');' +
            'document.body.dataset.status="rendering"; mermaid.initialize({startOnLoad:false,securityLevel:"strict",fontFamily:"Arial",flowchart:{htmlLabels:false}});' +
            'const code=JSON.parse(document.getElementById("source").textContent);await mermaid.parse(code);' +
            'const result=await mermaid.render("diagram",code);document.getElementById("rendered").innerHTML=result.svg;' +
            'document.body.dataset.nodes=String(document.querySelectorAll("g.node").length);' +
            'document.body.dataset.edges=String(document.querySelectorAll(".edgePaths path").length);' +
            'document.body.dataset.status="passed";' +
            '}catch(error){document.body.dataset.status="failed";document.body.dataset.error=String(error);}</script></body>', encoding="utf-8")
        shutil.copyfile(page, directory / page.name)
        run = subprocess.run([browser, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--enable-logging=stderr",
            "--dump-dom", "--virtual-time-budget=8000", root_url + "/" + page.name],
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
    report = {"status": "pass", "runtime": "actual_headless_chromium", "mermaid_version": version,
        "cases": cases, "paid_model_calls": 0, "scientific_validity_verified": False}
    write(directory / "mermaid-acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--mermaid-package", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.directory, args.mermaid_package), indent=2))
