import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
SKILL_DIR = ROOT / "skills" / "dockerfile-wizardry"
SKILL = SKILL_DIR / "SKILL.md"
NAME = "dockerfile-wizardry"


def front_matter(text):
    """Return the `key: value` pairs of the leading `---` block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md does not start with a --- front matter block")
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        key, sep, value = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            fields[key.strip()] = value.strip()
    raise ValueError("SKILL.md front matter is not closed with ---")


class PluginManifestTest(unittest.TestCase):
    def test_names_agree(self):
        plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
        marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        skill = front_matter(SKILL.read_text(encoding="utf-8"))
        self.assertEqual(plugin["name"], NAME)
        self.assertEqual(marketplace["plugins"][0]["name"], NAME)
        self.assertEqual(skill.get("name"), NAME)

    def test_marketplace_points_at_repo_root(self):
        marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        self.assertEqual(len(marketplace["plugins"]), 1)
        self.assertEqual(marketplace["plugins"][0]["source"], "./")

    def test_skill_mentions_only_existing_references(self):
        text = SKILL.read_text(encoding="utf-8")
        paths = set(re.findall(r"references/[\w./*-]*[\w*]", text))
        self.assertTrue(paths, "SKILL.md names no references/ files")
        for path in sorted(paths):
            with self.subTest(path=path):
                self.assertTrue(
                    list(SKILL_DIR.glob(path)),
                    f"SKILL.md names {path}, which is not under {SKILL_DIR}",
                )


if __name__ == "__main__":
    unittest.main()
