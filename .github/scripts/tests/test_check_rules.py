import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_rules

RULE = """\
## DW-BASE-01: Pin the base image by digest

strength: MUST

spells:
- 1

last_verified: 2026-11-02

statement:
  Reference the base image by `tag@sha256:digest`.

why:
  A republished tag cannot change which bytes you build on.

how_to_check:
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
        path = self.write(
            "base-image.md",
            RULE.replace(
                "why:\n  A republished tag cannot change which bytes you build on.\n\n",
                "",
            ),
        )
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

    def test_blank_lines_between_fields_and_multiline_text_parse(self):
        text = RULE.replace(
            "  A republished tag cannot change which bytes you build on.",
            "  A republished tag cannot change\n\n  which bytes you build on.",
        )
        (rule,) = check_rules.parse_rule_file(self.write("base-image.md", text))
        self.assertIn("which bytes", rule.why)

    def test_malformed_rule_heading_rejected(self):
        for heading in (
            "## DW-BASE-02 - Title",
            "## DW-Base-02: Title",
            "## DW-BASE-2",
        ):
            with self.subTest(heading=heading):
                path = self.write("base-image.md", RULE + "\n" + heading + "\n")
                with self.assertRaises(check_rules.RuleError) as caught:
                    check_rules.parse_rule_file(path)
                self.assertIn("heading", str(caught.exception))

    def test_inline_spells_rejected(self):
        path = self.write("base-image.md", RULE.replace("spells:\n- 1", "spells: 12"))
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(path)
        self.assertIn("spells", str(caught.exception))

    def test_list_given_for_a_scalar_field_rejected_without_a_traceback(self):
        path = self.write(
            "base-image.md",
            RULE.replace("last_verified: 2026-11-02", "last_verified:\n- 2026-11-02"),
        )
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(path)
        self.assertIn("last_verified", str(caught.exception))

    def test_list_item_after_a_blank_line_rejected(self):
        text = RULE.replace(
            "best-practices/#pin-base-image-versions",
            "best-practices/#pin-base-image-versions\n\n- http://evil.example/x",
        )
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(self.write("base-image.md", text))
        self.assertIn("unexpected", str(caught.exception))

    def test_unindented_continuation_line_rejected(self):
        text = RULE.replace("  manual", "  manual\nand more text")
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(self.write("base-image.md", text))
        self.assertIn("unexpected", str(caught.exception))

    def test_unknown_field_rejected(self):
        text = RULE.replace("strength: MUST", "strength: MUST\n\nstrenght: MUST")
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(self.write("base-image.md", text))
        self.assertIn("strenght", str(caught.exception))

    def test_real_rule_files_separate_fields_with_blank_lines(self):
        # GitHub folds a field into the previous list or paragraph unless a blank line
        # separates them, which garbles the rendered page.
        rules_dir = check_rules.ROOT / "docs" / "rules"
        for path in sorted(rules_dir.glob("*.md")):
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines[1:], start=2):
                if check_rules.FIELD_RE.match(line) or check_rules.HEADING_RE.match(
                    line
                ):
                    with self.subTest(file=path.name, line=number):
                        self.assertEqual(lines[number - 2].strip(), "")

    def test_a_longer_fence_is_not_closed_by_a_shorter_one(self):
        text = "````markdown\n```\n## DW-BASE-02 - Title\n```\n````\n\n" + RULE
        (rule,) = check_rules.parse_rule_file(self.write("base-image.md", text))
        self.assertEqual(rule.id, "DW-BASE-01")

    def test_rule_heading_at_the_wrong_level_rejected(self):
        for heading in ("# DW-BASE-02: Title", "### DW-BASE-02: Title"):
            with self.subTest(heading=heading):
                path = self.write("base-image.md", RULE + "\n" + heading + "\n")
                with self.assertRaises(check_rules.RuleError) as caught:
                    check_rules.parse_rule_file(path)
                self.assertIn("heading", str(caught.exception))

    def test_source_without_a_hostname_rejected(self):
        for source in ("https://#section", "https://?q=x", "https:///path"):
            with self.subTest(source=source):
                text = RULE.replace(
                    "https://docs.docker.com/build/building/best-practices/#pin-base-image-versions",
                    source,
                )
                with self.assertRaises(check_rules.RuleError) as caught:
                    check_rules.parse_rule_file(self.write("base-image.md", text))
                self.assertIn("https", str(caught.exception))

    def test_unparseable_source_url_rejected_without_a_traceback(self):
        text = RULE.replace(
            "https://docs.docker.com/build/building/best-practices/#pin-base-image-versions",
            "https://[example.com/rule",
        )
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(self.write("base-image.md", text))
        self.assertIn("DW-BASE-01", str(caught.exception))

    def test_a_rule_inside_an_indented_fence_is_ignored(self):
        # up to three spaces may precede a fence; the content may be less indented
        text = "  ```markdown\n" + RULE + "  ```\n"
        self.assertEqual(
            check_rules.parse_rule_file(self.write("base-image.md", text)), []
        )

    def test_four_space_indented_backticks_are_not_a_fence(self):
        text = "    ```\n\n" + RULE
        (rule,) = check_rules.parse_rule_file(self.write("base-image.md", text))
        self.assertEqual(rule.id, "DW-BASE-01")

    def test_date_must_use_the_yyyy_mm_dd_form(self):
        for date in ("20261102", "2026-W44-1"):
            with self.subTest(date=date):
                text = RULE.replace("2026-11-02", date)
                with self.assertRaises(check_rules.RuleError) as caught:
                    check_rules.parse_rule_file(self.write("base-image.md", text))
                self.assertIn("last_verified", str(caught.exception))

    def test_a_rule_without_spells_is_valid(self):
        text = RULE.replace("spells:\n- 1\n\n", "")
        (rule,) = check_rules.parse_rule_file(self.write("base-image.md", text))
        self.assertEqual(rule.spells, [])

    def test_spell_headings_inside_code_fences_are_not_spells(self):
        readme = self.write(
            "README.md",
            "### Spell #1: Real\n\n```markdown\n### Spell #9: Example\n```\n",
        )
        self.assertEqual(check_rules.spell_numbers(readme), {1})

    def test_secrets_and_supply_chain_themes_are_known(self):
        for theme, code in (("secrets", "SECRET"), ("supply-chain", "SUPPLY")):
            with self.subTest(theme=theme):
                text = RULE.replace("DW-BASE-01", f"DW-{code}-01")
                (rule,) = check_rules.parse_rule_file(self.write(f"{theme}.md", text))
                self.assertEqual(rule.id, f"DW-{code}-01")
                self.assertEqual(rule.theme, theme)

    def test_a_secrets_id_in_the_supply_chain_file_rejected(self):
        text = RULE.replace("DW-BASE-01", "DW-SECRET-01")
        with self.assertRaises(check_rules.RuleError) as caught:
            check_rules.parse_rule_file(self.write("supply-chain.md", text))
        self.assertIn("DW-SUPPLY-", str(caught.exception))


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

    def test_duplicate_id_rejected(self):
        # theme codes are unique per file, so a duplicate id can only repeat inside one file
        rules_dir = self.dir / "docs" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "base-image.md").write_text(RULE + "\n" + RULE, encoding="utf-8")
        (self.dir / "README.md").write_text("### Spell #1: Name\n", encoding="utf-8")
        _, problems = check_rules.collect(self.dir)
        self.assertTrue(any("duplicate" in p.lower() for p in problems))


INDEX_README = """\
# Rules

<!-- rules-index:start -->
<!-- rules-index:end -->
"""

USER_RULE = RULE.replace("DW-BASE-01", "DW-USER-01").replace("Pin the base", "Run as")


class MainTest(RuleFileTestCase):
    def tree(self, rule_text, spell_headings, extra_files=None):
        rules = self.dir / "docs" / "rules"
        rules.mkdir(parents=True)
        (rules / "base-image.md").write_text(rule_text, encoding="utf-8")
        for name, text in (extra_files or {}).items():
            (rules / name).write_text(text, encoding="utf-8")
        (rules / "README.md").write_text(INDEX_README, encoding="utf-8")
        readme = "\n".join(f"### 🛡️ Spell #{n}: Name" for n in spell_headings)
        (self.dir / "README.md").write_text(readme + "\n", encoding="utf-8")

    def index_text(self):
        return (self.dir / "docs" / "rules" / "README.md").read_text(encoding="utf-8")

    def test_check_passes_on_a_complete_tree(self):
        self.tree(RULE, [1])
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 0)

    def test_check_fails_when_a_spell_has_no_rule(self):
        self.tree(RULE, [1, 2])
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)

    def test_check_reports_a_broken_rule_file_without_a_traceback(self):
        self.tree(RULE.replace("MUST", "ALWAYS"), [1])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)
        message = stderr.getvalue()
        self.assertIn("base-image.md", message)
        self.assertIn("DW-BASE-01", message)
        self.assertNotIn("Traceback", message)

    def test_index_lists_every_rule_sorted(self):
        self.tree(
            RULE, [1, 2], {"users-and-permissions.md": USER_RULE.replace("- 1", "- 2")}
        )
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        text = self.index_text()
        self.assertIn("| DW-BASE-01 | Pin the base image by digest | MUST | #1 |", text)
        self.assertIn("[users-and-permissions](users-and-permissions.md)", text)
        self.assertLess(text.index("DW-BASE-01"), text.index("DW-USER-01"))

    def test_write_is_idempotent(self):
        self.tree(RULE, [1])
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        first = self.index_text()
        self.assertNotEqual(first, INDEX_README)
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        self.assertEqual(self.index_text(), first)

    def test_check_fails_when_index_stale(self):
        self.tree(RULE, [1])
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        path = self.dir / "docs" / "rules" / "README.md"
        before = path.read_text(encoding="utf-8")
        path.write_text(before.replace("MUST", "SHOULD"), encoding="utf-8")
        self.assertNotEqual(path.read_text(encoding="utf-8"), before)
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)

    def test_check_fails_when_the_index_markers_are_missing(self):
        self.tree(RULE, [1])
        (self.dir / "docs" / "rules" / "README.md").write_text("# Rules\n")
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)

    def test_a_tradeoffs_page_is_not_a_theme_file(self):
        self.tree(RULE, [1], {"tradeoffs.md": "# Trade-offs\n\nProse only.\n"})
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 0)

    def test_index_shows_a_dash_for_a_rule_without_spells(self):
        self.tree(RULE.replace("spells:\n- 1\n\n", ""), [])
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        self.assertIn("| MUST | - |", self.index_text())

    def test_usage_errors_exit_2(self):
        self.tree(RULE, [1])
        for argv in ([], ["--bogus"], ["--check", "--write"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check_rules.main(argv, root=self.dir), 2)


if __name__ == "__main__":
    unittest.main()
