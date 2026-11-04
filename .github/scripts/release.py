"""Keep CHANGELOG.md and the plugin version in step, and prepare releases.

The plugin is what users install: the skill in skills/ and the manifests in .claude-plugin/.
Claude Code gives existing users a new copy only when the `version` in
.claude-plugin/plugin.json changes, so that version is the release. CHANGELOG.md starts with an
`## [Unreleased]` section, followed by one `## [X.Y.Z] - YYYY-MM-DD` section per version, newest
first.

Usage:
    python3 .github/scripts/release.py check [--base REF]
        Fail when CHANGELOG.md is malformed or its newest version is not plugin.json's. With
        --base, also fail when the changes since REF touch the plugin but leave Unreleased
        unchanged or empty (a release, which raises the version, is exempt), or lower the
        version. Rewording or removing an entry counts as a change: the check is a reminder,
        and amending the entry for the same rule, or a revert removing its own, is legitimate.
    python3 .github/scripts/release.py prepare patch|minor|major
        Bump plugin.json and move the Unreleased entries into a section for the new version,
        dated today. Commit the result and open it as a pull request.
    python3 .github/scripts/release.py bumped REF
        Print plugin.json's version if it differs from the one at REF; print nothing otherwise.
    python3 .github/scripts/release.py notes VERSION
        Print the CHANGELOG.md entries for VERSION (the GitHub Release's notes).
    python3 .github/scripts/release.py pending [--days N]
        Fail when a commit older than N days (default 14) changed the plugin after the last
        release: the tag vX.Y.Z of plugin.json's version, or else the last version change.

Exits 0 on success, 1 when a check fails and 2 on bad usage or unreadable files. `bumped`,
`--base` and `pending` need the git history back to REF or to the last release. Runs with
the runner's system python3 (no third-party packages).
"""

import datetime
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = "CHANGELOG.md"
PLUGIN = ".claude-plugin/plugin.json"
# what an installed plugin is made of; a change under these needs a changelog entry
SHIPPED = ("skills/", ".claude-plugin/")
UNRELEASED = "Unreleased"
SECTION_RE = re.compile(r"^## \[([^\]]+)\](?: - (\S+))?[ \t]*$", re.MULTILINE)
VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
PLUGIN_VERSION_RE = re.compile(r'("version"\s*:\s*")([^"]*)(")')
PARTS = ("major", "minor", "patch")


class ReleaseError(Exception):
    """A file is missing or malformed, or git failed."""


@dataclass
class Section:
    name: str
    date: str | None
    # the text between this heading and the next one
    body: str
    start: int
    end: int


def parse_version(text):
    match = VERSION_RE.fullmatch(text)
    if not match:
        raise ReleaseError(f"{text!r} is not a MAJOR.MINOR.PATCH version")
    return tuple(int(part) for part in match.groups())


def bump(version, part):
    major, minor, patch = parse_version(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def sections(text):
    """The `## [...]` sections of a changelog, in order."""
    found = []
    matches = list(SECTION_RE.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        found.append(
            Section(
                name=match.group(1),
                date=match.group(2),
                body=text[match.end() : end],
                start=match.start(),
                end=end,
            )
        )
    return found


def has_entries(body):
    """True when a section body holds more than blank lines and `###` group headings."""
    return any(
        line.strip() and not line.startswith("###") for line in body.splitlines()
    )


def validate(text):
    """Problems with the changelog's structure, as strings."""
    found = sections(text)
    if not found or found[0].name != UNRELEASED:
        return [f"{CHANGELOG} must start its sections with ## [{UNRELEASED}]"]
    problems = []
    if found[0].date is not None:
        problems.append(f"## [{UNRELEASED}] takes no date")
    previous = None
    for section in found[1:]:
        try:
            version = parse_version(section.name)
        except ReleaseError as error:
            problems.append(f"## [{section.name}]: {error}")
            continue
        if section.date is None or not DATE_RE.fullmatch(section.date):
            problems.append(
                f"## [{section.name}] needs a date: ## [X.Y.Z] - YYYY-MM-DD"
            )
        else:
            try:
                datetime.date.fromisoformat(section.date)
            except ValueError:
                problems.append(f"## [{section.name}]: {section.date} is not a date")
        if previous is not None and version >= previous:
            problems.append(
                f"## [{section.name}] must be older than the section above it"
            )
        if not has_entries(section.body):
            problems.append(f"## [{section.name}] has no entries")
        previous = version
    if len(found) == 1:
        problems.append(f"{CHANGELOG} has no released version")
    return problems


def latest_version(text):
    found = sections(text)
    return found[1].name if len(found) > 1 else None


def plugin_version(text):
    try:
        version = json.loads(text).get("version")
    except (ValueError, AttributeError) as error:
        raise ReleaseError(f"{PLUGIN} is not a JSON object: {error}") from error
    if not isinstance(version, str):
        raise ReleaseError(f"{PLUGIN} has no version")
    parse_version(version)
    return version


def touches_plugin(paths):
    return any(path.startswith(SHIPPED) for path in paths)


def prepare(changelog, plugin, part, today):
    """(new changelog, new plugin.json, new version) for a `part` release dated `today`."""
    problems = validate(changelog)
    if problems:
        raise ReleaseError("; ".join(problems))
    unreleased = sections(changelog)[0]
    if not has_entries(unreleased.body):
        raise ReleaseError(f"## [{UNRELEASED}] has no entries to release")
    old = plugin_version(plugin)
    new = bump(old, part)
    heading = f"## [{UNRELEASED}]\n\n## [{new}] - {today}\n"
    body = unreleased.body.lstrip("\n")
    changelog = (
        changelog[: unreleased.start]
        + heading
        + "\n"
        + body
        + changelog[unreleased.end :]
    )
    plugin, count = PLUGIN_VERSION_RE.subn(rf"\g<1>{new}\g<3>", plugin, count=1)
    if count != 1:
        raise ReleaseError(f"{PLUGIN}: no version field to rewrite")
    return changelog, plugin, new


def notes(changelog, version):
    for section in sections(changelog):
        if section.name == version:
            return section.body.strip() + "\n"
    raise ReleaseError(f"{CHANGELOG} has no ## [{version}] section")


def git(root, *args):
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def overdue(commit_dates, today, days):
    """The oldest of `commit_dates` (YYYY-MM-DD) when it is more than `days` before `today`."""
    if not commit_dates:
        return None
    oldest = min(datetime.date.fromisoformat(date) for date in commit_dates)
    return oldest if (today - oldest).days > days else None


def read(root, name):
    try:
        return (root / name).read_text(encoding="utf-8")
    except OSError as error:
        raise ReleaseError(f"{name}: {error}") from error


def unreleased_body(text):
    found = sections(text)
    return found[0].body.strip() if found and found[0].name == UNRELEASED else ""


def adds_unreleased_entries(root, base, changelog):
    """True when the Unreleased section has entries and any change from the one at `base`, or
    when `base` has no changelog yet."""
    if CHANGELOG not in git(root, "ls-tree", "--name-only", base).splitlines():
        return True
    now = unreleased_body(changelog)
    return has_entries(now) and now != unreleased_body(
        git(root, "show", f"{base}:{CHANGELOG}")
    )


def run_check(root, base):
    changelog = read(root, CHANGELOG)
    problems = validate(changelog)
    version = plugin_version(read(root, PLUGIN))
    latest = latest_version(changelog)
    if latest is not None and latest != version:
        problems.append(
            f"{PLUGIN} says {version}, but the newest version in {CHANGELOG} is {latest}"
        )
    if base is not None:
        # --no-renames: a file moved out of skills/ is listed under its old path as well
        changed = git(
            root, "diff", "--name-only", "--no-renames", base, "HEAD"
        ).splitlines()
        before = plugin_version(git(root, "show", f"{base}:{PLUGIN}"))
        # a release moves the entries out of Unreleased, and the pull request that adds the
        # changelog has nothing to compare with
        if (
            touches_plugin(changed)
            and version == before
            and not adds_unreleased_entries(root, base, changelog)
        ):
            problems.append(
                f"this changes the plugin ({', '.join(SHIPPED)}) but leaves "
                f"## [{UNRELEASED}] in {CHANGELOG} unchanged: add an entry there"
            )
        if parse_version(version) < parse_version(before):
            problems.append(f"{PLUGIN} lowers the version from {before} to {version}")
    if problems:
        print(f"{CHANGELOG} and {PLUGIN} disagree:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"{CHANGELOG} is well formed and matches {PLUGIN} ({version}).")
    return 0


def run_prepare(root, part):
    changelog, plugin, new = prepare(
        read(root, CHANGELOG),
        read(root, PLUGIN),
        part,
        datetime.date.today().isoformat(),
    )
    (root / CHANGELOG).write_text(changelog, encoding="utf-8")
    (root / PLUGIN).write_text(plugin, encoding="utf-8")
    print(f"Prepared {new} in {CHANGELOG} and {PLUGIN}.")
    print(
        "Review the section, commit both files and open a pull request; merging it tags "
        f"v{new} and publishes the GitHub Release."
    )
    return 0


def run_bumped(root, base):
    version = plugin_version(read(root, PLUGIN))
    if version != plugin_version(git(root, "show", f"{base}:{PLUGIN}")):
        print(version)
    return 0


def last_release(root, version):
    """The commit tagged v`version`, or else the commit that last set the version in
    plugin.json (a release whose tag is not made yet, or the plugin's first commit)."""
    try:
        return git(
            root, "rev-parse", "--verify", "--quiet", f"refs/tags/v{version}^{{commit}}"
        ).strip()
    except ReleaseError:
        pass
    last = git(
        root, "log", "-1", "--format=%H", "-G", '"version"', "--", PLUGIN
    ).strip()
    if not last:
        raise ReleaseError(f"no commit sets the version in {PLUGIN}")
    return last


def run_pending(root, days):
    version = plugin_version(read(root, PLUGIN))
    last = last_release(root, version)
    dates = git(
        root, "log", "--format=%cs", f"{last}..HEAD", "--", *SHIPPED
    ).splitlines()
    oldest = overdue(dates, datetime.date.today(), days)
    if oldest is not None:
        print(
            f"{len(dates)} commit(s) since {version} changed the plugin, the oldest on {oldest} "
            f"(more than {days} days ago). Existing users get them only with a new version: "
            "run `python3 .github/scripts/release.py prepare patch|minor|major`.",
            file=sys.stderr,
        )
        return 1
    print(f"{len(dates)} unreleased commit(s) changed the plugin since {version}.")
    return 0


def main(argv, root=ROOT):
    usage = (
        "usage: release.py check [--base REF] | prepare patch|minor|major | bumped REF | "
        "notes VERSION | pending [--days N]"
    )
    command, rest = (argv[0], argv[1:]) if argv else (None, [])
    try:
        if command == "check" and (not rest or rest[0] == "--base" and len(rest) == 2):
            return run_check(root, rest[1] if rest else None)
        if command == "prepare" and len(rest) == 1 and rest[0] in PARTS:
            return run_prepare(root, rest[0])
        if command == "bumped" and len(rest) == 1:
            return run_bumped(root, rest[0])
        if command == "notes" and len(rest) == 1:
            print(notes(read(root, CHANGELOG), rest[0]), end="")
            return 0
        if command == "pending" and (
            not rest or rest[0] == "--days" and len(rest) == 2 and rest[1].isdecimal()
        ):
            return run_pending(root, int(rest[1]) if rest else 14)
    except ReleaseError as error:
        print(error, file=sys.stderr)
        return 2
    print(usage, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
