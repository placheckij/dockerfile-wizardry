"""Validate the Dockerfile rulebook in docs/rules/.

Each theme file (docs/rules/<theme>.md) holds rule entries. An entry starts with a level-2
heading and is followed by `field: value` lines:

    ## DW-BASE-01: Pin the base image by digest
    strength: MUST                 # MUST | SHOULD | TRADE-OFF
    spells:                        # README spells this rule covers
    - 1
    last_verified: 2026-11-02
    statement:
      One or two sentences.
    why:
      The reason.
    how_to_check:
      A linter rule id, a command, or `manual`.
    sources:                       # https:// links to the primary source
    - https://docs.docker.com/...

The script checks every entry, that every "Spell #N" heading in README.md is covered by a rule,
that every DW id and relative link (with its #anchor) in the prose of docs/rules/*.md resolves,
and that the generated index in docs/rules/README.md is current.

Usage:
    python3 .github/scripts/check_rules.py --check   # exit 1 on any problem (CI)
    python3 .github/scripts/check_rules.py --write   # regenerate the index

Runs with the runner's system python3 (no third-party packages).
"""

import datetime
import re
import sys
import urllib.parse
from dataclasses import dataclass
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# pages in docs/rules/ that hold prose, not rule entries
NON_THEME_FILES = ("README.md", "tradeoffs.md")
# theme file name (without .md) -> the code used in its rule ids
THEMES = {
    "base-image": "BASE",
    "build-and-cache": "BUILD",
    "dependencies": "DEPS",
    "users-and-permissions": "USER",
    "health-and-signals": "HEALTH",
    "secrets": "SECRET",
    "supply-chain": "SUPPLY",
}
STRENGTHS = ("MUST", "SHOULD", "TRADE-OFF")
TEXT_FIELDS = ("statement", "why", "how_to_check")
LIST_FIELDS = ("spells", "sources")
REQUIRED = ("strength", "last_verified", *TEXT_FIELDS, "sources")
KNOWN = (
    *REQUIRED,
    "spells",
)  # `spells` is optional: a rule need not come from a README spell

HEADING_RE = re.compile(r"^## (DW-([A-Z]+)-(\d+)): (.+?)\s*$")
DW_HEADING_RE = re.compile(r"^#{1,6}\s+DW-")
FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*?)\s*$")
INDEX_START = "<!-- rules-index:start -->"
INDEX_END = "<!-- rules-index:end -->"
SPELL_RE = re.compile(r"^###\s.*Spell #(\d+):", re.MULTILINE)
RULE_ID_RE = re.compile(r"\bDW-[A-Z]+-\d+\b")
LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)[^)]*\)")


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


def unfenced_lines(text):
    """The lines of `text` that are outside fenced code blocks."""
    fence = None
    for line in text.splitlines():
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence is None and opening:
            fence = opening.group(1)
            continue
        if fence is not None:
            # a closing fence uses the same character, at least as many times, and has no
            # info string
            if re.fullmatch(
                f" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}", line.rstrip()
            ):
                fence = None
            continue
        yield line


def _entries(path):
    """Yield (id, code, title, body lines) for each rule entry outside fenced code blocks."""
    current = None
    for line in unfenced_lines(path.read_text(encoding="utf-8")):
        heading = HEADING_RE.match(line)
        if DW_HEADING_RE.match(line) and not heading:
            raise RuleError(
                path,
                None,
                f"malformed rule heading {line!r} (expected '## DW-<THEME>-<NN>: <title>')",
            )
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


def _fields(lines, fail):
    """Split an entry body into {field: str | list[str]}; any line that is not part of a field is
    an error, so malformed input cannot be silently dropped."""
    fields = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip():
            continue
        match = FIELD_RE.match(line)
        if not match:
            raise fail(f"unexpected line {line.strip()[:60]!r}")
        name, value = match.groups()
        if name not in KNOWN:
            raise fail(f"unknown field '{name}'")
        if name in fields:
            raise fail(f"field '{name}' appears twice")
        if value:
            fields[name] = value
        elif i < len(lines) and lines[i].startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:].strip())
                i += 1
            fields[name] = items
        else:
            block = []
            while i < len(lines) and (
                not lines[i].strip() or lines[i].startswith("  ")
            ):
                block.append(lines[i].strip())
                i += 1
            fields[name] = "\n".join(block).strip()
    return fields


def parse_rule_file(path):
    path = Path(path)
    theme = path.stem
    if theme not in THEMES:
        raise RuleError(path, None, f"unknown theme (expected one of {sorted(THEMES)})")
    rules = []
    for rule_id, code, title, body in _entries(path):
        fail = partial(RuleError, path, rule_id)
        if code != THEMES[theme]:
            raise fail(f"id must start with DW-{THEMES[theme]}- in {path.name}")
        fields = _fields(body, fail)
        for name in REQUIRED:
            if not fields.get(name):
                raise fail(f"missing field '{name}'")
        for name, value in fields.items():
            wants_list = name in LIST_FIELDS
            if isinstance(value, list) != wants_list:
                raise fail(
                    f"'{name}' must be "
                    + ("a list (one '- ' line per item)" if wants_list else "text")
                )
        if fields["strength"] not in STRENGTHS:
            raise fail(f"strength must be one of {', '.join(STRENGTHS)}")
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields["last_verified"]):
                raise ValueError
            datetime.date.fromisoformat(fields["last_verified"])
        except ValueError:
            raise fail("last_verified must be an ISO date (YYYY-MM-DD)") from None
        for source in fields["sources"]:
            try:
                parts = urllib.parse.urlsplit(source)
                host = parts.hostname
            except ValueError:
                parts, host = None, None
            if (
                parts is None
                or parts.scheme != "https"
                or not host
                or re.search(r"\s", source)
            ):
                raise fail(
                    f"source must be an https:// URL with a host, got '{source}'"
                )
        try:
            spells = [int(n) for n in fields.get("spells", [])]
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
                problems.append(
                    f"{rule.id} names Spell #{number}, which does not exist"
                )
    covered = {number for rule in rules for number in rule.spells}
    for number in sorted(spell_numbers - covered):
        problems.append(f"Spell #{number} has no rule in docs/rules/")
    return problems


def spell_numbers(readme):
    text = "\n".join(unfenced_lines(readme.read_text(encoding="utf-8")))
    return {int(n) for n in SPELL_RE.findall(text)}


def collect(root):
    """(rules, problems) for the whole tree; file errors become problems, not tracebacks."""
    rules, problems = [], []
    rules_dir = root / "docs" / "rules"
    for path in sorted(rules_dir.glob("*.md")):
        if path.name in NON_THEME_FILES:
            continue
        try:
            rules.extend(parse_rule_file(path))
        except RuleError as error:
            problems.append(str(error))
    if not problems:
        problems.extend(validate(rules, spell_numbers(root / "README.md")))
    if not problems:
        problems.extend(check_references(rules_dir, rules))
    return rules, problems


def heading_slug(heading):
    """The anchor GitHub generates for a heading: lower case, punctuation dropped, spaces to
    hyphens."""
    text = re.sub(r"[`*]", "", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def anchors(path):
    """The heading anchors of a Markdown file (a repeated heading gets -1, -2, ...)."""
    found, counts = set(), {}
    for line in unfenced_lines(path.read_text(encoding="utf-8")):
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            slug = heading_slug(match.group(1))
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            found.add(slug if n == 0 else f"{slug}-{n}")
    return found


def check_references(rules_dir, rules):
    """Problems with DW ids and relative links in the prose of docs/rules/*.md."""
    problems = []
    known = {rule.id for rule in rules}
    for path in sorted(rules_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if path.name == "README.md":
            # the generated index is compared with the rules separately, and must be
            # regenerable when it is stale
            head, _, rest = text.partition(INDEX_START)
            text = head + rest.partition(INDEX_END)[2]
        prose = "\n".join(unfenced_lines(text))
        for rule_id in RULE_ID_RE.findall(prose):
            if rule_id not in known:
                problems.append(f"{path.name}: {rule_id} is not a rule")
        # a link's text may wrap over lines, so search the whole text, not line by line
        for target in LINK_RE.findall(prose):
            target = urllib.parse.unquote(target.strip("<>"))
            if re.match(r"[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            file_part, _, fragment = target.partition("#")
            linked = (path.parent / file_part) if file_part else path
            if not linked.exists():
                problems.append(f"{path.name}: link to missing file {file_part}")
            elif (
                fragment and linked.suffix == ".md" and fragment not in anchors(linked)
            ):
                problems.append(f"{path.name}: link {target} has no matching heading")
    return problems


def render_index(rules):
    """The Markdown table listing every rule, sorted by id."""
    lines = [
        "| Rule | Title | Strength | Spells | Theme |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rule in sorted(rules, key=lambda r: r.id):
        title = rule.title.replace("|", "\\|")
        spells = ", ".join(f"#{n}" for n in sorted(rule.spells)) or "-"
        theme = f"[{rule.theme}]({rule.theme}.md)"
        lines.append(f"| {rule.id} | {title} | {rule.strength} | {spells} | {theme} |")
    return "\n".join(lines)


def with_index(text, rules):
    """`text` with the block between the index markers replaced by the current index."""
    if (
        text.count(INDEX_START) != 1
        or text.count(INDEX_END) != 1
        or text.index(INDEX_START) > text.index(INDEX_END)
    ):
        raise ValueError(
            f"must contain exactly one {INDEX_START} ... {INDEX_END} block"
        )
    head, rest = text.split(INDEX_START, 1)
    _, tail = rest.split(INDEX_END, 1)
    return head + INDEX_START + "\n" + render_index(rules) + "\n" + INDEX_END + tail


def main(argv, root=ROOT):
    if sorted(argv) not in (["--check"], ["--write"]):
        print("usage: check_rules.py --check | --write", file=sys.stderr)
        return 2
    rules, problems = collect(root)
    index = root / "docs" / "rules" / "README.md"
    new = None
    if not problems:
        try:
            new = with_index(index.read_text(encoding="utf-8"), rules)
        except (OSError, ValueError) as error:
            problems.append(f"docs/rules/README.md: {error}")
    if problems:
        print("The rulebook has problems:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if "--write" in argv:
        if new != index.read_text(encoding="utf-8"):
            index.write_text(new, encoding="utf-8")
            print("docs/rules/README.md: index updated.")
        return 0
    if new != index.read_text(encoding="utf-8"):
        print(
            "docs/rules/README.md: the rule index is out of date.\n"
            "Run:  python3 .github/scripts/check_rules.py --write   and commit the result.",
            file=sys.stderr,
        )
        return 1
    print("The rulebook is valid and its index is current.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
