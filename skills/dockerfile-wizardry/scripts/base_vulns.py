"""List known vulnerabilities in an image's packages, from OSV.dev, without a scanner.

Usage: python3 base_vulns.py <image>[:<tag>][@<digest>] [--platform linux/amd64]
                            [--format markdown|json]

The image is never run: `docker create` and `docker export` stream its filesystem, from
which this reads the OS package database (apk on Alpine, dpkg on Debian and Ubuntu,
including distroless `status.d`) and the Python (`*.dist-info`, pip's vendored packages)
and npm (`node_modules/*/package.json`) packages. It asks OSV.dev for each package by
ecosystem, name and version, OS packages under their source package (`openssl`, not
`libssl3`), as the OSV schema requires, then fetches each advisory it gets back for the
fixed version and severity. The report names its source and the query time, and lists
what it could not see; an empty result is not a clean bill of health.

Needs the docker CLI and network access to the registry and to api.osv.dev. Standard
library only.

Exit codes: 0 = report printed (with or without vulnerabilities), 1 = could not check
(docker or network error), 2 = bad arguments, 3 = found no package it could look up,
so nothing was checked.
"""

import argparse
import http.client
import json
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

OSV_API = "https://api.osv.dev/v1"
BATCH_SIZE = 1000
TIMEOUT = 60
RETRIES = 3
FETCH_WORKERS = 8
# a package database or metadata file larger than this is not read (a large Debian
# dpkg status file is a few MB)
MAX_FILE_BYTES = 64 * 1024 * 1024

EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOTHING = 3

OS_RELEASE_PATHS = ("etc/os-release", "usr/lib/os-release")
APK_DB_PATHS = ("lib/apk/db/installed", "usr/lib/apk/db/installed")
DPKG_STATUS = "var/lib/dpkg/status"
DPKG_STATUS_D = re.compile(r"var/lib/dpkg/status\.d/[^/]+")
DIST_INFO = re.compile(
    r"(?:^|/)(?:site|dist)-packages/(?:.+/)?[^/]+\.dist-info/METADATA$"
)
PIP_VENDOR = re.compile(r"(?:^|/)(?:site|dist)-packages/pip/_vendor/vendor\.txt$")
NPM_PACKAGE = re.compile(r"(?:^|/)node_modules/((?:@[^/]+/)?[^/@]+)/package\.json$")
RELEASE = re.compile(r"(\d+)\.(\d+)(?:\.\d+)?")
# The image is untrusted and an agent reads this script's output, so a package name or
# version from its files is used only if it looks like one: no spaces, pipes, quotes or
# newlines that could break the table or carry instructions.
# (a leading dot is apk's virtual package, `.python-rundeps`)
# (used with fullmatch: `$` would also accept a trailing newline)
SAFE_TOKEN = re.compile(r"[A-Za-z0-9@.][A-Za-z0-9._+~:@/-]{0,127}")
UNSAFE_TEXT = re.compile(r"[^A-Za-z0-9._+~:@/ ()-]")


def clean(text, limit=80):
    """Free text from the image or an advisory, with anything but plain characters
    removed and cut to `limit`."""
    return UNSAFE_TEXT.sub("", str(text))[:limit].strip()


class CheckError(Exception):
    """The check could not run (exit code 1)."""


class Inventory:
    """What an image's filesystem says is installed."""

    def __init__(self):
        self.os_release = {}
        self.ecosystem = None
        # (source package, version, binary package)
        self.os_packages = []
        self.package_database = None
        # (ecosystem, name, version)
        self.language_packages = []
        # package entries left out because a name or version had unexpected characters
        self.skipped = 0
        # Python and npm packages the OS package manager installed: its own advisories
        # cover them (with any backported fix), so they are not looked up again
        self.os_owned = 0
        # package files left unread because they were larger than MAX_FILE_BYTES
        self.oversized = 0


def parse_os_release(text):
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.startswith("#"):
            fields[key.strip()] = value.strip().strip("\"'")
    return fields


def os_ecosystem(os_release):
    """The OSV ecosystem for the image's distribution release, or None if this script
    cannot query it."""
    distro = os_release.get("ID", "")
    version = os_release.get("VERSION_ID", "")
    release = RELEASE.fullmatch(version)
    if distro == "alpine" and release:
        return f"Alpine:v{release.group(1)}.{release.group(2)}"
    if distro == "debian" and re.fullmatch(r"\d+", version):
        return f"Debian:{version}"
    if distro == "ubuntu" and release:
        lts = ":LTS" if "LTS" in os_release.get("VERSION", "") else ""
        return f"Ubuntu:{version}{lts}"
    return None


def paragraphs(text):
    """Blank-line separated records of `Key: value` lines (apk and dpkg databases)."""
    record = []
    for line in text.splitlines() + [""]:
        if line.strip():
            record.append(line)
        elif record:
            yield record
            record = []


def parse_apk_installed(text):
    packages = []
    for record in paragraphs(text):
        fields = {}
        for line in record:
            if len(line) > 1 and line[1] == ":":
                fields.setdefault(line[0], line[2:])
        if "P" in fields and "V" in fields:
            packages.append((fields.get("o") or fields["P"], fields["V"], fields["P"]))
    return packages


def apk_owned_files(text):
    """The paths apk installed: each `F:` directory line, then its `R:` file lines."""
    owned, directory = set(), ""
    for line in text.splitlines():
        if line.startswith("F:"):
            directory = line[2:]
        elif line.startswith("R:"):
            owned.add(f"{directory}/{line[2:]}" if directory else line[2:])
    return owned


def parse_dpkg_status(text, require_status=True):
    packages = []
    for record in paragraphs(text):
        fields = {}
        for line in record:
            if not line.startswith((" ", "\t")):
                key, sep, value = line.partition(":")
                if sep:
                    fields[key.strip()] = value.strip()
        if "Package" not in fields or "Version" not in fields:
            continue
        status = fields.get("Status", "")
        if (require_status or status) and not status.endswith(" installed"):
            continue
        source, version = fields["Package"], fields["Version"]
        if fields.get("Source"):
            name, _, rest = fields["Source"].partition(" ")
            source = name
            # "Source: zlib (1:1.2.13.dfsg-1)" gives the source version, which differs
            # from the binary one after a binary-only rebuild (+b2)
            if rest.startswith("(") and rest.endswith(")"):
                version = rest[1:-1]
        packages.append((source, version, fields["Package"]))
    return packages


def normalize_pypi(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_metadata(text):
    """(name, version) from a Python METADATA file's headers."""
    fields = {}
    for line in text.splitlines():
        if not line.strip():
            break
        key, sep, value = line.partition(":")
        if sep:
            fields.setdefault(key.strip(), value.strip())
    if fields.get("Name") and fields.get("Version"):
        return normalize_pypi(fields["Name"]), fields["Version"]
    return None


def parse_pip_vendor(text):
    packages = []
    for line in text.splitlines():
        requirement = line.split("#", 1)[0].strip()
        name, sep, version = requirement.partition("==")
        if sep and name.strip() and version.strip():
            packages.append((normalize_pypi(name.strip()), version.strip()))
    return packages


def read_inventory(archive):
    """Read an Inventory from an open tarfile of the image's filesystem, in one pass."""
    inventory = Inventory()
    os_release = {}
    # (path the package was read from, (ecosystem, name, version))
    language = []
    owned = set()
    dpkg_status_d = []
    for member in archive:
        path = re.sub(r"^(?:\./|/)+", "", member.name)
        if not member.isfile():
            continue
        wanted = (
            path in OS_RELEASE_PATHS
            or path in APK_DB_PATHS
            or path == DPKG_STATUS
            or (DPKG_STATUS_D.fullmatch(path) and not path.endswith(".md5sums"))
            or DIST_INFO.search(path)
            or PIP_VENDOR.search(path)
            or NPM_PACKAGE.search(path)
        )
        if not wanted:
            continue
        # the image is untrusted: a file this large is no package metadata
        if member.size > MAX_FILE_BYTES:
            inventory.oversized += 1
            continue
        text = archive.extractfile(member).read().decode("utf-8", "replace")
        if path in OS_RELEASE_PATHS:
            os_release[path] = text
        elif path in APK_DB_PATHS:
            inventory.package_database = path
            inventory.os_packages.extend(parse_apk_installed(text))
            owned |= apk_owned_files(text)
        elif path == DPKG_STATUS:
            inventory.package_database = path
            inventory.os_packages.extend(parse_dpkg_status(text))
        elif DPKG_STATUS_D.fullmatch(path):
            inventory.package_database = "var/lib/dpkg/status.d"
            dpkg_status_d.extend(parse_dpkg_status(text, require_status=False))
        elif DIST_INFO.search(path):
            package = parse_metadata(text)
            if package:
                language.append((path, ("PyPI",) + package))
        elif PIP_VENDOR.search(path):
            language += [(path, ("PyPI",) + p) for p in parse_pip_vendor(text)]
        else:
            try:
                manifest = json.loads(text)
            except (ValueError, RecursionError):
                continue
            if not isinstance(manifest, dict):
                continue
            name, version = manifest.get("name"), manifest.get("version")
            if (
                isinstance(name, str)
                and isinstance(version, str)
                and name == NPM_PACKAGE.search(path).group(1)
            ):
                language.append((path, ("npm", name, version)))
    inventory.os_packages.extend(dpkg_status_d)
    # Debian and Ubuntu keep dist-packages under /usr/lib/python3 for their own
    # packages (pip installs under /usr/local); apk lists the files it installed.
    # Decided per file, so another copy of the same version is still looked up.
    found, by_os = set(), set()
    for path, package in language:
        if path in owned or path.startswith("usr/lib/python3/dist-packages/"):
            by_os.add(path)
        else:
            found.add(package)
    inventory.os_owned = len(by_os)
    safe_os = [
        p for p in inventory.os_packages if all(SAFE_TOKEN.fullmatch(t) for t in p)
    ]
    safe_language = {p for p in found if all(SAFE_TOKEN.fullmatch(t) for t in p[1:])}
    inventory.skipped = (
        len(inventory.os_packages) - len(safe_os) + len(found - safe_language)
    )
    inventory.os_packages = safe_os
    for path in OS_RELEASE_PATHS:
        if path in os_release:
            inventory.os_release = {
                key: clean(value)
                for key, value in parse_os_release(os_release[path]).items()
            }
            break
    inventory.ecosystem = os_ecosystem(inventory.os_release)
    inventory.language_packages = sorted(safe_language)
    return inventory


def build_queries(inventory):
    """One OSV query per (ecosystem, package, version)."""
    queries = []
    if inventory.ecosystem:
        for source, version in sorted({(s, v) for s, v, _ in inventory.os_packages}):
            queries.append(
                {
                    "package": {"name": source, "ecosystem": inventory.ecosystem},
                    "version": version,
                }
            )
    for ecosystem, name, version in inventory.language_packages:
        queries.append(
            {"package": {"name": name, "ecosystem": ecosystem}, "version": version}
        )
    return queries


def query_osv(queries, post):
    """Advisory ids for each query, in query order, following OSV's pagination."""
    hits = [[] for _ in queries]
    for start in range(0, len(queries), BATCH_SIZE):
        pending = {
            index: None for index in range(start, min(start + BATCH_SIZE, len(queries)))
        }
        while pending:
            order = list(pending)
            body = {"queries": []}
            for index in order:
                query = dict(queries[index])
                if pending[index]:
                    query["page_token"] = pending[index]
                body["queries"].append(query)
            response = post(body)
            results = response.get("results") if isinstance(response, dict) else None
            if not isinstance(results, list) or len(results) != len(order):
                raise CheckError(
                    "OSV.dev returned a response that does not match the queries"
                )
            pending = {}
            for index, result in zip(order, results):
                vulns = (
                    (result.get("vulns") or []) if isinstance(result, dict) else None
                )
                if not isinstance(vulns, list) or not all(
                    isinstance(vuln, dict)
                    and isinstance(vuln.get("id"), str)
                    and SAFE_TOKEN.fullmatch(vuln["id"])
                    for vuln in vulns
                ):
                    raise CheckError(
                        "OSV.dev returned a result without valid advisory ids"
                    )
                for vuln in vulns:
                    if vuln["id"] not in hits[index]:
                        hits[index].append(vuln["id"])
                if result.get("next_page_token"):
                    pending[index] = result["next_page_token"]
    return hits


# pre-release markers sort before the release they lead to (apk `_rc1`, semver `-rc.1`)
PRE_RELEASE = {"dev": 0, "alpha": 1, "beta": 2, "pre": 3, "rc": 4}
# PEP 440 also spells them a, b and c (2.0b1); elsewhere a trailing letter is later
PYPI_PRE_RELEASE = dict(PRE_RELEASE, a=1, b=2, c=4, preview=4)


def _version_parts(text, pre_release):
    parts = []
    for token in re.findall(r"\d+|[A-Za-z]+|~", text):
        if token == "~":
            parts.append((-2, 0, ""))
        elif token.isdigit():
            parts.append((2, int(token), ""))
        elif token.lower() in pre_release:
            parts.append((-1, pre_release[token.lower()], ""))
        else:
            parts.append((1, 0, token))
    parts.append((0, 0, ""))
    return parts


def version_key(version, ecosystem=None):
    """A sort key good enough to tell which range of an advisory holds a version:
    the epoch, then the version, then the revision after the last `-` (Debian's
    `-1~deb12u2`, apk's `-r0`). Numbers and letters compare in turn; Debian's `~`
    and pre-release markers come before the end."""
    pre_release = PYPI_PRE_RELEASE if ecosystem == "PyPI" else PRE_RELEASE
    epoch, sep, rest = version.partition(":")
    if not (sep and epoch.isdigit()):
        epoch, rest = "0", version
    upstream, _, revision = rest.rpartition("-")
    if not upstream:
        upstream, revision = rest, ""
    return (
        int(epoch),
        _version_parts(upstream, pre_release),
        _version_parts(revision, pre_release),
    )


def _range_status(events, installed, ecosystem):
    """("fixed", version) if `installed` falls in a part of the range that a later
    version fixes, ("unfixed", None) if it falls in a part with no fix, else
    ("outside", None). Events come in version order, as OSV lists them."""
    key = version_key(installed, ecosystem)
    affected = False
    for event in events:
        if "introduced" in event:
            if (
                event["introduced"] != "0"
                and version_key(event["introduced"], ecosystem) > key
            ):
                break
            affected = True
        elif "fixed" in event:
            if version_key(event["fixed"], ecosystem) > key:
                return ("fixed", event["fixed"]) if affected else ("outside", None)
            affected = False
        elif "last_affected" in event:
            if version_key(event["last_affected"], ecosystem) >= key:
                return ("unfixed", None) if affected else ("outside", None)
            affected = False
    return ("unfixed", None) if affected else ("outside", None)


def same_package(package, ecosystem, name):
    if package.get("ecosystem") != ecosystem:
        return False
    # advisories may spell a PyPI name as published (PyYAML); the query normalized it
    if ecosystem == "PyPI":
        return normalize_pypi(package.get("name", "")) == name
    return package.get("name") == name


def fixed_versions(record, ecosystem, name, installed):
    """The versions that fix this advisory for the installed version: from the range
    that holds it, so a fix on another release line does not count."""
    fixed, other, unfixed = [], [], False
    for affected in record.get("affected", []):
        if not same_package(affected.get("package", {}), ecosystem, name):
            continue
        for affected_range in affected.get("ranges", []):
            # a GIT range's events are commits, not versions
            if affected_range.get("type") == "GIT":
                continue
            events = affected_range.get("events", [])
            status, version = _range_status(events, installed, ecosystem)
            if status == "fixed" and version not in fixed:
                fixed.append(version)
            unfixed = unfixed or status == "unfixed"
            other += [
                event["fixed"]
                for event in events
                if "fixed" in event
                and version_key(event["fixed"], ecosystem)
                > version_key(installed, ecosystem)
            ]
    if fixed or unfixed:
        return fixed
    # OSV says the version is affected but no range seemed to hold it: the ordering
    # here is approximate, so fall back to the fixes above the installed version
    return list(dict.fromkeys(other))


def aliases(record):
    names = []
    for name in record.get("aliases", []) + record.get("upstream", []):
        if name != record.get("id") and name not in names:
            names.append(name)
    return names


def severity(record, ecosystem, name):
    """The severity as the source gives it for this package and release: Debian's
    urgency or another label if there is one, else a CVSS vector."""
    entries = [
        affected
        for affected in record.get("affected", [])
        if same_package(affected.get("package", {}), ecosystem, name)
    ]
    for affected in entries:
        specific = affected.get("ecosystem_specific") or {}
        if isinstance(specific.get("urgency"), str) and specific["urgency"]:
            return f"Debian urgency: {specific['urgency']}"
        if isinstance(specific.get("severity"), str) and specific["severity"]:
            return specific["severity"]
    label = (record.get("database_specific") or {}).get("severity")
    if isinstance(label, str) and label:
        return label
    for entry in record.get("severity", []) + [
        s for affected in entries for s in affected.get("severity", [])
    ]:
        if entry.get("score"):
            return entry["score"]
    return "not given"


def os_name(os_release):
    """`<ID> <VERSION_ID>` as strict tokens, or None. The free-text fields
    (PRETTY_NAME, NAME) come from the untrusted image and are never shown."""
    parts = [
        os_release[key]
        for key in ("ID", "VERSION_ID")
        if os_release.get(key) and SAFE_TOKEN.fullmatch(os_release[key])
    ]
    return " ".join(parts) or None


def not_covered(inventory, missing=0):
    gaps = []
    distro = inventory.os_release.get("ID")
    name = os_name(inventory.os_release) or "an unrecognised distribution"
    if not inventory.os_release:
        gaps.append(
            "OS packages: the image has no os-release file, so its distribution is unknown."
        )
    elif not inventory.ecosystem:
        gaps.append(
            f"OS packages: {name} is not a release this script can look up (Alpine, "
            "Debian and Ubuntu releases only)."
        )
    elif not inventory.package_database:
        gaps.append(f"OS packages: no package database found for {name}.")
    if inventory.oversized:
        gaps.append(
            f"{inventory.oversized} package files were too large to read and were "
            "skipped; look at them by hand."
        )
    if inventory.os_owned:
        gaps.append(
            f"{inventory.os_owned} Python or npm packages that the OS package manager "
            "installed are left to its own advisories (the OS lookup above), which know "
            "its backported fixes, and are not looked up again on PyPI or npm."
        )
    if missing:
        gaps.append(
            f"{missing} advisories OSV.dev returned could not be fetched, so their fix "
            "and severity are unknown."
        )
    if inventory.skipped:
        gaps.append(
            f"{inventory.skipped} package entries were skipped because a name or version "
            "had characters a package name does not use; look at the image's package "
            "database by hand."
        )
    if distro == "alpine" and inventory.ecosystem:
        gaps.append(
            "Alpine's security database lists a vulnerability only once a fix exists in "
            f"that release branch, so one without a fix in {inventory.ecosystem} is not "
            "shown. `docker scout cves` reports those too, or check the image's page on "
            "Docker Hub."
        )
    gaps.append(
        "Software installed without a package manager is not checked: the Python or "
        "Node.js runtime that official images build from source, or a binary a RUN step "
        "downloads."
    )
    gaps.append(
        "Language packages other than Python (dist-info, pip's vendored packages) and npm "
        "are not read."
    )
    gaps.append(
        "An advisory OSV.dev does not hold, or publishes after the query time, is not shown."
    )
    return gaps


def make_report(image, platform, inventory, queries, hits, records, queried_at):
    binaries = {}
    for source, version, binary in inventory.os_packages:
        binaries.setdefault((source, version), [])
        if binary not in binaries[(source, version)]:
            binaries[(source, version)].append(binary)
    findings = []
    missing = set()
    for query, ids in zip(queries, hits):
        name, ecosystem = query["package"]["name"], query["package"]["ecosystem"]
        kept_ids, kept_aliases = set(), set()
        returned = set(ids)
        for vuln_id in ids:
            record = records.get(vuln_id)
            if record is None:
                missing.add(vuln_id)
                record = {"id": vuln_id}
            # the same vulnerability can come back under ids that name each other as
            # aliases (GHSA-... and PYSEC-...); keep the first. A shared CVE alone does
            # not make two records the same.
            own_aliases = set(record.get("aliases", []))
            if vuln_id in kept_aliases or own_aliases & kept_ids:
                continue
            # a Debian DSA/DLA lists in `upstream` the DEBIAN-CVE records it bundles;
            # when OSV returned all of them, they already count its vulnerabilities
            bundled = [
                name
                for name in record.get("upstream", [])
                if not name.startswith("CVE-") and name != vuln_id
            ]
            if bundled and all(name in returned for name in bundled):
                continue
            kept_ids.add(vuln_id)
            kept_aliases |= own_aliases
            findings.append(
                {
                    "package": name,
                    "ecosystem": ecosystem,
                    "binaries": sorted(binaries.get((name, query["version"]), []))
                    if ecosystem == inventory.ecosystem
                    else [],
                    "version": query["version"],
                    "id": clean(vuln_id),
                    "aliases": [clean(alias) for alias in aliases(record)],
                    # None: the advisory could not be fetched, so the fix is unknown
                    "fixed": None
                    if vuln_id in missing
                    else [
                        clean(version)
                        for version in fixed_versions(
                            record, ecosystem, name, query["version"]
                        )
                    ],
                    "severity": "not fetched"
                    if vuln_id in missing
                    else clean(severity(record, ecosystem, name), 200),
                }
            )
    # what a newer base or package version can fix comes first, unknown ones last
    findings.sort(
        key=lambda finding: 2 if finding["fixed"] is None else int(not finding["fixed"])
    )
    with_fix = sum(1 for finding in findings if finding["fixed"])
    unknown_fix = sum(1 for finding in findings if finding["fixed"] is None)
    return {
        "image": image,
        "platform": platform,
        "source": "OSV.dev (https://api.osv.dev)",
        "queried_at": queried_at,
        "os": os_name(inventory.os_release),
        "ecosystem": inventory.ecosystem,
        "package_database": inventory.package_database,
        "os_packages": len(inventory.os_packages) if inventory.ecosystem else 0,
        "language_packages": len(inventory.language_packages),
        "with_fix": with_fix,
        "without_fix": len(findings) - with_fix - unknown_fix,
        "unknown_fix": unknown_fix,
        "findings": findings,
        "not_covered": not_covered(inventory, len(missing)),
    }


def render_markdown(report):
    lines = [
        f"Known vulnerabilities in {report['image']} ({report['platform']})",
        "",
        f"- Source: {report['source']}, queried {report['queried_at']}",
        f"- OS: {report['os'] or 'unknown'}"
        + (f" (OSV ecosystem {report['ecosystem']})" if report["ecosystem"] else ""),
        (
            f"- Packages looked up: {report['os_packages']} OS, "
            f"{report['language_packages']} Python and npm"
        ),
        "",
    ]
    if report["findings"]:
        lines += [
            (
                f"{len(report['findings'])} vulnerabilities: {report['with_fix']} with "
                f"a fix listed, {report['without_fix']} without"
                + (
                    f", {report['unknown_fix']} not fetched."
                    if report["unknown_fix"]
                    else "."
                )
            ),
            "",
            "| Package | Installed | Advisory | Also known as | Fixed in | Severity |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for finding in report["findings"]:
            if finding["binaries"] and finding["binaries"] != [finding["package"]]:
                package = f"{finding['package']} ({', '.join(finding['binaries'])})"
            elif finding["ecosystem"] == report["ecosystem"]:
                package = finding["package"]
            else:
                package = f"{finding['package']} ({finding['ecosystem']})"
            if finding["fixed"] is None:
                fixed = "unknown"
            else:
                fixed = ", ".join(finding["fixed"]) or "no fix listed"
            lines.append(
                f"| {package} | {finding['version']} | {finding['id']} | "
                f"{', '.join(finding['aliases']) or '-'} | {fixed} | "
                f"{finding['severity']} |"
            )
    else:
        lines.append("No known vulnerabilities were found in the packages looked up.")
    lines += ["", "Not covered:"] + [f"- {gap}" for gap in report["not_covered"]]
    return "\n".join(lines)


def osv_post(body):
    return _request(f"{OSV_API}/querybatch", json.dumps(body).encode("utf-8"))


def osv_get(vuln_id):
    """The advisory, or None if OSV.dev no longer has it (404)."""
    record = _request(
        f"{OSV_API}/vulns/{urllib.parse.quote(vuln_id)}", None, missing_ok=True
    )
    if record is not None and not isinstance(record, dict):
        raise CheckError(
            f"OSV.dev returned an advisory for {clean(vuln_id)} that is not one"
        )
    return record


def _request(
    url, data, urlopen=urllib.request.urlopen, sleep=time.sleep, missing_ok=False
):
    """JSON from OSV.dev, retrying a rate limit (429), a server error (5xx) or a network
    error a few times. With `missing_ok`, a 404 gives None."""
    for attempt in range(RETRIES + 1):
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "dockerfile-wizardry",
            },
        )
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            failure = error
            if error.code == 404 and missing_ok:
                return None
            if error.code != 429 and error.code < 500:
                break
        # HTTPException: the connection broke mid-body (IncompleteRead and the like)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            failure = error
        except ValueError as error:
            failure = error
            break
        if attempt < RETRIES:
            sleep(2**attempt)
    raise CheckError(f"OSV.dev request to {url} failed: {failure}")


class DockerExport:
    """The image's filesystem as a tar stream, from a container that is created, never
    started, and removed afterwards."""

    def __init__(self, image, platform):
        self.image, self.platform = image, platform
        self.container, self.process = None, None

    def __enter__(self):
        created = _docker(["create", "--platform", self.platform, self.image, "x"])
        self.container = created.strip()
        try:
            self.process = subprocess.Popen(
                ["docker", "export", self.container],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as error:
            self._remove()
            raise CheckError(f"could not run docker export: {error}") from error
        return self.process.stdout

    def _remove(self):
        # a failed removal must not hide the check's own result or error: say what to
        # remove by hand instead
        try:
            _docker(["rm", "-v", self.container])
        except CheckError as error:
            print(
                f"Could not remove the container this check created ({error}); "
                f"remove it with: docker rm -v {self.container}",
                file=sys.stderr,
            )

    def __exit__(self, kind, value, traceback):
        try:
            # read what tarfile left (end-of-archive padding) so export exits cleanly
            while self.process.stdout.read(65536):
                pass
            self.process.stdout.close()
            error = self.process.stderr.read().decode("utf-8", "replace").strip()
            # a failed export is the cause of any tar error it led to, so report it
            if self.process.wait() != 0:
                raise CheckError(f"docker export failed: {error[:300]}") from value
        finally:
            self._remove()
        return False


def _docker(arguments):
    try:
        result = subprocess.run(
            ["docker"] + arguments,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise CheckError(f"could not run docker {arguments[0]}: {error}") from error
    if result.returncode != 0:
        raise CheckError(f"docker {arguments[0]} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def read_image(export, image, platform):
    with export(image, platform) as stream:  # noqa: SIM117 - one `with` needs 3.10 parentheses
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            return read_inventory(archive)


def main(argv=None, export=DockerExport, post=osv_post, get=osv_get):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", help="image reference, ideally <image>:<tag>@<digest>")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_:
        return EXIT_USAGE if exit_.code else 0
    try:
        inventory = read_image(export, args.image, args.platform)
        queries = build_queries(inventory)
        if not queries:
            print(
                f"Nothing was checked: found no package in {args.image} that OSV.dev can "
                "be asked about.",
                file=sys.stderr,
            )
            for gap in not_covered(inventory):
                print(f"- {gap}", file=sys.stderr)
            return EXIT_NOTHING
        queried_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        hits = query_osv(queries, post)
        ids = list(dict.fromkeys(vuln_id for found in hits for vuln_id in found))
        # a large Debian base returns hundreds of advisories; fetch them in parallel
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            records = dict(zip(ids, pool.map(get, ids)))
        report = make_report(
            args.image, args.platform, inventory, queries, hits, records, queried_at
        )
    except (CheckError, tarfile.TarError) as error:
        # messages can quote docker's or OSV.dev's output: print them cleaned
        print(f"Could not check {args.image}: {clean(error, 400)}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as error:  # noqa: BLE001 - safety net: the image and the advisories are untrusted input, and a crash must still read as "could not check"
        print(
            f"Could not check {args.image}: unexpected {type(error).__name__}: "
            f"{clean(error, 200)}",
            file=sys.stderr,
        )
        return EXIT_ERROR
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
