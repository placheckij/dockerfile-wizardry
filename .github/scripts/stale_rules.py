"""Fail while a rule is older than a recorded change to a source it cites.

.github/standards-baseline.json records, per watched upstream source, the value this repo was
last checked against. Each entry lists `rule_sources`: URL prefixes that tie it to the rules
(and trade-off sections) citing it. A rule cites a watched source when one of its `sources`
starts with one of those prefixes. When the monthly standards watch reports a change and the
baseline is moved to the new value, the entry's `changed_on` is set to that date; from then on
every rule citing the source must have a `last_verified` date on or after `changed_on`.

The script also fails when a prefix matches no rule and no trade-off source, since a typo there
would silently switch the check off for that source.

Usage:
    python3 .github/scripts/stale_rules.py

Exits 0 when every rule is current, 1 on stale rules, unmatched prefixes or rulebook problems,
and 2 when the baseline is missing or malformed. Needs no network. Runs with the runner's system
python3 (no third-party packages).
"""

import datetime
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# check_rules.py sits next to this file; `python3 -I` does not put the script's directory on the
# path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_rules


class BaselineError(Exception):
    """The baseline file is missing or malformed."""


@dataclass
class Watched:
    key: str
    prefixes: list
    changed_on: str | None


def _valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10


def load_watched(baseline):
    """The watched sources of a parsed baseline: every object-valued key."""
    watched = []
    for key, entry in baseline.items():
        if key.startswith("_") or not isinstance(entry, dict):
            continue
        prefixes = entry.get("rule_sources")
        if (
            not isinstance(prefixes, list)
            or not prefixes
            or not all(
                isinstance(p, str) and p.startswith("https://") for p in prefixes
            )
        ):
            raise BaselineError(
                f"{key}: rule_sources must be a non-empty list of https:// prefixes"
            )
        changed_on = entry.get("changed_on")
        if changed_on is not None and not _valid_date(changed_on):
            raise BaselineError(f"{key}: changed_on must be a YYYY-MM-DD date")
        watched.append(Watched(key, prefixes, changed_on))
    return watched


def cites(urls, prefixes):
    return any(url.startswith(prefix) for url in urls for prefix in prefixes)


def cited_by(prefixes, rules, tradeoffs):
    """Labels of the rules, then the trade-off sections, that cite one of `prefixes`."""
    labels = sorted(rule.id for rule in rules if cites(rule.sources, prefixes))
    labels += [
        f"tradeoffs.md: {heading}"
        for heading, urls in tradeoffs
        if cites(urls, prefixes)
    ]
    return labels


def stale(rules, watched):
    """(rule id, key, changed_on, last_verified) for rules verified before a recorded change."""
    found = [
        (rule.id, source.key, source.changed_on, rule.last_verified)
        for rule in rules
        for source in watched
        if source.changed_on
        and cites(rule.sources, source.prefixes)
        and rule.last_verified < source.changed_on
    ]
    return sorted(found)


def unmatched(watched, rules, tradeoffs):
    """(key, prefix) for prefixes that no rule source and no trade-off source starts with."""
    urls = [url for rule in rules for url in rule.sources]
    urls += [url for _, section_urls in tradeoffs for url in section_urls]
    return [
        (source.key, prefix)
        for source in watched
        for prefix in source.prefixes
        if not cites(urls, [prefix])
    ]


def main(argv, root=ROOT):
    if argv:
        print("usage: stale_rules.py", file=sys.stderr)
        return 2
    baseline_path = root / ".github" / "standards-baseline.json"
    try:
        watched = load_watched(json.loads(baseline_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, AttributeError, BaselineError) as error:
        print(f"{baseline_path.relative_to(root)}: {error}", file=sys.stderr)
        return 2
    rules, problems = check_rules.collect(root)
    if problems:
        print("The rulebook has problems; run check_rules.py:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    tradeoffs = check_rules.tradeoff_sources(root / "docs" / "rules" / "tradeoffs.md")
    found = [
        f"{rule_id} cites {key}, which changed on {changed_on}; last verified {verified}"
        for rule_id, key, changed_on, verified in stale(rules, watched)
    ]
    found += [
        f"{key}: prefix {prefix} matches no rule or trade-off source"
        for key, prefix in unmatched(watched, rules, tradeoffs)
    ]
    if found:
        print("Rules to re-check against the standards baseline:", file=sys.stderr)
        for line in found:
            print(f"  - {line}", file=sys.stderr)
        print(
            "Re-read each rule's sources, then set its last_verified date.",
            file=sys.stderr,
        )
        return 1
    print(
        "No rule is older than a recorded change to the sources it cites "
        f"({len(watched)} watched sources)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
