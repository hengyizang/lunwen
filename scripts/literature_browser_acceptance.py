"""Exercise the generated no-network search UI in actual headless Chromium."""
from __future__ import annotations
import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlencode
from scripts.literaturectl import require_cloud
from scripts.research_artifacts import write


class SearchResult(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_results = False
        self.links = []
        self.in_status = False
        self.status = ""

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id") == "reading-results":
            self.in_results = True
        if values.get("id") == "reading-status":
            self.in_status = True
        if self.in_results and tag == "a":
            self.links.append(values.get("href"))

    def handle_endtag(self, tag):
        if tag == "ol":
            self.in_results = False
        if tag == "p":
            self.in_status = False

    def handle_data(self, data):
        if self.in_status:
            self.status += data


def exercise(directory: Path) -> dict:
    require_cloud()
    browser = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser:
        raise ValueError("Actual Chromium is required for browser acceptance")
    page = (directory / "fixture-project/reports/literature-workbench/index.html").resolve()
    if not page.is_file():
        raise ValueError("Build the linked reading fixture before browser acceptance")
    cases = []
    for params, expected in (({"q": "baseline"}, "fixture-a"),
                             ({"q": "calibration", "paper": "P02", "material": "fulltext"}, "fixture-b"),
                             ({"q": "no_matching_word_91377"}, None)):
        process = subprocess.run([browser, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
            "--allow-file-access-from-files", "--dump-dom", "--virtual-time-budget=1500",
            page.as_uri() + "?" + urlencode(params)], capture_output=True, text=True, timeout=40, check=True)
        result = SearchResult()
        result.feed(process.stdout)
        if not result.status or (expected is None and result.links) or (
                expected is not None and not any(expected in link for link in result.links)):
            raise ValueError("Actual browser search failed: " + json.dumps({"query": params, "status": result.status,
                                                                          "links": result.links}))
        cases.append({"query": params, "status": result.status, "source_links": result.links})
    report = {"status": "pass", "runtime": "actual_headless_chromium", "cases": cases,
              "paid_model_calls": 0, "scientific_completion_verified": False}
    write(directory / "browser-acceptance.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/literature-workbench"))
    print(json.dumps(exercise(parser.parse_args().directory), indent=2))
