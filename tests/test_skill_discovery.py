"""Generated discovery entries retain one native instruction source."""
import tempfile
from pathlib import Path
import unittest

from scripts import skill_discovery as discovery


class SkillDiscoveryTests(unittest.TestCase):
    def test_exact_old_copy_migrates_and_reinstall_preserves_local_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "skills/example/SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_text("---\nname: example\ndescription: A native example.\n---\n\nOriginal instructions.\n", encoding="utf-8")
            target = root / ".agents/skills/example/SKILL.md"
            target.parent.mkdir(parents=True)
            target.write_bytes(source.read_bytes())
            discovery.install(root, "example")
            self.assertTrue(discovery.current(root, "example"))
            self.assertIn("`skills/example/SKILL.md`", target.read_text())
            self.assertNotIn("Original instructions.", target.read_text())
            before = target.read_bytes()
            discovery.install(root, "example")
            self.assertEqual(target.read_bytes(), before)
            target.write_text(target.read_text() + "Local customization.\n", encoding="utf-8")
            changed = target.read_bytes()
            with self.assertRaisesRegex(ValueError, "Preserve changed"):
                discovery.install(root, "example")
            self.assertEqual(target.read_bytes(), changed)

    def test_missing_discovery_generates_but_symlink_cannot_redirect_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "skills/example/SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_text("---\nname: example\ndescription: Native rules.\n---\n", encoding="utf-8")
            discovery.install(root, "example")
            target = root / ".agents/skills/example/SKILL.md"
            target.unlink()
            target.symlink_to(source)
            with self.assertRaisesRegex(ValueError, "symlink"):
                discovery.install(root, "example")
            self.assertIn("Native rules.", source.read_text())
