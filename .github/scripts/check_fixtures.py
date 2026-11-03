"""Confirm that the labelled Dockerfile fixtures are good or bad as labelled.

Each fixture is a directory fixtures/dockerfiles/<name>/ holding a `Dockerfile` and an
`expected-findings.txt`. The file lists, per line, a rulebook id and the linter codes that
Dockerfile is expected to trigger for it; a good fixture lists only accepted findings, each
with a reason:

    # comments start with a hash
    DW-BASE-01  DL3007
    DW-USER-01  DL3002 DL3059   # Hadolint codes and Docker build-check rule names mix freely
    DW-HEALTH-01                # a rule id with no code, for rules no linter covers

The linters are Hadolint (pinned image, run through Docker) and `docker buildx build --call
check`. The union of the codes they report must equal the union of the listed codes, and every
rule id must exist in docs/rules/.

Usage:
    python3 .github/scripts/check_fixtures.py

Exits 1 on any problem and 2 when Docker is unavailable. Runs with the runner's system python3
(no third-party packages).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# check_rules.py sits next to this file; `python3 -I` does not put the script's directory on the
# path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_rules

# index digest of the v2.15.1 tag, checked with `docker buildx imagetools inspect` on 2026-11-03
HADOLINT_IMAGE = "hadolint/hadolint:v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d"
RULE_ID = re.compile(r"DW-[A-Z]+-\d+")


class DockerUnavailable(Exception):
    """Docker cannot be run here."""


class LinterError(Exception):
    """A linter produced output that cannot be read."""


def parse_expected(text):
    """[(rule id, [codes])] from the text of an expected-findings.txt."""
    entries = []
    for number, line in enumerate(text.splitlines(), start=1):
        tokens = line.split("#", 1)[0].split()
        if not tokens:
            continue
        if not RULE_ID.fullmatch(tokens[0]):
            raise ValueError(
                f"line {number}: {tokens[0]!r} is not a rule id like DW-BASE-01"
            )
        entries.append((tokens[0], tokens[1:]))
    return entries


def run_docker(args, stdin=None):
    """(stdout, stderr) of a docker command. A non-zero exit is normal when a linter finds
    something, so the caller judges the output; stderr is kept to explain a failure."""
    try:
        result = subprocess.run(
            ["docker", *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise DockerUnavailable("the docker command was not found") from error
    return result.stdout, result.stderr


def ensure_docker():
    """Raise DockerUnavailable unless the docker daemon answers."""
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError as error:
        raise DockerUnavailable("the docker command was not found") from error
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or ["no output"]
        raise DockerUnavailable(f"`docker info` failed: {detail[0]}")


def load_json(output, linter, stderr=""):
    """The JSON a linter printed; empty or unreadable output is a LinterError with stderr."""
    detail = f": {stderr.strip()[-500:]}" if stderr.strip() else ""
    if not output.strip():
        raise LinterError(f"{linter} printed nothing{detail}")
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise LinterError(
            f"{linter} did not print valid JSON ({error}){detail}"
        ) from error


def parse_hadolint(output, stderr=""):
    findings = load_json(output, "Hadolint", stderr)
    if not isinstance(findings, list):
        raise LinterError("Hadolint JSON is not a list")
    return {finding["code"] for finding in findings if "code" in finding}


def parse_buildcheck(output, stderr=""):
    result = load_json(output, "docker build check", stderr)
    if not isinstance(result, dict):
        raise LinterError("docker build check JSON is not an object")
    # a Dockerfile buildx cannot parse prints "warnings": null and a "buildError" object
    failure = result.get("buildError") or result.get("error")
    if failure:
        message = failure.get("message") if isinstance(failure, dict) else failure
        raise LinterError(f"docker build check failed: {message}")
    # the key is absent or null when there are no warnings
    return {warning["ruleName"] for warning in result.get("warnings") or []}


def hadolint_codes(dockerfile):
    """Hadolint codes for a Dockerfile. DL3057 (missing HEALTHCHECK) is ignored by default."""
    output, stderr = run_docker(
        [
            "run", "--rm", "-i", HADOLINT_IMAGE,
            "hadolint", "--format", "json", "--info", "DL3057", "-",
        ],
        stdin=dockerfile.read_text(encoding="utf-8"),
    )  # fmt: skip
    return parse_hadolint(output, stderr)


def buildcheck_codes(fixture_dir):
    """Rule names reported by `docker buildx build --call check` for a fixture directory."""
    output, stderr = run_docker(
        ["buildx", "build", "--call", "check,format=json", str(fixture_dir)]
    )
    return parse_buildcheck(output, stderr)


def compare(expected, reported, rule_ids):
    """Problems between the labelled findings and the codes the linters reported."""
    problems = []
    listed = set()
    for rule_id, codes in expected:
        if rule_id not in rule_ids:
            problems.append(f"{rule_id} is not a rule in docs/rules/")
        listed.update(codes)
    for code in sorted(listed - reported):
        problems.append(f"expected {code}, linters did not report it")
    for code in sorted(reported - listed):
        problems.append(f"unexpected {code}")
    return problems


def fixture_problems(fixture, rule_ids):
    """The problems of one fixture directory."""
    expected_path = fixture / "expected-findings.txt"
    if not expected_path.is_file():
        return ["expected-findings.txt is missing"]
    try:
        expected = parse_expected(expected_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"expected-findings.txt: {error}"]
    try:
        reported = hadolint_codes(fixture / "Dockerfile") | buildcheck_codes(fixture)
    except LinterError as error:
        return [str(error)]
    return compare(expected, reported, rule_ids)


def main(argv, root=ROOT):
    if argv:
        print("usage: check_fixtures.py", file=sys.stderr)
        return 2
    rules, problems = check_rules.collect(root)
    if problems:
        print("The rulebook has problems; run check_rules.py:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    rule_ids = {rule.id for rule in rules}
    fixtures = sorted(
        path.parent for path in (root / "fixtures" / "dockerfiles").glob("*/Dockerfile")
    )
    found = []
    try:
        if fixtures:
            ensure_docker()
        for fixture in fixtures:
            found.extend(
                (fixture.name, problem)
                for problem in fixture_problems(fixture, rule_ids)
            )
    except DockerUnavailable as error:
        print(f"Docker is unavailable: {error}", file=sys.stderr)
        return 2
    if found:
        print("The fixtures have problems:", file=sys.stderr)
        for name, problem in found:
            print(f"  - {name}: {problem}", file=sys.stderr)
        return 1
    print(f"{len(fixtures)} fixtures match their labels.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
