import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_rules  # noqa: E402

RULE = """\
## DW-BASE-01: Pin the base image by digest
strength: MUST
spells:
- 1
last_verified: 2026-11-02
statement: |
  Reference the base image by `tag@sha256:digest`.
why: |
  A republished tag cannot change which bytes you build on.
how_to_check: |
  manual
sources:
- https://docs.docker.com/build/building/best-practices/#pin-base-image-versions
"""


class RuleFileTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path


class ParseRuleFileTest(RuleFileTestCase):
    def test_parses_a_valid_rule(self):
        path = self.write("base-image.md", "# Base image\n\nIntro.\n\n" + RULE)
        (rule,) = check_rules.parse_rule_file(path)
        self.assertEqual(rule.id, "DW-BASE-01")
        self.assertEqual(rule.title, "Pin the base image by digest")
        self.assertEqual(rule.strength, "MUST")
        self.assertEqual(rule.spells, [1])
        self.assertEqual(rule.last_verified, "2026-11-02")
        self.assertEqual(rule.theme, "base-image")
        self.assertIn("tag@sha256:digest", rule.statement)
        self.assertEqual(rule.how_to_check, "manual")
        self.assertEqual(len(rule.sources), 1)

    def test_missing_field_names_file_and_rule(self):
        path = self.write("base-image.md", RULE.replace("why: |", "wyh: |"))
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(path)
        message = str(caught.exception)
        self.assertIn("base-image.md", message)
        self.assertIn("DW-BASE-01", message)
        self.assertIn("why", message)

    def test_unknown_strength_rejected(self):
        path = self.write("base-image.md", RULE.replace("MUST", "ALWAYS"))
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(path)
        self.assertIn("strength", str(caught.exception))

    def test_http_source_rejected(self):
        path = self.write(
            "base-image.md", RULE.replace("- https://docs", "- http://docs")
        )
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(path)
        self.assertIn("https", str(caught.exception))

    def test_non_url_source_rejected(self):
        path = self.write("base-image.md", RULE.replace("- https://docs", "- docs"))
        with self.assertRaises(check_rules.RuleError):
            check_rules.parse_rule_file(path)

    def test_bad_date_rejected(self):
        path = self.write("base-image.md", RULE.replace("2026-11-02", "2026-13-40"))
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(path)
        self.assertIn("last_verified", str(caught.exception))

    def test_id_must_match_filename_theme(self):
        path = self.write("users-and-permissions.md", RULE)
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(path)
        self.assertIn("DW-USER-", str(caught.exception))

    def test_rule_heading_inside_a_code_fence_is_ignored(self):
        text = "```markdown\n" + RULE + "```\n"
        path = self.write("base-image.md", text)
        self.assertEqual(check_rules.parse_rule_file(path), [])


class ValidateTest(RuleFileTestCase):
    def rules(self, text, name="base-image.md"):
        return check_rules.parse_rule_file(self.write(name, text))

    def test_valid_set_has_no_problems(self):
        self.assertEqual(check_rules.validate(self.rules(RULE), {1}), [])

    def test_spell_without_rule_reported(self):
        problems = check_rules.validate(self.rules(RULE), {1, 2})
        self.assertEqual(len(problems), 1)
        self.assertIn("Spell #2", problems[0])

    def test_spell_out_of_range_rejected(self):
        problems = check_rules.validate(self.rules(RULE.replace("- 1", "- 9")), {1})
        joined = "\n".join(problems)
        self.assertIn("DW-BASE-01", joined)
        self.assertIn("Spell #9", joined)

    def test_duplicate_id_across_files_rejected(self):
        first = self.rules(RULE)
        # Same id in a second file whose theme code is also BASE is impossible by
        # the filename check, so build the duplicate from an already-parsed rule.
        problems = check_rules.validate(first + first, {1})
        self.assertTrue(any("duplicate" in p.lower() for p in problems))


class MainTest(RuleFileTestCase):
    def tree(self, rule_text, spell_headings):
        (self.dir / "docs" / "rules").mkdir(parents=True)
        (self.dir / "docs" / "rules" / "base-image.md").write_text(
            rule_text, encoding="utf-8"
        )
        readme = "\n".join(f"### 🛡️ Spell #{n}: Name" for n in spell_headings)
        (self.dir / "README.md").write_text(readme + "\n", encoding="utf-8")

    def test_check_passes_on_a_complete_tree(self):
        self.tree(RULE, [1])
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 0)

    def test_check_fails_when_a_spell_has_no_rule(self):
        self.tree(RULE, [1, 2])
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)

    def test_check_reports_a_broken_rule_file_without_a_traceback(self):
        self.tree(RULE.replace("MUST", "ALWAYS"), [1])
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)


if __name__ == "__main__":
    unittest.main()
