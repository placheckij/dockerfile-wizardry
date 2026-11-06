import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
SKILL_DIR = ROOT / "skills" / "dockerfile-wizardry"
SKILL = SKILL_DIR / "SKILL.md"
RULES = SKILL_DIR / "references" / "rules.md"
NAME = "dockerfile-wizardry"
RULE_ID = re.compile(r"DW-[A-Z]+-\d+")
# the Limits section names the TRADE-OFF rules: "the `TRADE-OFF` rules (DW-..., DW-...)"
TRADE_OFF_LIST = re.compile(r"the `TRADE-OFF` rules \(([^)]*)\)")
# Claude Code replaces these in SKILL.md with the skill's arguments when it loads the skill,
# code spans included, so an awk `$1` would arrive as the user's argument
ARGUMENT_PLACEHOLDER = re.compile(r"\$(?:ARGUMENTS|[0-9])")


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


def rule_strengths(text):
    """{rule id: strength} from the `## <id>: ...` headings of references/rules.md."""
    strengths = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"## (DW-[A-Z]+-\d+):", line)
        if heading:
            current = heading.group(1)
            strengths[current] = None
            continue
        strength = re.match(r"Strength: ([A-Z-]+)\.", line)
        if strength and current and strengths[current] is None:
            strengths[current] = strength.group(1)
    return strengths


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

    def test_skill_cites_only_existing_rules(self):
        cited = set(RULE_ID.findall(SKILL.read_text(encoding="utf-8")))
        known = rule_strengths(RULES.read_text(encoding="utf-8"))
        self.assertTrue(cited, "SKILL.md cites no rule ids")
        self.assertEqual(
            sorted(cited - set(known)), [], "SKILL.md cites ids rules.md does not have"
        )

    def test_skill_has_no_argument_placeholders(self):
        lines = SKILL.read_text(encoding="utf-8").splitlines()
        found = [
            f"line {number}: {line.strip()}"
            for number, line in enumerate(lines, 1)
            if ARGUMENT_PLACEHOLDER.search(line)
        ]
        self.assertEqual(
            found,
            [],
            "SKILL.md uses $ARGUMENTS or $<n>, which the skill's arguments replace",
        )

    def test_skill_trade_off_list_matches_rules(self):
        lists = TRADE_OFF_LIST.findall(SKILL.read_text(encoding="utf-8"))
        self.assertEqual(len(lists), 1, "SKILL.md should list the TRADE-OFF rules once")
        stated = set(RULE_ID.findall(lists[0]))
        known = rule_strengths(RULES.read_text(encoding="utf-8"))
        trade_offs = {
            rule for rule, strength in known.items() if strength == "TRADE-OFF"
        }
        self.assertTrue(trade_offs, "rules.md has no TRADE-OFF rules")
        self.assertEqual(sorted(stated), sorted(trade_offs))


if __name__ == "__main__":
    unittest.main()
