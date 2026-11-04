import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_rules
import skill_references
import test_check_rules
from test_check_rules import RULE, RuleFileTestCase

BLOB = skill_references.REPO_BLOB
REFERENCE = "skills/dockerfile-wizardry/references/rules.md"


class AbsolutizeLinksTest(unittest.TestCase):
    def test_relative_links_become_github_urls(self):
        text = "[t](tradeoffs.md#2-x) and [r](../../README.md#spell-1)"
        self.assertEqual(
            skill_references.absolutize_links(text, "docs/rules/base-image.md"),
            f"[t]({BLOB}docs/rules/tradeoffs.md#2-x) and [r]({BLOB}README.md#spell-1)",
        )

    def test_absolute_and_code_links_untouched(self):
        text = (
            "[a](https://example.org/x.md) [b](mailto:me@example.org) `[c](d.md)`\n"
            "```\n[e](f.md)\n```\n"
        )
        self.assertEqual(
            skill_references.absolutize_links(text, "docs/rules/base-image.md"), text
        )

    def test_bare_anchor_points_at_source_file(self):
        self.assertEqual(
            skill_references.absolutize_links(
                "[x](#dw-base-01-pin)", "docs/rules/base-image.md"
            ),
            f"[x]({BLOB}docs/rules/base-image.md#dw-base-01-pin)",
        )

    def test_link_definitions_are_rewritten(self):
        self.assertEqual(
            skill_references.absolutize_links(
                "[t]: tradeoffs.md#1-x", "docs/rules/base-image.md"
            ),
            f"[t]: {BLOB}docs/rules/tradeoffs.md#1-x",
        )


class RulesReferenceTest(RuleFileTestCase):
    def rules(self):
        second = (
            RULE.replace("DW-BASE-01", "DW-BASE-10")
            .replace("Pin the base image", "Later rule")
            .replace("https://docs.docker.com/", "https://example.org/")
            .replace("manual", "See [the trade-off](tradeoffs.md#1-x).")
        )
        third = second.replace("DW-BASE-10", "DW-BASE-09")
        path = self.write("base-image.md", f"{second}\n{RULE}\n{third}")
        return check_rules.parse_rule_file(path)

    def test_rules_reference_lists_every_rule(self):
        text = skill_references.render_rules_reference(self.rules())
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        self.assertEqual(
            headings,
            [
                "## DW-BASE-01: Pin the base image by digest",
                "## DW-BASE-09: Later rule by digest",
                "## DW-BASE-10: Later rule by digest",
            ],
        )
        for expected in (
            "Strength: MUST",
            "Last verified: 2026-11-02",
            "Reference the base image by `tag@sha256:digest`.",
            "Why: A republished tag",
            "How to check: manual",
            "- https://docs.docker.com/build/building/best-practices/#pin-base-image-versions",
            "- https://example.org/build/building/best-practices/#pin-base-image-versions",
            f"[the trade-off]({BLOB}docs/rules/tradeoffs.md#1-x)",
        ):
            self.assertIn(expected, text)
        self.assertNotIn("spells", text.lower())

    def test_reference_header_says_generated(self):
        text = skill_references.render_rules_reference(self.rules())
        header = text.split("\n\n")[0]
        self.assertIn("generated from", header)
        self.assertIn("must not be edited by hand", header)
        self.assertIn(f"({BLOB}docs/rules/)", header)


class ReferenceFilesTest(RuleFileTestCase):
    def test_examples_copied_verbatim(self):
        (self.dir / "docs" / "rules").mkdir(parents=True)
        (self.dir / "docs" / "rules" / "tradeoffs.md").write_text("# T\n")
        (self.dir / "examples").mkdir()
        for name, text in (("compose.yaml", "a: 1\n\n"), ("pod.yaml", "b: 2")):
            (self.dir / "examples" / name).write_text(text)
        files = {
            path.relative_to(self.dir).as_posix(): text
            for path, text in skill_references.reference_files([], self.dir)
        }
        base = "skills/dockerfile-wizardry/references/"
        self.assertEqual(files[base + "examples/compose.yaml"], "a: 1\n\n")
        self.assertEqual(files[base + "examples/pod.yaml"], "b: 2")
        self.assertEqual(
            sorted(files),
            [
                base + "examples/compose.yaml",
                base + "examples/pod.yaml",
                base + "rules.md",
                base + "tradeoffs.md",
            ],
        )
        self.assertTrue(files[base + "tradeoffs.md"].endswith("\n\n# T\n"))


class CheckIntegrationTest(RuleFileTestCase):
    # a module attribute, so unittest does not collect MainTest's tests again here
    tree = test_check_rules.MainTest.tree

    def test_check_reports_stale_reference(self):
        self.tree(RULE, [1])
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 0)
        (self.dir / REFERENCE).unlink()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)
        self.assertIn(REFERENCE, stderr.getvalue())
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 0)

    def test_check_reports_a_stray_reference_file(self):
        self.tree(RULE, [1])
        self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        stray = "skills/dockerfile-wizardry/references/old-rules.md"
        (self.dir / stray).write_text("stale\n")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)
        self.assertIn(stray, stderr.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_rules.main(["--write"], root=self.dir), 0)
        self.assertFalse((self.dir / stray).exists())
        self.assertEqual(check_rules.main(["--check"], root=self.dir), 0)

    def test_check_reports_a_missing_example(self):
        self.tree(RULE, [1])
        (self.dir / "examples" / "pod.yaml").unlink()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(check_rules.main(["--check"], root=self.dir), 1)
        self.assertIn("pod.yaml", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
