"""Lint every Dockerfile in the repository that is not a labelled fixture.

Runs Hadolint (the pinned image from check_fixtures.py) and `docker buildx build --call check`
on each tracked file named `Dockerfile` or `Dockerfile.<suffix>` outside fixtures/, with the
repository root as build context. Hadolint findings at warning level and above fail, as do all
build check warnings. Hadolint runs without a repository config, so a `.hadolint.yaml` fails
the check instead of being silently ignored. Fixtures are checked against their labels by check_fixtures.py instead.

Usage:
    python3 .github/scripts/lint_dockerfiles.py

Exits 1 on any finding (or when no Dockerfile is found) and 2 when Docker is unavailable. Runs
with the runner's system python3 (no third-party packages).
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# check_fixtures.py sits next to this file; `python3 -I` does not put the script's directory on
# the path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_fixtures

# the same threshold as Hadolint's `--failure-threshold warning`
FAIL_LEVELS = {"error", "warning"}
DOCKERFILE_RE = re.compile(r"^Dockerfile(\.[^/]+)?$")
# Hadolint runs in a container on stdin, so a repository config would be silently ignored
HADOLINT_CONFIGS = (".hadolint.yaml", ".hadolint.yml")


def tracked_dockerfiles(root):
    """Tracked Dockerfiles outside fixtures/, sorted by path."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths = [
        Path(name)
        for name in result.stdout.split("\0")
        if DOCKERFILE_RE.match(Path(name).name)
        and not name.endswith(".dockerignore")
        and not name.startswith("fixtures/")
    ]
    return [root / path for path in sorted(paths, key=lambda p: p.as_posix())]


def main(argv, root=ROOT):
    if argv:
        print("usage: lint_dockerfiles.py", file=sys.stderr)
        return 2
    configs = [name for name in HADOLINT_CONFIGS if (root / name).exists()]
    if configs:
        print(
            f"{', '.join(configs)}: not applied, because Hadolint runs in a container on "
            "stdin. Pass it to the container in check_fixtures.hadolint_codes first.",
            file=sys.stderr,
        )
        return 1
    dockerfiles = tracked_dockerfiles(root)
    if not dockerfiles:
        print("No Dockerfile found outside fixtures/.", file=sys.stderr)
        return 1
    found = []
    try:
        check_fixtures.ensure_docker()
        for dockerfile in dockerfiles:
            name = dockerfile.relative_to(root).as_posix()
            try:
                codes = check_fixtures.hadolint_codes(
                    dockerfile, levels=FAIL_LEVELS
                ) | check_fixtures.buildcheck_codes(root, dockerfile)
            except check_fixtures.LinterError as error:
                found.append(f"{name}: {error}")
                continue
            found.extend(f"{name}: {code}" for code in sorted(codes))
    except check_fixtures.DockerUnavailable as error:
        print(f"Docker is unavailable: {error}", file=sys.stderr)
        return 2
    if found:
        print("The Dockerfiles have linter findings:", file=sys.stderr)
        for line in found:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(
        f"{len(dockerfiles)} Dockerfiles pass Hadolint (warning and above) and Docker's "
        "build checks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
