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
import json
import re
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OSV_API = "https://api.osv.dev/v1"
BATCH_SIZE = 1000
TIMEOUT = 60
RETRIES = 3

EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOTHING = 3

OS_RELEASE_PATHS = ("etc/os-release", "usr/lib/os-release")
APK_DB_PATHS = ("lib/apk/db/installed", "usr/lib/apk/db/installed")
DPKG_STATUS = "var/lib/dpkg/status"
DPKG_STATUS_D = re.compile(r"^var/lib/dpkg/status\.d/[^/]+$")
DIST_INFO = re.compile(r"(?:^|/)(?:site|dist)-packages/(?:.+/)?[^/]+\.dist-info/METADATA$")
PIP_VENDOR = re.compile(r"(?:^|/)(?:site|dist)-packages/pip/_vendor/vendor\.txt$")
NPM_PACKAGE = re.compile(r"(?:^|/)node_modules/((?:@[^/]+/)?[^/@]+)/package\.json$")
RELEASE = re.compile(r"^(\d+)\.(\d+)(?:\.\d+)?$")
# The image is untrusted and an agent reads this script's output, so a package name or
# version from its files is used only if it looks like one: no spaces, pipes, quotes or
# newlines that could break the table or carry instructions.
# (a leading dot is apk's virtual package, `.python-rundeps`)
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9@.][A-Za-z0-9._+~:@/-]{0,127}$")
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
    release = RELEASE.match(version)
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
    language = set()
    dpkg_status_d = []
    for member in archive:
        path = re.sub(r"^(?:\./|/)+", "", member.name)
        if not member.isfile():
            continue
        wanted = (
            path in OS_RELEASE_PATHS
            or path in APK_DB_PATHS
            or path == DPKG_STATUS
            or (DPKG_STATUS_D.match(path) and not path.endswith(".md5sums"))
            or DIST_INFO.search(path)
            or PIP_VENDOR.search(path)
            or NPM_PACKAGE.search(path)
        )
        if not wanted:
            continue
        text = archive.extractfile(member).read().decode("utf-8", "replace")
        if path in OS_RELEASE_PATHS:
            os_release[path] = text
        elif path in APK_DB_PATHS:
            inventory.package_database = path
            inventory.os_packages.extend(parse_apk_installed(text))
        elif path == DPKG_STATUS:
            inventory.package_database = path
            inventory.os_packages.extend(parse_dpkg_status(text))
        elif DPKG_STATUS_D.match(path):
            inventory.package_database = "var/lib/dpkg/status.d"
            dpkg_status_d.extend(parse_dpkg_status(text, require_status=False))
        elif DIST_INFO.search(path):
            package = parse_metadata(text)
            if package:
                language.add(("PyPI",) + package)
        elif PIP_VENDOR.search(path):
            language.update(("PyPI",) + package for package in parse_pip_vendor(text))
        else:
            try:
                manifest = json.loads(text)
            except ValueError:
                continue
            name, version = manifest.get("name"), manifest.get("version")
            if (
                isinstance(name, str)
                and isinstance(version, str)
                and name == NPM_PACKAGE.search(path).group(1)
            ):
                language.add(("npm", name, version))
    inventory.os_packages.extend(dpkg_status_d)
    safe_os = [p for p in inventory.os_packages if all(SAFE_TOKEN.match(t) for t in p)]
    safe_language = {p for p in language if all(SAFE_TOKEN.match(t) for t in p[1:])}
    inventory.skipped = len(inventory.os_packages) - len(safe_os) + len(language - safe_language)
    inventory.os_packages = safe_os
    for path in OS_RELEASE_PATHS:
        if path in os_release:
            inventory.os_release = {
                key: clean(value) for key, value in parse_os_release(os_release[path]).items()
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
                {"package": {"name": source, "ecosystem": inventory.ecosystem}, "version": version}
            )
    for ecosystem, name, version in inventory.language_packages:
        queries.append({"package": {"name": name, "ecosystem": ecosystem}, "version": version})
    return queries


def query_osv(queries, post):
    """Advisory ids for each query, in query order, following OSV's pagination."""
    hits = [[] for _ in queries]
    for start in range(0, len(queries), BATCH_SIZE):
        pending = {index: None for index in range(start, min(start + BATCH_SIZE, len(queries)))}
        while pending:
            order = list(pending)
            body = {"queries": []}
            for index in order:
                query = dict(queries[index])
                if pending[index]:
                    query["page_token"] = pending[index]
                body["queries"].append(query)
            results = post(body).get("results", [])
            if len(results) != len(order):
                raise CheckError("OSV.dev returned a different number of results than queries")
            pending = {}
            for index, result in zip(order, results):
                for vuln in result.get("vulns") or []:
                    if vuln["id"] not in hits[index]:
                        hits[index].append(vuln["id"])
                if result.get("next_page_token"):
                    pending[index] = result["next_page_token"]
    return hits


def fixed_versions(record, ecosystem, name):
    fixed = []
    for affected in record.get("affected", []):
        package = affected.get("package", {})
        if package.get("ecosystem") != ecosystem or package.get("name") != name:
            continue
        for affected_range in affected.get("ranges", []):
            # a GIT range's events are commits, not versions
            if affected_range.get("type") == "GIT":
                continue
            for event in affected_range.get("events", []):
                if "fixed" in event and event["fixed"] not in fixed:
                    fixed.append(event["fixed"])
    return fixed


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
        if affected.get("package", {}).get("ecosystem") == ecosystem
        and affected.get("package", {}).get("name") == name
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


def not_covered(inventory):
    gaps = []
    distro = inventory.os_release.get("ID")
    if not inventory.os_release:
        gaps.append("OS packages: the image has no os-release file, so its distribution is unknown.")
    elif not inventory.ecosystem:
        gaps.append(
            f"OS packages: {distro} {inventory.os_release.get('VERSION_ID', '')} is not a "
            "release this script can look up (Alpine, Debian and Ubuntu releases only)."
        )
    elif not inventory.os_packages:
        gaps.append(f"OS packages: no package database found for {distro}.")
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
    for query, ids in zip(queries, hits):
        name, ecosystem = query["package"]["name"], query["package"]["ecosystem"]
        seen = set()
        for vuln_id in ids:
            record = records.get(vuln_id, {"id": vuln_id})
            # the same vulnerability can come back under several ids that alias each
            # other (GHSA-... and PYSEC-...); keep the first
            names = {vuln_id} | set(aliases(record))
            if names & seen:
                seen |= names
                continue
            seen |= names
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
                    "fixed": [clean(version) for version in fixed_versions(record, ecosystem, name)],
                    "severity": clean(severity(record, ecosystem, name), 200),
                }
            )
    # what a newer base or package version can fix comes first
    findings.sort(key=lambda finding: not finding["fixed"])
    with_fix = sum(1 for finding in findings if finding["fixed"])
    return {
        "image": image,
        "platform": platform,
        "source": "OSV.dev (https://api.osv.dev)",
        "queried_at": queried_at,
        "os": inventory.os_release.get("PRETTY_NAME") or inventory.os_release.get("ID"),
        "ecosystem": inventory.ecosystem,
        "package_database": inventory.package_database,
        "os_packages": len(inventory.os_packages) if inventory.ecosystem else 0,
        "language_packages": len(inventory.language_packages),
        "with_fix": with_fix,
        "without_fix": len(findings) - with_fix,
        "findings": findings,
        "not_covered": not_covered(inventory),
    }


def render_markdown(report):
    lines = [
        f"Known vulnerabilities in {report['image']} ({report['platform']})",
        "",
        f"- Source: {report['source']}, queried {report['queried_at']}",
        f"- OS: {report['os'] or 'unknown'}"
        + (f" (OSV ecosystem {report['ecosystem']})" if report["ecosystem"] else ""),
        f"- Packages looked up: {report['os_packages']} OS, "
        f"{report['language_packages']} Python and npm",
        "",
    ]
    if report["findings"]:
        lines += [
            f"{len(report['findings'])} vulnerabilities: {report['with_fix']} with a fix "
            f"listed, {report['without_fix']} without.",
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
            lines.append(
                f"| {package} | {finding['version']} | {finding['id']} | "
                f"{', '.join(finding['aliases']) or '-'} | "
                f"{', '.join(finding['fixed']) or 'no fix listed'} | {finding['severity']} |"
            )
    else:
        lines.append("No known vulnerabilities were found in the packages looked up.")
    lines += ["", "Not covered:"] + [f"- {gap}" for gap in report["not_covered"]]
    return "\n".join(lines)


def osv_post(body):
    return _request(f"{OSV_API}/querybatch", json.dumps(body).encode("utf-8"))


def osv_get(vuln_id):
    return _request(f"{OSV_API}/vulns/{urllib.parse.quote(vuln_id)}", None)


def _request(url, data, urlopen=urllib.request.urlopen, sleep=time.sleep):
    """JSON from OSV.dev, retrying a rate limit (429), a server error (5xx) or a network
    error a few times."""
    for attempt in range(RETRIES + 1):
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "dockerfile-wizardry"},
        )
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            failure = error
            if error.code != 429 and error.code < 500:
                break
        except (urllib.error.URLError, OSError) as error:
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
        self.process = subprocess.Popen(
            ["docker", "export", self.container], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return self.process.stdout

    def __exit__(self, kind, value, traceback):
        try:
            # read what tarfile left (end-of-archive padding) so export exits cleanly
            while self.process.stdout.read(65536):
                pass
            self.process.stdout.close()
            error = self.process.stderr.read().decode("utf-8", "replace").strip()
            if self.process.wait() != 0 and kind is None:
                raise CheckError(f"docker export failed: {error[:300]}")
        finally:
            _docker(["rm", "-v", self.container])
        return False


def _docker(arguments):
    try:
        result = subprocess.run(
            ["docker"] + arguments, capture_output=True, text=True, timeout=600, check=False
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise CheckError(f"could not run docker {arguments[0]}: {error}") from error
    if result.returncode != 0:
        raise CheckError(f"docker {arguments[0]} failed: {result.stderr.strip()[:300]}")
    return result.stdout


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
        with export(args.image, args.platform) as stream:
            with tarfile.open(fileobj=stream, mode="r|") as archive:
                inventory = read_inventory(archive)
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
        records = {}
        for ids in hits:
            for vuln_id in ids:
                if vuln_id not in records:
                    records[vuln_id] = get(vuln_id)
    except (CheckError, tarfile.TarError) as error:
        print(f"Could not check {args.image}: {error}", file=sys.stderr)
        return EXIT_ERROR
    report = make_report(args.image, args.platform, inventory, queries, hits, records, queried_at)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
