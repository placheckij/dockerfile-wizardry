import contextlib
import datetime
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import release

PLUGIN = '{\n  "name": "dockerfile-wizardry",\n  "version": "0.1.0",\n  "license": "MIT"\n}\n'
CHANGELOG = """# Changelog

Intro.

## [Unreleased]

### Changed

- DW-USER-01 now wants numbers. (#17)

## [0.1.0] - 2026-11-04

### Added

- The skill. (#15)
"""


class VersionTest(unittest.TestCase):
    def test_bump(self):
        self.assertEqual(release.bump("0.1.3", "patch"), "0.1.4")
        self.assertEqual(release.bump("0.1.3", "minor"), "0.2.0")
        self.assertEqual(release.bump("0.1.3", "major"), "1.0.0")

    def test_rejects_non_semver(self):
        for text in ("1.0", "v1.0.0", "01.0.0", "1.0.0-rc.1"):
            with self.subTest(text=text), self.assertRaises(release.ReleaseError):
                release.parse_version(text)

    def test_versions_compare_as_numbers(self):
        self.assertLess(release.parse_version("0.9.0"), release.parse_version("0.10.0"))


class ValidateTest(unittest.TestCase):
    def test_well_formed(self):
        self.assertEqual(release.validate(CHANGELOG), [])
        self.assertEqual(release.latest_version(CHANGELOG), "0.1.0")

    def test_unreleased_must_come_first(self):
        text = CHANGELOG.replace("## [Unreleased]\n", "")
        self.assertEqual(len(release.validate(text)), 1)

    def test_released_section_needs_a_date(self):
        text = CHANGELOG.replace("## [0.1.0] - 2026-11-04", "## [0.1.0]")
        self.assertIn("needs a date", " ".join(release.validate(text)))
        text = CHANGELOG.replace("2026-11-04", "2026-13-04")
        self.assertIn("is not a date", " ".join(release.validate(text)))

    def test_versions_must_descend(self):
        text = CHANGELOG + "\n## [0.2.0] - 2026-11-05\n\n- Later. (#18)\n"
        self.assertIn("must be older", " ".join(release.validate(text)))

    def test_released_section_needs_entries(self):
        text = CHANGELOG.replace("- The skill. (#15)\n", "")
        self.assertIn("has no entries", " ".join(release.validate(text)))

    def test_group_headings_are_not_entries(self):
        self.assertFalse(release.has_entries("\n### Changed\n\n"))
        self.assertTrue(release.has_entries("\n### Changed\n\n- One.\n"))


class PrepareTest(unittest.TestCase):
    def test_moves_entries_and_bumps(self):
        changelog, plugin, new = release.prepare(
            CHANGELOG, PLUGIN, "minor", "2026-11-10"
        )
        self.assertEqual(new, "0.2.0")
        self.assertIn('"version": "0.2.0"', plugin)
        self.assertEqual(plugin.replace("0.2.0", "0.1.0"), PLUGIN)
        self.assertIn(
            "## [Unreleased]\n\n## [0.2.0] - 2026-11-10\n\n### Changed\n\n"
            "- DW-USER-01 now wants numbers. (#17)\n\n## [0.1.0]",
            changelog,
        )
        self.assertEqual(release.validate(changelog), [])
        self.assertEqual(release.latest_version(changelog), "0.2.0")
        self.assertFalse(release.has_entries(release.sections(changelog)[0].body))

    def test_refuses_without_entries(self):
        text = CHANGELOG.replace("- DW-USER-01 now wants numbers. (#17)\n", "")
        with self.assertRaises(release.ReleaseError):
            release.prepare(text, PLUGIN, "patch", "2026-11-10")

    def test_notes_are_the_section_body(self):
        self.assertEqual(
            release.notes(CHANGELOG, "0.1.0"), "### Added\n\n- The skill. (#15)\n"
        )
        with self.assertRaises(release.ReleaseError):
            release.notes(CHANGELOG, "9.9.9")


class PendingTest(unittest.TestCase):
    def test_overdue(self):
        today = datetime.date(2026, 11, 30)
        self.assertIsNone(release.overdue([], today, 14))
        self.assertIsNone(release.overdue(["2026-11-16"], today, 14))
        self.assertEqual(
            release.overdue(["2026-11-20", "2026-11-15"], today, 14),
            datetime.date(2026, 11, 15),
        )

    def test_shipped_paths(self):
        self.assertTrue(release.touches_plugin(["skills/dockerfile-wizardry/SKILL.md"]))
        self.assertTrue(release.touches_plugin([".claude-plugin/plugin.json"]))
        self.assertFalse(release.touches_plugin(["docs/rules/secrets.md", "README.md"]))


class CheckTest(unittest.TestCase):
    """`check --base` against a throwaway git repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        (self.root / ".claude-plugin").mkdir()
        (self.root / "skills").mkdir()
        self.write(release.PLUGIN, PLUGIN)
        self.write(release.CHANGELOG, CHANGELOG)
        self.write("skills/SKILL.md", "one\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@example.com",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def write(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")

    def check(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = release.main(list(argv), root=self.root)
        return code, out.getvalue() + err.getvalue()

    def test_plugin_change_needs_a_changelog_entry(self):
        self.write("skills/SKILL.md", "two\n")
        self.commit()
        code, output = self.check("check", "--base", self.base)
        self.assertEqual(code, 1)
        self.assertIn("add an entry there", output)
        self.write(
            release.CHANGELOG, CHANGELOG.replace("(#17)\n", "(#17)\n- More. (#18)\n")
        )
        self.commit()
        self.assertEqual(self.check("check", "--base", self.base)[0], 0)

    def test_entry_outside_unreleased_does_not_count(self):
        self.write("skills/SKILL.md", "two\n")
        self.write(release.CHANGELOG, CHANGELOG.replace("Intro.", "Intro, reworded."))
        self.commit()
        self.assertEqual(self.check("check", "--base", self.base)[0], 1)
        self.write(
            release.CHANGELOG,
            CHANGELOG.replace(
                "- The skill. (#15)\n", "- The skill. (#15)\n- More. (#18)\n"
            ),
        )
        self.commit()
        self.assertEqual(self.check("check", "--base", self.base)[0], 1)

    def test_first_changelog_needs_no_unreleased_entry(self):
        self.git("rm", "-q", release.CHANGELOG)
        self.commit()
        base = self.git("rev-parse", "HEAD").strip()
        self.write(release.CHANGELOG, CHANGELOG)
        self.write("skills/SKILL.md", "two\n")
        self.commit()
        self.assertEqual(self.check("check", "--base", base)[0], 0)

    def test_other_changes_need_no_entry(self):
        self.write("README.md", "readme\n")
        self.commit()
        self.assertEqual(self.check("check", "--base", self.base)[0], 0)

    def test_prepared_release_passes_and_is_bumped(self):
        self.assertEqual(self.check("prepare", "minor")[0], 0)
        self.commit()
        self.assertEqual(self.check("check", "--base", self.base)[0], 0)
        self.assertEqual(self.check("bumped", self.base), (0, "0.2.0\n"))
        self.assertEqual(self.check("bumped", "HEAD"), (0, ""))

    def test_version_must_match_the_changelog(self):
        self.write(release.PLUGIN, PLUGIN.replace("0.1.0", "0.2.0"))
        code, output = self.check("check")
        self.assertEqual(code, 1)
        self.assertIn("says 0.2.0", output)

    def test_version_must_not_go_down(self):
        self.write(release.PLUGIN, PLUGIN.replace("0.1.0", "0.0.1"))
        self.write(
            release.CHANGELOG,
            CHANGELOG.replace("## [0.1.0] - 2026-11-04", "## [0.0.1] - 2026-11-04"),
        )
        self.commit()
        code, output = self.check("check", "--base", self.base)
        self.assertEqual(code, 1)
        self.assertIn("lowers the version", output)

    def test_pending_counts_commits_since_the_version_changed(self):
        code, output = self.check("pending")
        self.assertEqual(code, 0)
        self.assertIn("0 unreleased commit(s)", output)
        self.write("skills/SKILL.md", "two\n")
        self.commit()
        code, output = self.check("pending")
        self.assertEqual(code, 0)
        self.assertIn("1 unreleased commit(s)", output)

    def test_pending_counts_from_the_release_tag(self):
        self.write("skills/SKILL.md", "two\n")
        self.commit()
        self.git("tag", "v0.1.0")
        self.write("skills/SKILL.md", "three\n")
        self.commit()
        code, output = self.check("pending")
        self.assertEqual(code, 0)
        self.assertIn("1 unreleased commit(s)", output)

    def test_bad_usage(self):
        for argv in (
            [],
            ["check", "--days", "1"],
            ["prepare", "huge"],
            ["pending", "--days", "x"],
            # a digit int() does not take
            ["pending", "--days", "\u00b2"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(self.check(*argv)[0], 2)


if __name__ == "__main__":
    unittest.main()
