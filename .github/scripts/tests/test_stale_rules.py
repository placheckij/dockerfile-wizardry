import contextlib
import io
import sys
import unittest
from pathlib import Path

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
        ):
            with (
                self.subTest(entry=entry),
                self.assertRaisesRegex(stale_rules.BaselineError, "^hadolint: "),
            ):
                stale_rules.load_watched({"hadolint": entry})


class MainTest(unittest.TestCase):
    def test_main_on_repo_baseline_passes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = stale_rules.main([])
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
