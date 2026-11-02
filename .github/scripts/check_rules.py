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
that every DW id, and every relative link or link definition (with its #anchor), in the prose of
docs/rules/*.md and the README resolves (inline code and HTML comments are not searched for links),
and that the generated blocks in docs/rules/README.md (rule index) and docs/rules/sources.md
(sources index, which also lists the sources of docs/rules/tradeoffs.md) are current. Heading
anchors come from readme_toc.py, so both scripts agree with the anchors github.com generates.

Usage:
    python3 .github/scripts/check_rules.py --check   # exit 1 on any problem (CI)
    python3 .github/scripts/check_rules.py --write   # regenerate the generated blocks

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
# readme_toc.py sits next to this file; `python3 -I` does not put the script's directory on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import readme_toc

# pages in docs/rules/ that hold prose, not rule entries
NON_THEME_FILES = ("README.md", "sources.md", "tradeoffs.md")
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
SOURCES_START = "<!-- sources-index:start -->"
SOURCES_END = "<!-- sources-index:end -->"
SPELL_RE = re.compile(r"^###\s.*Spell #(\d+):", re.MULTILINE)
RULE_ID_RE = re.compile(r"\bDW-[A-Z]+-\d+\b")
LINK_RE = re.compile(r"\]\(\s*(<[^>]*>|(?:[^()\s]|\([^()\s]*\))+)[^)]*\)")
DEFINITION_RE = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)", re.MULTILINE)


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
        problems.extend(check_references(rules_dir, rules))
    return rules, problems


def heading_slug(heading):
    """The anchor GitHub generates for a heading (shared with readme_toc.py)."""
    return readme_toc.slugify(heading)


def anchors(path):
    """The heading anchors of a Markdown file, numbered like GitHub numbers repeats."""
    headings, previous = [], ""
    for line in unfenced_lines(path.read_text(encoding="utf-8")):
        atx = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if atx:
            headings.append(atx.group(1))
        elif re.match(r"^ {0,3}(=+|-+)\s*$", line) and previous.strip():
            headings.append(previous.strip())
        previous = line
    return set(readme_toc.unique_slugs(headings))


def prose_lines(text):
    """The lines of `text` outside fenced and indented code blocks. An indented line (four
    spaces or a tab) is code when it follows a blank line or more code, unless the paragraph
    before the blank line belongs to a list, where indentation continues the list item."""
    in_code, blank_before, in_list = False, True, False
    for line in unfenced_lines(text):
        if not line.strip():
            blank_before = True
            yield line
            continue
        indented = line.startswith(("    ", "\t"))
        if indented and (in_code or (blank_before and not in_list)):
            in_code = True
        else:
            in_code = False
            if not indented:
                in_list = bool(re.match(r"^ {0,3}([-*+]|\d+[.)])\s", line)) or (
                    in_list and not blank_before
                )
            yield line
        blank_before = False


def link_targets(prose):
    """Relative-link candidates in `prose`: inline `](target)` links and `[ref]: target`
    definitions. Inline code and HTML comments are not searched."""
    prose = re.sub(r"<!--.*?-->", "", prose, flags=re.DOTALL)
    prose = re.sub(r"(`+)(?:(?!\1).)+?\1", "", prose, flags=re.DOTALL)
    return LINK_RE.findall(prose) + DEFINITION_RE.findall(prose)


def check_references(rules_dir, rules):
    """Problems with DW ids and relative links in the prose of docs/rules/*.md and the README. Ids are checked
    wherever they appear outside fenced code, inline code included."""
    problems = []
    known = {rule.id for rule in rules}
    root = rules_dir.parents[1]
    pages = sorted(rules_dir.glob("*.md"))
    if (root / "README.md").exists():
        pages.append(root / "README.md")
    for path in pages:
        text = path.read_text(encoding="utf-8")
        for page, start, end in (
            ("README.md", INDEX_START, INDEX_END),
            ("sources.md", SOURCES_START, SOURCES_END),
        ):
            if path.parent == rules_dir and path.name == page:
                # a generated block is compared with the rules separately, and must be
                # regenerable when it is stale
                head, _, rest = text.partition(start)
                text = head + rest.partition(end)[2]
        prose = "\n".join(prose_lines(text))
        for rule_id in dict.fromkeys(RULE_ID_RE.findall(prose)):
            if rule_id not in known:
                problems.append(f"{path.name}: {rule_id} is not a rule")
        for target in link_targets(prose):
            target = target.strip().strip("<>")
            if re.match(r"[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            file_part, _, fragment = target.partition("#")
            file_part, fragment = (
                urllib.parse.unquote(x) for x in (file_part, fragment)
            )
            if file_part.startswith("/"):
                linked = root / file_part.lstrip("/")
            else:
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


def tradeoff_sources(path):
    """(section heading, [source URLs]) for each section of the trade-offs page, read from its
    `Sources:` lines."""
    if not path.exists():
        return []
    sections, heading = [], None
    for line in unfenced_lines(path.read_text(encoding="utf-8")):
        match = re.match(r"^## (.+?)\s*$", line)
        if match:
            heading = match.group(1)
        elif heading and line.startswith("Sources:"):
            sections.append((heading, re.findall(r"\]\((https://[^)\s]+)\)", line)))
    return sections


def _natural(text):
    """Sort key that orders the numbers inside `text` by value (rule-2 before rule-12)."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def _label(text):
    """`text` safe to use as link text: Markdown's emphasis and bracket characters escaped."""
    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", text)


def render_sources(rules, tradeoffs=()):
    """Markdown listing every cited source under its site, grouped by page, with links to the
    rules and trade-off sections that cite it."""
    cited = {}  # url -> {reference link: sort key}
    for rule in rules:
        link = (
            f"[{rule.id}]({rule.theme}.md#{heading_slug(f'{rule.id}: {rule.title}')})"
        )
        for source in rule.sources:
            cited.setdefault(source, {})[link] = (0, _natural(rule.id))
    for heading, urls in tradeoffs:
        number = re.match(r"(\d+)\.", heading)
        name = f"trade-off {number.group(1)}" if number else heading
        link = f"[{_label(name)}](tradeoffs.md#{heading_slug(heading)})"
        for url in urls:
            cited.setdefault(url, {})[link] = (1, _natural(heading))
    sites = {}  # site -> page -> [urls]
    for url in cited:
        parts = urllib.parse.urlsplit(url)
        site = parts.hostname.removeprefix("www.")
        page = url.split("#", 1)[0]
        sites.setdefault(site, {}).setdefault(page, []).append(url)

    def shown(url):
        text = url.removeprefix("https://").removeprefix("www.")
        return _label(urllib.parse.unquote(text))

    def refs(url):
        return ", ".join(sorted(cited[url], key=cited[url].get))

    lines = []
    for site in sorted(sites, key=_natural):
        lines += [f"## {site}", ""]
        for page in sorted(sites[site], key=_natural):
            urls = sorted(sites[site][page], key=_natural)
            if len(urls) == 1:
                lines.append(f"- [{shown(urls[0])}](<{urls[0]}>): {refs(urls[0])}")
                continue
            lines.append(f"- [{shown(page)}](<{page}>)")
            for url in urls:
                name = "whole page" if url == page else "#" + url.split("#", 1)[1]
                lines.append(f"  - [{_label(name)}](<{url}>): {refs(url)}")
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def with_block(text, start, end, body):
    """`text` with the block between the `start` and `end` markers replaced by `body`."""
    if (
        text.count(start) != 1
        or text.count(end) != 1
        or text.index(start) > text.index(end)
    ):
        raise ValueError(f"must contain exactly one {start} ... {end} block")
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return head + start + "\n" + body + "\n" + end + tail


def generated_pages(rules, tradeoffs=()):
    """(file name, label, start marker, end marker, body) of each generated block."""
    return (
        ("README.md", "rule index", INDEX_START, INDEX_END, render_index(rules)),
        (
            "sources.md",
            "sources index",
            SOURCES_START,
            SOURCES_END,
            render_sources(rules, tradeoffs),
        ),
    )


def main(argv, root=ROOT):
    if sorted(argv) not in (["--check"], ["--write"]):
        print("usage: check_rules.py --check | --write", file=sys.stderr)
        return 2
    rules, problems = collect(root)
    rules_dir = root / "docs" / "rules"
    updates = []  # (path, label, current text, new text)
    if not problems:
        tradeoffs = tradeoff_sources(rules_dir / "tradeoffs.md")
        for name, label, start, end, body in generated_pages(rules, tradeoffs):
            path = rules_dir / name
            try:
                current = path.read_text(encoding="utf-8")
                updates.append(
                    (path, label, current, with_block(current, start, end, body))
                )
            except (OSError, ValueError) as error:
                problems.append(f"docs/rules/{name}: {error}")
    if problems:
        print("The rulebook has problems:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    stale = [(path, label) for path, label, current, new in updates if current != new]
    if "--write" in argv:
        for path, label, current, new in updates:
            if current != new:
                path.write_text(new, encoding="utf-8")
                print(f"docs/rules/{path.name}: {label} updated.")
        return 0
    if stale:
        for path, label in stale:
            print(
                f"docs/rules/{path.name}: the {label} is out of date.", file=sys.stderr
            )
        print(
            "Run:  python3 .github/scripts/check_rules.py --write   and commit the result.",
            file=sys.stderr,
        )
        return 1
    print("The rulebook is valid and its indexes are current.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
