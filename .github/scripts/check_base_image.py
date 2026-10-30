"""Fail when the Dockerfile's pinned base image digest is out of date.

The Dockerfile pins its base image as tag@digest. Pinning makes builds
reproducible, but it also freezes the base: when the tag is republished with
security patches, the pin keeps building the old image. This check compares the
pinned digest with what the tag points to today.

Exit codes: 0 = pin is current, 1 = tag has moved (prints the new digest),
2 = could not check (Dockerfile not parseable, registry/network error, ...).
Either non-zero code fails the workflow, and GitHub emails the failed run.
"""

import re
import subprocess
import sys
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ARG_RE = re.compile(r"^ARG\s+([A-Z_]+)=(\S+)\s*$", re.MULTILINE)
FROM_RE = re.compile(
    r"^FROM\s+(\S+?)@(sha256:[0-9a-f]{64})\s+AS\s+base\s*$", re.MULTILINE
)


class CheckError(Exception):
    """The check itself could not run (exit code 2)."""


def pinned_reference():
    try:
        text = DOCKERFILE.read_text(encoding="utf-8")
    except OSError as error:
        raise CheckError(f"cannot read {DOCKERFILE}: {error}") from error
    match = FROM_RE.search(text)
    if not match:
        raise CheckError(
            "no 'FROM <image>@sha256:<digest> AS base' line found in the Dockerfile"
        )
    image, digest = match.groups()
    args = dict(ARG_RE.findall(text))
    # Substitute ${NAME} with the ARG default; anything left over is unresolvable.
    image = re.sub(
        r"\$\{([A-Z_]+)\}", lambda m: args.get(m.group(1), m.group(0)), image
    )
    if "${" in image or not re.fullmatch(r"[a-z0-9./_-]+:[A-Za-z0-9._-]+", image):
        raise CheckError(f"cannot resolve the base image reference: {image!r}")
    return image, digest


def current_digest(image):
    try:
        result = subprocess.run(
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                image,
                "--format",
                "{{.Manifest.Digest}}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        raise CheckError(f"could not run docker buildx: {error}") from error
    digest = result.stdout.strip()
    if result.returncode != 0 or not DIGEST_RE.match(digest):
        raise CheckError(
            f"could not read the digest of {image}: {result.stderr.strip()[:200]}"
        )
    return digest


def main():
    image, pinned = pinned_reference()
    current = current_digest(image)
    print(f"base image : {image}")
    print(f"pinned     : {pinned}")
    print(f"tag now at : {current}")
    if pinned == current:
        print("\nThe pinned digest is current.")
        return 0
    print(
        f"\nOUTDATED: {image} has been republished since the digest was pinned.\n"
        f"  Update the digest in the Dockerfile FROM line to {current},\n"
        "  rebuild, and run the tests. (This is how base-image security patches arrive.)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckError as error:
        print(f"CHECK FAILED: {error}", file=sys.stderr)
        sys.exit(2)
    except Exception as error:  # noqa: BLE001 - safety net: a crash must never look like "outdated" (exit 1)
        print(
            f"CHECK FAILED: unexpected {type(error).__name__}: {error}", file=sys.stderr
        )
        sys.exit(2)
