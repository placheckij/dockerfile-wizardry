"""Generate or check the table of contents in README.md.

The TOC lives between the markers

    <!-- toc:start -->
    <!-- toc:end -->

and lists every level-2 and level-3 heading (except the TOC's own heading). Anchors follow
GitHub's own rules - which keep the invisible emoji characters (variation selectors, zero-width
joiners, keycaps) in the anchor, so they cannot sensibly be written by hand - and are verified
against how github.com renders the page.

Usage:
    python3 .github/scripts/readme_toc.py           # rewrite the TOC in place
    python3 .github/scripts/readme_toc.py --check   # exit 1 if the TOC is out of date (CI)

Runs with the runner's system python3 (no third-party packages).
"""

import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"
START = "<!-- toc:start -->"
END = "<!-- toc:end -->"
TOC_TITLE = "Table of Contents"
LISTED_LEVELS = (2, 3)
# Space, hyphen and the zero-width joiner (kept in GitHub anchors; built with chr() so that no
# invisible character sits in this source file)
KEPT_PUNCTUATION = " -" + chr(0x200D)


def headings(text):
    """Yield (level, heading text) for every heading outside fenced code blocks."""
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)[0]
            elif line.startswith(fence * 3):
                fence = None
            continue
        if fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if match:
            yield len(match.group(1)), match.group(2)


def plain(text):
    """Heading text without inline Markdown markup."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links and images
    text = text.replace("`", "")
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)  # bold
    text = re.sub(r"(?<!\w)([*_])(.*?)\1(?!\w)", r"\2", text)  # emphasis
    return text


def slugify(text):
    """GitHub's heading anchor: lowercase; keep letters, numbers, marks, connector punctuation,
    hyphens, the zero-width joiner and spaces; drop everything else; spaces become hyphens."""
    kept = []
    for char in plain(text).lower():
        category = unicodedata.category(char)
        if char in KEPT_PUNCTUATION or category[0] in "LNM" or category == "Pc":
            kept.append(char)
    return "".join(kept).replace(" ", "-")


def anchors(text):
    """(level, heading text, unique anchor) for every heading, numbering duplicates like GitHub."""
    seen = {}
    result = []
    for level, title in headings(text):
        base = slugify(title)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.append((level, title, base if count == 0 else f"{base}-{count}"))
    return result


def build_toc(text):
    lines = []
    for level, title, anchor in anchors(text):
        if level not in LISTED_LEVELS or plain(title).strip().endswith(TOC_TITLE):
            continue
        # Percent-encode: the anchors contain invisible characters, which stay unambiguous this way
        target = urllib.parse.quote(anchor, safe="-_")
        lines.append(f"{'  ' * (level - LISTED_LEVELS[0])}- [{title}](#{target})")
    return "\n".join(lines)


def render(text):
    if (
        text.count(START) != 1
        or text.count(END) != 1
        or text.index(START) > text.index(END)
    ):
        raise SystemExit(f"README.md must contain exactly one {START} ... {END} block")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    return head + START + "\n" + build_toc(text) + "\n" + END + tail


def main():
    text = README.read_text(encoding="utf-8")
    new = render(text)
    if "--check" in sys.argv[1:]:
        if new != text:
            print(
                "README.md's table of contents is out of date.\n"
                "Run:  python3 .github/scripts/readme_toc.py   and commit the result.",
                file=sys.stderr,
            )
            return 1
        print("README.md's table of contents is up to date.")
        return 0
    if new != text:
        README.write_text(new, encoding="utf-8")
        print("README.md's table of contents updated.")
    else:
        print("README.md's table of contents already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
