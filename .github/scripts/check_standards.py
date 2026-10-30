#!/usr/bin/env python3
"""Fail when the security references this repo cites have moved on.

Compares upstream state with .github/standards-baseline.json:
  * CIS Docker Benchmark: newest version listed on cisecurity.org
  * OWASP Docker Security Cheat Sheet: newest commit to the source file
  * every OWASP anchor cited in the docs must still exist on the live page

Exit codes: 0 = up to date, 1 = outdated (or a cited anchor is broken),
2 = could not check (page layout changed, network error, ...). Any non-zero
exit fails the workflow, and GitHub emails the failed scheduled run.

Usage: check_standards.py [--report-only]
  --report-only  still fails on exit 2, but exits 0 when merely outdated
                 (used on pull requests to validate the check itself).

Everything fetched from the web is untrusted: values are matched against
strict patterns before they are printed or compared.
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / ".github" / "standards-baseline.json"

CIS_URL = "https://www.cisecurity.org/benchmark/docker"
OWASP_PAGE = "https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html"
OWASP_REPO = "OWASP/CheatSheetSeries"
OWASP_FILE = "cheatsheets/Docker_Security_Cheat_Sheet.md"

CIS_VERSION_RE = re.compile(r"Docker[ _]Benchmark[ _]\(?v?(\d+\.\d+\.\d+)")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ANCHOR_RE = re.compile(r"^[a-z0-9-]+$")
CITED_ANCHOR_RE = re.compile(r"Docker_Security_Cheat_Sheet\.html#([A-Za-z0-9-]+)")
PAGE_ID_RE = re.compile(r"""\bid=["']?([a-z0-9-]+)""")


class CheckError(Exception):
    """The check itself could not run (exit code 2)."""


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (standards-watch)"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except OSError as error:
        raise CheckError(f"could not fetch {url}: {error}") from error


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def latest_cis_version():
    versions = set(CIS_VERSION_RE.findall(fetch(CIS_URL)))
    if not versions:
        raise CheckError(f"no 'Docker Benchmark vX.Y.Z' found on {CIS_URL} - did the page change?")
    return max(versions, key=version_key)


def latest_owasp_commit():
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{OWASP_REPO}/commits?path={OWASP_FILE}&per_page=1",
             "--jq", ".[0] | [.sha, .commit.committer.date, (.commit.message | split(\"\\n\")[0])] | @tsv"],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise CheckError(f"could not run 'gh api' for the OWASP commit history: {error}") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise CheckError(f"could not read OWASP commit history: {result.stderr.strip()[:200]}")
    parts = result.stdout.rstrip("\n").split("\t", 2)
    if len(parts) != 3 or not SHA_RE.match(parts[0]):
        raise CheckError("unexpected output from the GitHub commits API")
    sha, date, message = parts
    message = "".join(ch for ch in message if ch.isprintable())[:120].replace("`", "'")
    return sha, date[:10], message


def broken_owasp_anchors():
    cited = set()
    for path in ROOT.glob("*.md"):
        cited.update(CITED_ANCHOR_RE.findall(path.read_text(encoding="utf-8")))
    cited = {anchor for anchor in cited if ANCHOR_RE.match(anchor)}
    page_ids = set(PAGE_ID_RE.findall(fetch(OWASP_PAGE)))
    if not any(anchor.startswith("rule-") for anchor in page_ids):
        raise CheckError(f"no rule anchors found on {OWASP_PAGE} - did the page change?")
    return sorted(cited - page_ids), sorted(cited)


def load_baseline():
    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cis = baseline["cis_docker_benchmark"]["verified_version"]
        owasp = baseline["owasp_docker_cheat_sheet"]["reviewed_commit"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CheckError(f"baseline file {BASELINE.relative_to(ROOT)} is missing or malformed: {error!r}") from error
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(cis)) or not SHA_RE.match(str(owasp)):
        raise CheckError(f"baseline file {BASELINE.relative_to(ROOT)} has an invalid version or commit")
    return cis, owasp


def main():
    report_only = "--report-only" in sys.argv[1:]
    cis_verified, owasp_reviewed = load_baseline()

    cis_latest = latest_cis_version()
    sha, date, message = latest_owasp_commit()
    broken, cited = broken_owasp_anchors()

    problems = []
    if version_key(cis_latest) > version_key(cis_verified):
        problems.append(
            f"CIS Docker Benchmark: newest is v{cis_latest}, this repo was checked against v{cis_verified}.\n"
            f"  Re-check the control numbers cited in README.md and the Dockerfile, then set "
            f"cis_docker_benchmark.verified_version in {BASELINE.relative_to(ROOT)}."
        )
    if sha != owasp_reviewed:
        problems.append(
            f"OWASP Docker Security Cheat Sheet changed: latest commit {sha[:9]} ({date}): {message}\n"
            f"  Review https://github.com/{OWASP_REPO}/commits/master/{OWASP_FILE}, then set "
            f"owasp_docker_cheat_sheet.reviewed_commit in {BASELINE.relative_to(ROOT)}."
        )
    if broken:
        problems.append(
            "OWASP anchors cited in the docs no longer exist on the live page: "
            + ", ".join(broken)
        )

    lines = [
        f"CIS Docker Benchmark : newest v{cis_latest}, verified v{cis_verified}",
        f"OWASP cheat sheet    : latest {sha[:9]} ({date}), reviewed {owasp_reviewed[:9]}",
        f"OWASP anchors        : {len(cited)} cited, {len(broken)} broken",
    ]
    print("\n".join(lines))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("### Standards watch\n\n```\n" + "\n".join(lines) + "\n```\n")
            if problems:
                handle.write("\n**Outdated:**\n\n" + "\n".join(f"- {p}" for p in problems) + "\n")

    if problems:
        print("\nOUTDATED:\n" + "\n".join(f"- {p}" for p in problems), file=sys.stderr)
        return 0 if report_only else 1
    print("\nUp to date.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckError as error:
        print(f"CHECK FAILED: {error}", file=sys.stderr)
        sys.exit(2)
    except Exception as error:  # safety net: a crash must never look like "outdated" (exit 1)
        print(f"CHECK FAILED: unexpected {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
