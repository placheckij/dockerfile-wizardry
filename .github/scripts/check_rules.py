"""Validate the Dockerfile rulebook in docs/rules/.

Each theme file (docs/rules/<theme>.md) holds rule entries. An entry starts with a level-2
heading and is followed by `field: value` lines:

    ## DW-BASE-01: Pin the base image by digest
    strength: MUST                 # MUST | SHOULD | TRADE-OFF
    spells:                        # README spells this rule covers
    - 1
    last_verified: 2026-11-02
    statement: |
      One or two sentences.
    why: |
      The reason.
    how_to_check: |
      A linter rule id, a command, or `manual`.
    sources:                       # https:// links to the primary source
    - https://docs.docker.com/...

The script checks every entry, that every "Spell #N" heading in README.md is covered by a rule,
and that the generated index in docs/rules/README.md is current.

Usage:
    python3 .github/scripts/check_rules.py --check   # exit 1 on any problem (CI)
    python3 .github/scripts/check_rules.py --write   # regenerate the index

Runs with the runner's system python3 (no third-party packages).
"""

import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# theme file name (without .md) -> the code used in its rule ids
THEMES = {
    "base-image": "BASE",
    "build-and-cache": "BUILD",
    "dependencies": "DEPS",
    "users-and-permissions": "USER",
    "health-and-signals": "HEALTH",
}
STRENGTHS = ("MUST", "SHOULD", "TRADE-OFF")
TEXT_FIELDS = ("statement", "why", "how_to_check")
REQUIRED = ("strength", "spells", "last_verified", *TEXT_FIELDS, "sources")

HEADING_RE = re.compile(r"^## (DW-([A-Z]+)-(\d+)): (.+?)\s*$")
FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*?)\s*$")
SPELL_RE = re.compile(r"^###\s.*Spell #(\d+):", re.MULTILINE)


class RuleError(Exception):
    def __init__(self, path, rule_id, message):
        self.path = Path(path)
        self.rule_id = rule_id
        where = f"{self.path.name}" + (f" {rule_id}" if rule_id else "")
        super().__init__(f"{where}: {message}")


@dataclass
class Rule:
    id: str
    title: str
    statement: str
    strength: str
    why: str
    how_to_check: str
    sources: list
    spells: list
    last_verified: str
    theme: str
    path: Path


def _entries(path):
    """Yield (id, code, title, body lines) for each rule entry outside fenced code blocks."""
    fence = None
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = re.match(r"^(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)[0]
            elif line.startswith(fence * 3):
                fence = None
            continue
        if fence:
            continue
        heading = HEADING_RE.match(line)
        if heading:
            if current:
                yield current
            current = (heading.group(1), heading.group(2), heading.group(4), [])
        elif line.startswith("#"):
            if current:
                yield current
            current = None
        elif current:
            current[3].append(line)
    if current:
        yield current


def _fields(lines):
    """Split an entry body into {field: str | list[str]}."""
    fields = {}
    i = 0
    while i < len(lines):
        match = FIELD_RE.match(lines[i])
        i += 1
        if not match:
            continue
        name, value = match.groups()
        if value == "|":
            block = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith(" ")):
                block.append(lines[i].strip())
                i += 1
            fields[name] = "\n".join(block).strip()
        elif value == "":
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:].strip())
                i += 1
            fields[name] = items
        else:
            fields[name] = value
    return fields


def parse_rule_file(path):
    path = Path(path)
    theme = path.stem
    if theme not in THEMES:
        raise RuleError(path, None, f"unknown theme (expected one of {sorted(THEMES)})")
    rules = []
    for rule_id, code, title, body in _entries(path):
        fail = lambda message, rule_id=rule_id: RuleError(path, rule_id, message)  # noqa: E731
        if code != THEMES[theme]:
            raise fail(f"id must start with DW-{THEMES[theme]}- in {path.name}")
        fields = _fields(body)
        for name in REQUIRED:
            if not fields.get(name):
                raise fail(f"missing field '{name}'")
        if fields["strength"] not in STRENGTHS:
            raise fail(f"strength must be one of {', '.join(STRENGTHS)}")
        try:
            datetime.date.fromisoformat(fields["last_verified"])
        except ValueError:
            raise fail("last_verified must be an ISO date (YYYY-MM-DD)") from None
        for source in fields["sources"]:
            if not re.match(r"^https://[^\s/]+\S*$", source):
                raise fail(f"source must be an https:// URL, got '{source}'")
        try:
            spells = [int(n) for n in fields["spells"]]
        except ValueError:
            raise fail("spells must be a list of spell numbers") from None
        rules.append(
            Rule(
                id=rule_id,
                title=title,
                statement=fields["statement"],
                strength=fields["strength"],
                why=fields["why"],
                how_to_check=fields["how_to_check"],
                sources=fields["sources"],
                spells=spells,
                last_verified=fields["last_verified"],
                theme=theme,
                path=path,
            )
        )
    return rules


def validate(rules, spell_numbers):
    """Cross-file problems: duplicate ids, unknown spells, spells without a rule."""
    problems = []
    seen = set()
    for rule in rules:
        if rule.id in seen:
            problems.append(f"duplicate rule id {rule.id}")
        seen.add(rule.id)
        for number in rule.spells:
            if number not in spell_numbers:
                problems.append(f"{rule.id} names Spell #{number}, which does not exist")
    covered = {number for rule in rules for number in rule.spells}
    for number in sorted(spell_numbers - covered):
        problems.append(f"Spell #{number} has no rule in docs/rules/")
    return problems


def spell_numbers(readme):
    return {int(n) for n in SPELL_RE.findall(readme.read_text(encoding="utf-8"))}


def collect(root):
    """(rules, problems) for the whole tree; file errors become problems, not tracebacks."""
    rules, problems = [], []
    rules_dir = root / "docs" / "rules"
    for path in sorted(rules_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        try:
            rules.extend(parse_rule_file(path))
        except RuleError as error:
            problems.append(str(error))
    if not problems:
        problems.extend(validate(rules, spell_numbers(root / "README.md")))
    return rules, problems


def main(argv, root=ROOT):
    _, problems = collect(root)
    if problems:
        print("The rulebook has problems:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("The rulebook is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
