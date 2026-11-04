import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import standards_sources as s

HADOLINT_README = """\
| Rule | Severity | Description |
| [DL3000](https://github.com/hadolint/hadolint/wiki/DL3000) | Error | Use absolute WORKDIR. |
| [DL3007](https://github.com/hadolint/hadolint/wiki/DL3007) | Warning | Using latest. |
See [DL3007] again, and [SC2086](https://www.shellcheck.net/wiki/SC2086).
"""
SOURCES = ["https://example.com/"]


def gh(*outputs):
    """Patch gh_api to return `outputs` in order."""
    return mock.patch.object(s, "gh_api", side_effect=list(outputs))


class ParserTest(unittest.TestCase):
    def test_latest_stable_ignores_prereleases_and_junk(self):
        refs = [
            "refs/tags/dockerfile/1.9.0",
            "refs/tags/dockerfile/1.10.0",
            "refs/tags/dockerfile/1.11.0-rc1",
            "refs/tags/dockerfile/1.11.0-labs",
            "refs/tags/dockerfile/1.12.0::set-output",
            "refs/tags/v0.30.0",
        ]
        self.assertEqual(s.latest_stable(refs), "1.10.0")

    def test_build_check_names(self):
        names = [
            "_index.md",
            "json-args-recommended.md",
            "undefined-var.md",
            "README",
            "../x.md",
        ]
        self.assertEqual(
            s.build_check_names(names), ["json-args-recommended", "undefined-var"]
        )

    def test_hadolint_rules(self):
        self.assertEqual(s.hadolint_rules(HADOLINT_README), ["DL3000", "DL3007"])

    def test_distroless_debian_versions(self):
        text = (
            "| gcr.io/distroless/static-debian12 | latest |\n"
            "| gcr.io/distroless/python3-debian13 | latest |\n"
            "| gcr.io/distroless/cc-debian13 | latest |\n"
        )
        self.assertEqual(s.distroless_debian_versions(text), ["12", "13"])

    def test_distroless_versions_come_from_the_image_table_only(self):
        text = (
            "Specifying `gcr.io/distroless/static-debian14` will select newer images.\n"
            "| Image | Tags |\n"
            "| gcr.io/distroless/static-debian13     | latest, nonroot |\n"
            "|gcr.io/distroless/cc-debian12|latest|\n"
            "FROM gcr.io/distroless/python3-debian11:debug\n"
        )
        self.assertEqual(s.distroless_debian_versions(text), ["12", "13"])

    def test_non_ascii_digits_are_not_matched(self):
        for call in (
            lambda: s.latest_stable(["refs/tags/dockerfile/1.\u0662.0"]),
            lambda: s.hadolint_rules("[DL\uff13\uff10\uff10\uff10]"),
            lambda: s.distroless_debian_versions(
                "| gcr.io/distroless/static-debian\u0661\u0663 | latest |"
            ),
        ):
            with self.subTest(call=call), self.assertRaises(s.CheckError):
                call()

    def test_empty_signal_is_check_error(self):
        for call in (
            lambda: s.latest_stable([]),
            lambda: s.latest_stable(["refs/tags/dockerfile/1.11.0-rc1"]),
            lambda: s.build_check_names(["_index.md"]),
            lambda: s.hadolint_rules("no table"),
            lambda: s.distroless_debian_versions(""),
        ):
            with self.subTest(call=call), self.assertRaises(s.CheckError):
                call()

    def test_set_diff(self):
        self.assertEqual(
            s.set_diff(["DL3000", "DL3007"], ["DL3007", "DL3062"]),
            ["+ DL3062", "- DL3000"],
        )


class WatchTest(unittest.TestCase):
    def hadolint_entry(self, release="v2.15.1"):
        return {
            "reviewed_release": release,
            "reviewed_rules": ["DL3000", "DL3007"],
            "rule_sources": SOURCES,
        }

    def test_watch_hadolint_up_to_date(self):
        with gh("v2.15.1\n", HADOLINT_README):
            watch = s.watch_hadolint(self.hadolint_entry())
        self.assertEqual(watch.key, "hadolint")
        self.assertIsNone(watch.problem)
        self.assertEqual(watch.diff, [])
        self.assertIn("v2.15.1", watch.status)

    def test_watch_hadolint_new_rule(self):
        readme = HADOLINT_README + "| [DL3062](x) | Warning | New. |\n"
        with gh("v2.15.1\n", readme):
            watch = s.watch_hadolint(self.hadolint_entry())
        self.assertIsNotNone(watch.problem)
        self.assertIn("reviewed_rules", watch.problem)
        self.assertEqual(watch.diff, ["+ DL3062"])

    def test_watch_hadolint_new_release(self):
        with gh("v2.16.0\n", HADOLINT_README):
            watch = s.watch_hadolint(self.hadolint_entry())
        self.assertIn("v2.16.0", watch.problem)
        self.assertIn("reviewed_release", watch.problem)

    def test_watch_hadolint_release_and_rules_form_one_bullet(self):
        readme = HADOLINT_README + "| [DL3062](x) | Warning | New. |\n"
        with gh("v2.16.0\n", readme):
            watch = s.watch_hadolint(self.hadolint_entry())
        lines = watch.problem.splitlines()
        self.assertTrue(lines[0].startswith("Hadolint: newest release is v2.16.0"))
        self.assertTrue(all(line.startswith("  ") for line in lines[1:]), lines)
        self.assertTrue(
            lines[3].startswith("  Hadolint rules: the list changed"), lines
        )

    def test_problem_says_to_record_the_change(self):
        with gh("v2.16.0\n", HADOLINT_README):
            watch = s.watch_hadolint(self.hadolint_entry())
        self.assertIn("hadolint.reviewed_on and hadolint.changed_on", watch.problem)
        self.assertIn("last_verified", watch.problem)

    def test_watch_hadolint_bad_tag_is_check_error(self):
        with (
            gh("v2.16.0::set-output\n", HADOLINT_README),
            self.assertRaises(s.CheckError),
        ):
            s.watch_hadolint(self.hadolint_entry())

    def test_watch_hadolint_non_ascii_tag_is_check_error(self):
        with (
            gh("v2.\u0661\u0666.0\n", HADOLINT_README),
            self.assertRaises(s.CheckError),
        ):
            s.watch_hadolint(self.hadolint_entry())

    def test_watch_frontend_newer_upstream_is_a_problem(self):
        entry = {"reviewed_version": "1.28.0", "rule_sources": SOURCES}
        with gh("refs/tags/dockerfile/1.28.0\nrefs/tags/dockerfile/1.29.0\n"):
            watch = s.watch_dockerfile_frontend(entry)
        self.assertIn("1.29.0", watch.problem)

    def test_watch_frontend_older_upstream_is_not_a_problem(self):
        entry = {"reviewed_version": "1.28.0", "rule_sources": SOURCES}
        with gh("refs/tags/dockerfile/1.27.1\n"):
            watch = s.watch_dockerfile_frontend(entry)
        self.assertIsNone(watch.problem)

    def test_watch_build_checks_removed_check(self):
        entry = {
            "reviewed_checks": ["json-args-recommended", "undefined-var"],
            "rule_sources": SOURCES,
        }
        with gh("_index.md\njson-args-recommended.md\n"):
            watch = s.watch_build_checks(entry)
        self.assertEqual(watch.diff, ["- undefined-var"])
        self.assertIsNotNone(watch.problem)

    def test_watch_distroless_new_debian(self):
        entry = {"reviewed_debian_versions": ["13"], "rule_sources": SOURCES}
        table = (
            "| gcr.io/distroless/static-debian13 | latest |\n"
            "| gcr.io/distroless/static-debian14 | latest |\n"
        )
        with gh(table):
            watch = s.watch_distroless(entry)
        self.assertEqual(watch.diff, ["+ 14"])

    def test_watch_rejects_malformed_entry(self):
        cases = [
            (s.watch_build_checks, {"reviewed_checks": "json-args-recommended"}),
            (s.watch_build_checks, {"reviewed_checks": []}),
            (s.watch_dockerfile_frontend, {"reviewed_version": "1.28"}),
            (s.watch_hadolint, {"reviewed_release": "2.15.1", "reviewed_rules": []}),
            (s.watch_distroless, {}),
        ]
        for watcher, entry in cases:
            with (
                self.subTest(entry=entry),
                gh() as fetch,
                self.assertRaisesRegex(s.CheckError, "^baseline [a-z_]+: "),
            ):
                watcher(entry)
            fetch.assert_not_called()

    def test_watchers_are_keyed_by_baseline_key(self):
        self.assertEqual(
            sorted(s.WATCHERS),
            ["build_checks", "distroless", "dockerfile_frontend", "hadolint"],
        )


class GhApiTest(unittest.TestCase):
    def test_failure_is_check_error(self):
        result = mock.Mock(returncode=1, stdout="", stderr="HTTP 404")
        with (
            mock.patch.object(s.subprocess, "run", return_value=result),
            self.assertRaisesRegex(s.CheckError, "HTTP 404"),
        ):
            s.gh_api("repos/x/y")

    def test_empty_output_is_check_error(self):
        result = mock.Mock(returncode=0, stdout="  \n", stderr="")
        with (
            mock.patch.object(s.subprocess, "run", return_value=result),
            self.assertRaises(s.CheckError),
        ):
            s.gh_api("repos/x/y")

    def test_arguments(self):
        result = mock.Mock(returncode=0, stdout="ok", stderr="")
        with mock.patch.object(s.subprocess, "run", return_value=result) as run:
            s.gh_api("repos/x/readme", raw=True, paginate=True, jq=".x")
        args = run.call_args.args[0]
        self.assertEqual(args[:2], ["gh", "api"])
        self.assertIn("--paginate", args)
        self.assertIn("Accept: application/vnd.github.raw", args)
        self.assertEqual(args[args.index("--jq") + 1], ".x")
        self.assertIn("repos/x/readme", args)


if __name__ == "__main__":
    unittest.main()
