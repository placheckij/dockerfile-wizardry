"""Render the skill's references folder from the rulebook in docs/rules/.

skills/dockerfile-wizardry/references/ is generated: check_rules.py --write creates it and
--check fails when it has drifted. The folder holds rules.md (every rule), tradeoffs.md (the
trade-offs page) and a copy of the example manifests. Relative links become absolute GitHub
links, because the skill is installed without the rest of the repository.

Runs with the runner's system python3 (no third-party packages).
"""

import posixpath
import re
import sys
from pathlib import Path

# check_rules.py sits next to this file; `python3 -I` does not put the script's directory on
# the path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_rules

REPO_BLOB = "https://github.com/placheckij/dockerfile-wizardry/blob/main/"
REFERENCES = Path("skills") / "dockerfile-wizardry" / "references"
EXAMPLES = ("compose.yaml", "pod.yaml")
HEADER = (
    f"This file is generated from [docs/rules/]({REPO_BLOB}docs/rules/) and must not be edited "
    "by hand: change the rulebook, then run `python3 .github/scripts/check_rules.py --write`. "
    '"This repository" below means placheckij/dockerfile-wizardry, where the rulebook lives, '
    "not the project the skill is used on."
)
# fenced code blocks and inline code spans, which are left alone
CODE_RE = re.compile(
    r"(^ {0,3}(`{3,}|~{3,}).*?^ {0,3}\2[`~]*[ \t]*$|(`+)(?:(?!\3).)+?\3)",
    re.DOTALL | re.MULTILINE,
)


def absolutize_links(text, source):
    """`text` with relative link targets rewritten to GitHub URLs. `source` is the
    repo-relative path of the file `text` came from, which relative targets are resolved
    against."""

    def absolute(target):
        bare = target.strip("<>")
        if re.match(r"[a-z][a-z0-9+.-]*:", bare, re.IGNORECASE):
            return target
        file_part, hash_, fragment = bare.partition("#")
        if file_part.startswith("/"):
            path = posixpath.normpath(file_part.lstrip("/"))
        elif file_part:
            path = posixpath.normpath(
                posixpath.join(posixpath.dirname(source), file_part)
            )
        else:
            path = source
        url = REPO_BLOB + path + hash_ + fragment
        return f"<{url}>" if target.startswith("<") else url

    def rewrite(match):
        start, end = match.start(1) - match.start(), match.end(1) - match.start()
        whole = match.group()
        return whole[:start] + absolute(match.group(1)) + whole[end:]

    # split() returns the text between code, then the three groups of each code match; only
    # the text (every fourth piece) is rewritten and the code (the next piece) kept
    parts = CODE_RE.split(text)
    for i in range(0, len(parts), 4):
        parts[i] = check_rules.DEFINITION_RE.sub(
            rewrite, check_rules.LINK_RE.sub(rewrite, parts[i])
        )
    return "".join(part for i, part in enumerate(parts) if i % 4 in (0, 1))


def render_rules_reference(rules):
    """The Markdown page listing every rule with its statement, reasoning and sources."""
    lines = [HEADER, "", "# Dockerfile rules", ""]
    for rule in sorted(rules, key=lambda r: check_rules._natural(r.id)):
        entry = [
            f"## {rule.id}: {rule.title}",
            "",
            f"Strength: {rule.strength}. Last verified: {rule.last_verified}.",
            "",
            rule.statement,
            "",
            f"Why: {rule.why}",
            "",
            f"How to check: {rule.how_to_check}",
            "",
            "Sources:",
            *(f"- {url}" for url in rule.sources),
            "",
        ]
        source = f"docs/rules/{rule.theme}.md"
        lines.append(absolutize_links("\n".join(entry), source))
    return "\n".join(lines)


def reference_files(rules, root):
    """(absolute path, expected content) of each generated file in the skill's references."""
    out = root / REFERENCES
    tradeoffs = (root / "docs" / "rules" / "tradeoffs.md").read_text(encoding="utf-8")
    files = [
        (out / "rules.md", render_rules_reference(rules)),
        (
            out / "tradeoffs.md",
            HEADER + "\n\n" + absolutize_links(tradeoffs, "docs/rules/tradeoffs.md"),
        ),
    ]
    for name in EXAMPLES:
        content = (root / "examples" / name).read_text(encoding="utf-8")
        files.append((out / "examples" / name, content))
    return files


def stray_files(root, generated):
    """Files in the skill's references that are not among the generated paths."""
    out = root / REFERENCES
    if not out.is_dir():
        return []
    generated = set(generated)
    return sorted(p for p in out.rglob("*") if p.is_file() and p not in generated)
