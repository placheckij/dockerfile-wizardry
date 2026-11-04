import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_rules
import stale_rules

HADOLINT = "https://github.com/hadolint/hadolint"
DISTROLESS_SECTION = "6. Which base image: default, slim, Alpine or distroless"


def rule(rule_id, sources, last_verified="2026-11-02"):
    return check_rules.Rule(
        id=rule_id,
        title="t",
        statement="s",
        strength="MUST",
        why="w",
        how_to_check="manual",
        sources=sources,
        spells=[],
        last_verified=last_verified,
        theme="base-image",
        path=Path("base-image.md"),
    )


class StaleTest(unittest.TestCase):
    def test_older_rule_is_stale(self):
        rules = [rule("DW-BASE-01", [HADOLINT])]
        watched = [stale_rules.Watched("hadolint", [HADOLINT], "2026-12-01")]
        self.assertEqual(
            stale_rules.stale(rules, watched),
            [("DW-BASE-01", "hadolint", "2026-12-01", "2026-11-02")],
        )

    def test_same_day_is_not_stale(self):
        rules = [rule("DW-BASE-01", [HADOLINT], "2026-12-01")]
        watched = [stale_rules.Watched("hadolint", [HADOLINT], "2026-12-01")]
        self.assertEqual(stale_rules.stale(rules, watched), [])

    def test_no_changed_on_is_never_stale(self):
        rules = [rule("DW-BASE-01", [HADOLINT])]
        watched = [stale_rules.Watched("hadolint", [HADOLINT], None)]
        self.assertEqual(stale_rules.stale(rules, watched), [])

    def test_prefix_matches_deeper_url(self):
        url = HADOLINT + "/blob/master/src/Hadolint/Rule/DL3020.hs"
        self.assertTrue(stale_rules.cites([url], [HADOLINT]))
        self.assertFalse(stale_rules.cites(["https://example.com/"], [HADOLINT]))

    def test_prefix_ends_at_a_url_boundary(self):
        frontend = "https://github.com/moby/buildkit/releases/tag/dockerfile"
        cases = [
            (HADOLINT, HADOLINT, True),
            (HADOLINT + "#rules", HADOLINT, True),
            (HADOLINT + "?tab=readme", HADOLINT, True),
            (HADOLINT + "-extra", HADOLINT, False),
            (HADOLINT + "-extra/README.md", HADOLINT, False),
            (frontend + "%2F1.16.0", frontend, True),
            (frontend + "-labs", frontend, False),
            ("https://example.com/a/b", "https://example.com/a/", True),
        ]
        for url, prefix, expected in cases:
            with self.subTest(url=url, prefix=prefix):
                self.assertIs(stale_rules.cites([url], [prefix]), expected)


class MatchingTest(unittest.TestCase):
    def test_unmatched_prefix_is_reported(self):
        rules = [rule("DW-BASE-01", [HADOLINT])]
        distroless = "https://github.com/GoogleContainerTools/distroless"
        tradeoffs = [(DISTROLESS_SECTION, [distroless])]
        watched = [
            stale_rules.Watched(
                "hadolint", ["https://github.com/hadolint/hadolin/"], None
            ),
            stale_rules.Watched("distroless", [distroless], None),
        ]
        self.assertEqual(
            stale_rules.unmatched(watched, rules, tradeoffs),
            [("hadolint", "https://github.com/hadolint/hadolin/")],
        )

    def test_cited_by_lists_rules_then_tradeoffs(self):
        rules = [
            rule("DW-DEPS-01", [HADOLINT + "/blob/master/README.md"]),
            rule("DW-BASE-01", [HADOLINT]),
            rule("DW-USER-01", ["https://example.com/"]),
        ]
        tradeoffs = [
            (DISTROLESS_SECTION, [HADOLINT]),
            ("1. Tag or digest", ["https://example.com/"]),
        ]
        self.assertEqual(
            stale_rules.cited_by([HADOLINT], rules, tradeoffs),
            ["DW-BASE-01", "DW-DEPS-01", f"tradeoffs.md: {DISTROLESS_SECTION}"],
        )


class LoadWatchedTest(unittest.TestCase):
    def test_reads_entries_and_skips_comment(self):
        baseline = {
            "_comment": "text",
            "hadolint": {"rule_sources": [HADOLINT], "changed_on": "2026-12-01"},
            "cis": {"rule_sources": ["https://www.cisecurity.org/benchmark/docker"]},
        }
        self.assertEqual(
            stale_rules.load_watched(baseline),
            [
                stale_rules.Watched("hadolint", [HADOLINT], "2026-12-01"),
                stale_rules.Watched(
                    "cis", ["https://www.cisecurity.org/benchmark/docker"], None
                ),
            ],
        )

    def test_malformed_entry_is_reported(self):
        for entry in (
            {},
            {"rule_sources": []},
            {"rule_sources": ["http://x"]},
            {"rule_sources": HADOLINT},
            {"rule_sources": [HADOLINT], "changed_on": "2026-13-01"},
            {"rule_sources": [HADOLINT], "changed_on": 20261201},
            {"rule_sources": [HADOLINT], "changed_on": "2026-W49-2"},
            {"rule_sources": [HADOLINT], "changed_on": "20261201"},
        ):
            with (
                self.subTest(entry=entry),
                self.assertRaisesRegex(stale_rules.BaselineError, "^hadolint: "),
            ):
                stale_rules.load_watched({"hadolint": entry})


class MainExitTest(unittest.TestCase):
    """main() on a temporary root, with the rulebook replaced by `rules`."""

    def run_main(self, baseline, rules=(), problems=(), tradeoffs=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".github").mkdir()
        if baseline is not None:
            (root / ".github" / "standards-baseline.json").write_text(
                baseline if isinstance(baseline, str) else json.dumps(baseline),
                encoding="utf-8",
            )
        out = io.StringIO()
        with (
            mock.patch.object(
                check_rules, "collect", return_value=(list(rules), list(problems))
            ),
            mock.patch.object(
                check_rules, "tradeoff_sources", return_value=list(tradeoffs)
            ),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(out),
        ):
            code = stale_rules.main([], root=root)
        return code, out.getvalue()

    def test_stale_rule_exits_1(self):
        code, out = self.run_main(
            {"hadolint": {"rule_sources": [HADOLINT], "changed_on": "2026-12-01"}},
            rules=[rule("DW-BASE-01", [HADOLINT])],
        )
        self.assertEqual(code, 1)
        self.assertIn(
            "DW-BASE-01 cites hadolint, which changed on 2026-12-01; "
            "last verified 2026-11-02",
            out,
        )

    def test_unmatched_prefix_exits_1(self):
        code, out = self.run_main(
            {"hadolint": {"rule_sources": ["https://github.com/hadolint/hadolin/"]}},
            rules=[rule("DW-BASE-01", [HADOLINT])],
        )
        self.assertEqual(code, 1)
        self.assertIn("hadolint: prefix https://github.com/hadolint/hadolin/", out)

    def test_rulebook_problems_exit_1(self):
        code, out = self.run_main(
            {"hadolint": {"rule_sources": [HADOLINT]}}, problems=["x.md: broken"]
        )
        self.assertEqual(code, 1)
        self.assertIn("x.md: broken", out)

    def test_malformed_baseline_exits_2(self):
        for baseline in ({"hadolint": {}}, "{not json", None, "[]"):
            with self.subTest(baseline=baseline):
                code, _ = self.run_main(
                    baseline, rules=[rule("DW-BASE-01", [HADOLINT])]
                )
                self.assertEqual(code, 2)

    def test_current_rules_exit_0(self):
        code, out = self.run_main(
            {"hadolint": {"rule_sources": [HADOLINT], "changed_on": "2026-11-02"}},
            rules=[rule("DW-BASE-01", [HADOLINT])],
        )
        self.assertEqual(code, 0, out)


class MainTest(unittest.TestCase):
    def test_main_on_repo_baseline_passes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = stale_rules.main([])
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
