"""Regression tests for offline skill indexing and task routing."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import skill_router as sr  # noqa: E402


def make_skill(folder: Path, name: str, description: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nBody text.\n",
                    encoding="utf-8")
    return path


class SkillRouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="skill-router-test-"))
        make_skill(self.tmp / "skills" / "alpha", "alpha-search",
                   "Search literature and retrieve counterevidence from recent papers")
        make_skill(self.tmp / "skills" / "beta", "beta-figures",
                   "Render editable scientific figures and check panel alignment")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_chinese_task_routes_to_the_right_subskill(self):
        index = sr.build_index([self.tmp], 100, False, None)
        self.assertEqual(index["count"], 2)
        picks = sr.route(index, "检索最新论文的反证", 1)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["name"], "alpha-search")
        picks = sr.route(index, "生成可编辑主图面板对齐", 1)
        self.assertEqual(picks[0]["name"], "beta-figures")

    def test_index_is_incremental_by_hash(self):
        first = sr.build_index([self.tmp], 100, False, None)
        second = sr.build_index([self.tmp], 100, False, first)
        a = next(iter(first["files"].values()))
        b = next(iter(second["files"].values()))
        self.assertEqual(a["sha256"], b["sha256"])
        self.assertEqual(a["name_tokens"], b["name_tokens"])
        changed = make_skill(self.tmp / "skills" / "alpha", "alpha-renamed",
                             "Find rival explanations and novel queries")
        self.assertNotEqual(sr._sha(changed.read_bytes()), b["sha256"])
        third = sr.build_index([self.tmp], 100, False, first)
        refreshed = [r for r in third["files"].values() if r["name"] == "alpha-renamed"]
        self.assertEqual(len(refreshed), 1)

    def test_packet_embeds_full_text_and_hashes(self):
        index = sr.build_index([self.tmp], 100, False, None)
        picks = sr.route(index, "检索反证", 1)
        packet = sr.make_packet(index, "检索反证", picks, ["AGENTS.md"])
        self.assertTrue(packet["advisory_only"])
        self.assertEqual(len(packet["selected"]), 1)
        self.assertTrue(packet["selected"][0]["content"].startswith("---"))
        self.assertEqual(packet["selected"][0]["content_sha256"],
                         sr._sha(packet["selected"][0]["content"].encode("utf-8")))
        self.assertEqual(len(packet["included_files"]), 1)
        self.assertTrue(packet["index_sha256"])

    def test_include_rejects_paths_outside_repository(self):
        index = sr.build_index([self.tmp], 100, False, None)
        with self.assertRaises(ValueError):
            sr.make_packet(index, "x", [], ["../outside.md"])
        with self.assertRaises(ValueError):
            sr.make_packet(index, "x", [], ["AGENTS.md", "missing-file.md"])

    def test_empty_task_returns_no_matches(self):
        index = sr.build_index([self.tmp], 100, False, None)
        self.assertEqual(sr.route(index, "", 5), [])


if __name__ == "__main__":
    unittest.main()
