import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_fixtures
from test_check_rules import RULE

BASE = [("DW-BASE-01", ["DL3007"])]
IDS = {"DW-BASE-01"}


class ParseExpectedTest(unittest.TestCase):
    def test_parse_expected_reads_ids_and_codes(self):
        text = "# c\nDW-BASE-01  DL3007\n\nDW-USER-01\n"
        self.assertEqual(
            check_fixtures.parse_expected(text),
            [("DW-BASE-01", ["DL3007"]), ("DW-USER-01", [])],
        )

    def test_parse_expected_rejects_non_id(self):
        with self.assertRaises(ValueError):
            check_fixtures.parse_expected("DL3007 DW-BASE-01")

    def test_parse_expected_strips_trailing_comments(self):
        self.assertEqual(
            check_fixtures.parse_expected("DW-BASE-01 DL3007  # why\n"), BASE
        )


class CompareTest(unittest.TestCase):
    def test_unexpected_code_fails(self):
        problems = check_fixtures.compare(BASE, {"DL3007", "DL3020"}, IDS)
        self.assertEqual(len(problems), 1)
        self.assertIn("DL3020", problems[0])

    def test_missing_code_fails(self):
        problems = check_fixtures.compare(BASE, set(), IDS)
        self.assertEqual(len(problems), 1)
        self.assertIn("DL3007", problems[0])

    def test_unknown_rule_id_fails(self):
        problems = check_fixtures.compare([("DW-BASE-99", [])], set(), IDS)
        self.assertEqual(len(problems), 1)
        self.assertIn("DW-BASE-99", problems[0])

    def test_clean_fixture_passes(self):
        self.assertEqual(check_fixtures.compare([], set(), IDS), [])


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        rules = self.dir / "docs" / "rules"
        rules.mkdir(parents=True)
        (rules / "base-image.md").write_text(RULE, encoding="utf-8")
        (self.dir / "README.md").write_text("### 🛡️ Spell #1: Name\n", encoding="utf-8")
        self.fixture = self.dir / "fixtures" / "dockerfiles" / "bad-latest"
        self.fixture.mkdir(parents=True)
        (self.fixture / "Dockerfile").write_text("FROM alpine\n", encoding="utf-8")

    def run_main(self, hadolint=(), buildcheck=()):
        stderr = io.StringIO()
        with (
            mock.patch.object(check_fixtures, "ensure_docker"),
            mock.patch.object(
                check_fixtures, "hadolint_codes", return_value=set(hadolint)
            ),
            mock.patch.object(
                check_fixtures, "buildcheck_codes", return_value=set(buildcheck)
            ),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(stderr),
        ):
            code = check_fixtures.main([], root=self.dir)
        return code, stderr.getvalue()

    def test_main_reports_fixture_name(self):
        (self.fixture / "expected-findings.txt").write_text(
            "DW-BASE-01  DL3007\n", encoding="utf-8"
        )
        code, message = self.run_main(hadolint={"DL3007", "DL3020"})
        self.assertEqual(code, 1)
        self.assertIn("bad-latest", message)
        self.assertIn("DL3020", message)

    def test_main_passes_when_labels_match(self):
        (self.fixture / "expected-findings.txt").write_text(
            "DW-BASE-01  DL3007 SecretsUsedInArgOrEnv\n", encoding="utf-8"
        )
        code, _ = self.run_main(
            hadolint={"DL3007"}, buildcheck={"SecretsUsedInArgOrEnv"}
        )
        self.assertEqual(code, 0)

    def test_main_reports_missing_expected_file(self):
        code, message = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("bad-latest", message)
        self.assertIn("expected-findings.txt", message)

    def test_main_reports_bad_expected_file(self):
        (self.fixture / "expected-findings.txt").write_text(
            "DL3007 DW-BASE-01\n", encoding="utf-8"
        )
        code, message = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("bad-latest", message)

    def test_main_exits_2_when_docker_is_unavailable(self):
        (self.fixture / "expected-findings.txt").write_text("", encoding="utf-8")
        stderr = io.StringIO()
        with (
            mock.patch.object(
                check_fixtures,
                "ensure_docker",
                side_effect=check_fixtures.DockerUnavailable("no docker"),
            ),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(check_fixtures.main([], root=self.dir), 2)
        self.assertIn("no docker", stderr.getvalue())

    def test_main_reports_invalid_linter_output_with_fixture_name(self):
        (self.fixture / "expected-findings.txt").write_text("", encoding="utf-8")
        stderr = io.StringIO()
        with (
            mock.patch.object(check_fixtures, "ensure_docker"),
            mock.patch.object(
                check_fixtures,
                "hadolint_codes",
                side_effect=check_fixtures.LinterError("not JSON"),
            ),
            mock.patch.object(check_fixtures, "buildcheck_codes", return_value=set()),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(check_fixtures.main([], root=self.dir), 1)
        self.assertIn("bad-latest", stderr.getvalue())
        self.assertIn("not JSON", stderr.getvalue())


class ParseJsonTest(unittest.TestCase):
    def test_hadolint_json(self):
        out = '[{"code":"DL3007","line":1},{"code":"DL3007","line":2}]'
        self.assertEqual(check_fixtures.parse_hadolint(out), {"DL3007"})

    def test_buildcheck_json_without_warnings_key(self):
        self.assertEqual(check_fixtures.parse_buildcheck('{"sources":[]}'), set())

    def test_buildcheck_json(self):
        out = '{"warnings":[{"ruleName":"SecretsUsedInArgOrEnv"}]}'
        self.assertEqual(
            check_fixtures.parse_buildcheck(out), {"SecretsUsedInArgOrEnv"}
        )

    def test_buildcheck_build_error_is_a_linter_error(self):
        # what buildx 0.36 prints, with exit 1, for a Dockerfile it cannot parse
        out = (
            '{"warnings": null, "sources": [], "buildError": {"message": '
            '"dockerfile parse error on line 1: FROM requires either one or three '
            'arguments"}}'
        )
        with self.assertRaisesRegex(check_fixtures.LinterError, "FROM requires"):
            check_fixtures.parse_buildcheck(out)

    def test_buildcheck_null_warnings_is_clean(self):
        self.assertEqual(check_fixtures.parse_buildcheck('{"warnings": null}'), set())

    def test_empty_output_includes_stderr(self):
        with self.assertRaisesRegex(check_fixtures.LinterError, "pull access denied"):
            check_fixtures.parse_hadolint("", "pull access denied")
        with self.assertRaisesRegex(check_fixtures.LinterError, "daemon gone"):
            check_fixtures.parse_buildcheck("", "daemon gone")

    def test_unparseable_output_includes_stderr(self):
        with self.assertRaisesRegex(check_fixtures.LinterError, "out of memory"):
            check_fixtures.parse_hadolint("oops", "out of memory")

    def test_invalid_json_is_a_linter_error(self):
        with self.assertRaises(check_fixtures.LinterError):
            check_fixtures.parse_hadolint("oops")
        with self.assertRaises(check_fixtures.LinterError):
            check_fixtures.parse_buildcheck("oops")


if __name__ == "__main__":
    unittest.main()
