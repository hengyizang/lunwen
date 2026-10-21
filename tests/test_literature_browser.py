"""Cloud-only software checks for the no-network reading viewer."""
import json
import re
from scripts import literature_browser as browser, literature_workbench as workbench
from tests.test_literature_workbench import WorkbenchFixture


class BrowserTests(WorkbenchFixture):
    def test_search_data_escapes_active_content_and_preserves_original_text(self):
        evil = '</script><img src=x onerror="alert(1)"> & \u2028'
        rendered = browser.markup({"documents": [{"text": evil}]})
        data = re.search(r'id="literature-search-data">(.*?)</script>', rendered, re.S).group(1)
        self.assertNotIn("<", data)
        self.assertEqual(json.loads(data)["documents"][0]["text"], evil)
        self.assertNotIn("innerHTML", browser.SCRIPT)
        self.assertNotIn("fetch(", browser.SCRIPT)
        self.assertNotIn("localStorage", browser.SCRIPT)

    def test_built_browser_has_search_filters_source_hashes_and_matching_csp(self):
        paper = self.add_paper("one", "The example describes a baseline with held-out devices.")
        self.card(paper, field="baseline")
        self.build()
        page = (self.project / workbench.OUTPUT / "index.html").read_text()
        self.assertIn('id="literature-search"', page)
        self.assertIn('id="reading-paper"', page)
        self.assertIn("script-src 'sha256-" + browser.script_hash(), page)
        data = json.loads(re.search(r'id="literature-search-data">(.*?)</script>', page, re.S).group(1))
        self.assertEqual(data["paperMappings"], ["P01"])
        self.assertEqual({row["kind"] for row in data["documents"]}, {"card", "fulltext"})
        self.assertTrue(all(row["sha256"] == paper["source"]["sha256"] for row in data["documents"]))
        self.assertTrue(all(row["href"].endswith("one.txt") for row in data["documents"]))

    def test_unchanged_build_keeps_reading_and_comparison_views(self):
        self.add_paper("one", "The baseline comparison uses device splits.")
        self.build()
        workbench.itinerary(self.project, "device splits")
        workbench.comparison_packet(self.project, ["one"], question="baseline comparison")
        before = self.output("itinerary.json"), self.output("comparison.json")
        self.assertTrue(self.build()["views_reused"])
        self.assertEqual(before, (self.output("itinerary.json"), self.output("comparison.json")))
