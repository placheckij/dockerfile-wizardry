import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_standards
import standards_sources

SHA = "66226906bbe7f4086ad8450435c2a72b5b8fbb8d"
HADOLINT = "https://github.com/hadolint/hadolint"


def baseline(**changes):
    data = {
        "_comment": "test",
        "cis_docker_benchmark": {
            "verified_version": "1.9.0",
            "rule_sources": ["https://www.cisecurity.org/benchmark/docker"],
        },
        "owasp_docker_cheat_sheet": {
            "reviewed_commit": SHA,
            "rule_sources": [
                "https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html"
            ],
        },
        "dockerfile_frontend": {
            "reviewed_version": "1.28.0",
            "rule_sources": [HADOLINT],
        },
        "build_checks": {
            "reviewed_checks": ["undefined-var"],
            "rule_sources": [HADOLINT],
        },
        "hadolint": {
            "reviewed_release": "v2.15.1",
            "reviewed_rules": ["DL3000"],
            "rule_sources": [HADOLINT],
        },
        "distroless": {"reviewed_debian_versions": ["13"], "rule_sources": [HADOLINT]},
    }
    data.update(changes)
    return data


def current(key):
    return lambda entry: standards_sources.Watch(key, f"{key} : current")


class StandardsTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "standards-baseline.json"
        self.write(baseline())
        for patcher in (
            mock.patch.object(check_standards, "BASELINE", self.path),
            mock.patch.object(
                check_standards, "latest_cis_version", return_value="1.9.0"
            ),
            mock.patch.object(
                check_standards,
                "latest_owasp_commit",
                return_value=(SHA, "2026-10-30", "msg"),
            ),
            mock.patch.object(
                check_standards, "broken_owasp_anchors", return_value=([], ["rule-2"])
            ),
            mock.patch.dict(
                standards_sources.WATCHERS,
                {key: current(key) for key in standards_sources.WATCHERS},
            ),
            mock.patch.dict("os.environ", {"GITHUB_STEP_SUMMARY": ""}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["check_standards.py", *args]),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = check_standards.main()
        return code, out.getvalue(), err.getvalue()


class LoadBaselineTest(StandardsTestCase):
    def test_load_baseline_rejects_bad_entry(self):
        data = baseline()
        del data["hadolint"]["rule_sources"]
        self.write(data)
        with self.assertRaisesRegex(check_standards.CheckError, "hadolint"):
            check_standards.load_baseline()

    def test_load_baseline_requires_every_watched_key(self):
        data = baseline()
        del data["distroless"]
        self.write(data)
        with self.assertRaisesRegex(check_standards.CheckError, "distroless"):
            check_standards.load_baseline()

    def test_check_error_is_the_shared_class(self):
        self.assertIs(check_standards.CheckError, standards_sources.CheckError)


class MainTest(StandardsTestCase):
    def outdated_hadolint(self):
        watch = standards_sources.Watch(
            "hadolint", "hadolint : changed", "Hadolint moved.", ["+ DL3062"]
        )
        return mock.patch.dict(
            standards_sources.WATCHERS, {"hadolint": lambda e: watch}
        )

    def test_all_current_returns_zero(self):
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertTrue(out.rstrip().endswith("Up to date."))
        for key in standards_sources.WATCHERS:
            self.assertIn(f"{key} : current", out)

    def test_outdated_source_names_rules_to_recheck(self):
        with self.outdated_hadolint():
            code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("Hadolint moved.", err)
        self.assertIn("Re-check: ", err)
        # DW-DEPS-01 cites the Hadolint repository in the real rulebook
        self.assertIn("DW-DEPS-01", err)
        self.assertIn("| + DL3062", err)

    def test_report_only_returns_zero_when_outdated(self):
        with self.outdated_hadolint():
            code, _, _ = self.run_main("--report-only")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
