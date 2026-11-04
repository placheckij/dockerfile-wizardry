"""Upstream signals the standards watch compares with .github/standards-baseline.json.

Each watcher reads one stable signal, not a page hash, so wording edits on a page do not raise
alarms but a change the rules depend on does:

  * dockerfile_frontend: newest stable `dockerfile/X.Y.Z` tag of moby/buildkit (the frontend
    that `# syntax=docker/dockerfile:1` resolves to); `-labs` and `-rcN` tags are ignored
  * build_checks: the rule pages in buildkit's frontend/dockerfile/docs/rules, which
    docs.docker.com/reference/build-checks/ is rendered from
  * hadolint: the latest Hadolint release and the DL rule codes listed in its README
  * distroless: the Debian versions the distroless README lists images for

Everything is read through `gh api` and is untrusted: values are matched against strict
patterns before they are compared or printed, and finding nothing is a CheckError (the check
could not run), never "up to date".

Imported by check_standards.py. Runs with the runner's system python3 (no third-party packages).
"""

import re
import subprocess
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field

BASELINE_NAME = ".github/standards-baseline.json"
BUILDKIT = "moby/buildkit"
BUILD_CHECKS_DIR = "frontend/dockerfile/docs/rules"

FRONTEND_REF_RE = re.compile(r"^refs/tags/dockerfile/(\d+\.\d+\.\d+)$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
HADOLINT_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
CHECK_FILE_RE = re.compile(r"^([a-z0-9-]+)\.md$")
CHECK_NAME_RE = re.compile(r"^[a-z0-9-]+$")
HADOLINT_CITED_RE = re.compile(r"\[(DL\d{4})\]")
HADOLINT_CODE_RE = re.compile(r"^DL\d{4}$")
DISTROLESS_IMAGE_RE = re.compile(r"distroless/[a-z0-9-]+-debian(\d+)\b")
DEBIAN_RE = re.compile(r"^\d+$")


class CheckError(Exception):
    """The check itself could not run (exit code 2)."""


def gh_api(path, jq=None, raw=False, paginate=False):
    """The stdout of `gh api <path>`; CheckError when the call fails or prints nothing."""
    args = ["gh", "api"]
    if paginate:
        args.append("--paginate")
    if raw:
        args += ["-H", "Accept: application/vnd.github.raw"]
    if jq:
        args += ["--jq", jq]
    args.append(path)
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=60, check=False
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise CheckError(f"could not run 'gh api {path}': {error}") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise CheckError(
            f"'gh api {path}' failed: {result.stderr.strip()[:200] or 'no output'}"
        )
    return result.stdout


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def latest_stable(refs):
    """The newest X.Y.Z among `refs/tags/dockerfile/X.Y.Z` refs."""
    versions = [m.group(1) for ref in refs if (m := FRONTEND_REF_RE.match(ref.strip()))]
    if not versions:
        raise CheckError(f"no stable dockerfile/X.Y.Z tag found in {BUILDKIT}")
    return max(versions, key=version_key)


def _nonempty(values, what):
    if not values:
        raise CheckError(f"no {what} found - did the upstream layout change?")
    return sorted(set(values))


def build_check_names(names):
    """Build check names from the file names of buildkit's rule pages."""
    found = [
        m.group(1)
        for name in names
        if (m := CHECK_FILE_RE.match(name.strip())) and name.strip() != "_index.md"
    ]
    return _nonempty(found, f"build check pages in {BUILDKIT}/{BUILD_CHECKS_DIR}")


def hadolint_rules(readme):
    return _nonempty(
        HADOLINT_CITED_RE.findall(readme), "DL rules in the Hadolint README"
    )


def distroless_debian_versions(readme):
    return _nonempty(
        DISTROLESS_IMAGE_RE.findall(readme), "Debian images in the distroless README"
    )


def set_diff(reviewed, current):
    """`+ x` for each added value, then `- y` for each removed one."""
    added = sorted(set(current) - set(reviewed))
    removed = sorted(set(reviewed) - set(current))
    return [f"+ {value}" for value in added] + [f"- {value}" for value in removed]


@dataclass
class Watch:
    key: str
    status: str
    problem: str | None = None
    diff: list = field(default_factory=list)


def _field(key, entry, name, pattern):
    value = entry.get(name) if isinstance(entry, dict) else None
    if not isinstance(value, str) or not pattern.match(value):
        raise CheckError(f"baseline {key}: {name} is missing or malformed")
    return value


def _list_field(key, entry, name, pattern):
    value = entry.get(name) if isinstance(entry, dict) else None
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and pattern.match(item) for item in value)
    ):
        raise CheckError(f"baseline {key}: {name} is missing or malformed")
    return value


def _update_hint(key, name):
    return f"set {key}.{name} in {BASELINE_NAME}"


def watch_dockerfile_frontend(entry):
    key = "dockerfile_frontend"
    reviewed = _field(key, entry, "reviewed_version", VERSION_RE)
    refs = gh_api(
        f"repos/{BUILDKIT}/git/matching-refs/tags/dockerfile/",
        jq=".[].ref",
        paginate=True,
    ).splitlines()
    latest = latest_stable(refs)
    watch = Watch(key, f"Dockerfile frontend  : newest {latest}, reviewed {reviewed}")
    if version_key(latest) > version_key(reviewed):
        watch.problem = (
            f"Dockerfile frontend: newest is {latest}, this repo was checked against {reviewed}.\n"
            f"  Release notes: https://github.com/{BUILDKIT}/releases/tag/dockerfile%2F{latest}\n"
            f"  Re-check the rules below, then {_update_hint(key, 'reviewed_version')}."
        )
    return watch


def _set_watch(
    key, label, reviewed, current, field_name, link, status_prefix="", list_name=None
):
    diff = set_diff(reviewed, current)
    watch = Watch(
        key,
        f"{label:<21}: {status_prefix}{len(current)} upstream, {len(reviewed)} reviewed, "
        f"{len(diff)} changed",
        diff=diff,
    )
    if diff:
        watch.problem = (
            f"{list_name or label}: the list changed ({len(diff)} added or removed, shown below).\n"
            f"  Look at {link}\n"
            f"  Re-check the rules below, then {_update_hint(key, field_name)}."
        )
    return watch


def watch_build_checks(entry):
    key = "build_checks"
    reviewed = _list_field(key, entry, "reviewed_checks", CHECK_NAME_RE)
    names = gh_api(
        f"repos/{BUILDKIT}/contents/{BUILD_CHECKS_DIR}", jq=".[].name"
    ).splitlines()
    return _set_watch(
        key,
        "Build Checks",
        reviewed,
        build_check_names(names),
        "reviewed_checks",
        "https://docs.docker.com/reference/build-checks/",
    )


def watch_hadolint(entry):
    key = "hadolint"
    reviewed_release = _field(key, entry, "reviewed_release", HADOLINT_TAG_RE)
    reviewed_rules = _list_field(key, entry, "reviewed_rules", HADOLINT_CODE_RE)
    tag = gh_api("repos/hadolint/hadolint/releases/latest", jq=".tag_name").strip()
    if not HADOLINT_TAG_RE.match(tag):
        raise CheckError("unexpected tag name from the Hadolint releases API")
    rules = hadolint_rules(gh_api("repos/hadolint/hadolint/readme", raw=True))
    watch = _set_watch(
        key,
        "Hadolint",
        reviewed_rules,
        rules,
        "reviewed_rules",
        "https://github.com/hadolint/hadolint#rules",
        status_prefix=f"newest {tag}, reviewed {reviewed_release}; rules: ",
        list_name="Hadolint rules",
    )
    if version_key(tag[1:]) > version_key(reviewed_release[1:]):
        release = (
            f"Hadolint: newest release is {tag}, this repo was checked against "
            f"{reviewed_release}.\n"
            f"  Release notes: https://github.com/hadolint/hadolint/releases/tag/{tag}\n"
            f"  Re-check the rules below, then {_update_hint(key, 'reviewed_release')}."
        )
        if (
            watch.problem
        ):  # one bullet: indent the rule-list part under the release part
            release += "\n" + textwrap.indent(watch.problem, "  ")
        watch.problem = release
    return watch


def watch_distroless(entry):
    key = "distroless"
    reviewed = _list_field(key, entry, "reviewed_debian_versions", DEBIAN_RE)
    readme = gh_api("repos/GoogleContainerTools/distroless/readme", raw=True)
    return _set_watch(
        key,
        "distroless Debian",
        reviewed,
        distroless_debian_versions(readme),
        "reviewed_debian_versions",
        "https://github.com/GoogleContainerTools/distroless#what-images-are-available",
    )


WATCHERS: dict[str, Callable[[dict], Watch]] = {
    "dockerfile_frontend": watch_dockerfile_frontend,
    "build_checks": watch_build_checks,
    "hadolint": watch_hadolint,
    "distroless": watch_distroless,
}
