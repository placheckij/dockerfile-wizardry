# Dependencies

What goes into the image besides your code: operating-system packages and language tooling.
DW-DEPS-01 and DW-DEPS-02 are written from Spell #3 and Spell #5; DW-DEPS-03 comes from its sources
alone.

## DW-DEPS-01: Install only the packages you need, in one layer

strength: TRADE-OFF

spells:
- 3

last_verified: 2026-11-02

statement:
  Install only what the running container needs, run the package index update and the install in
  the same `RUN`, and remove package caches in that same layer, unless you keep them in a cache
  mount (DW-BUILD-05), which is not part of the layer and should not be deleted. Whether to pin
  each OS package to an exact version is a trade-off, described below.

why:
  Every extra package is attack surface and size (CIS 4.3). An index update in its own layer can be
  cached and go stale before the install runs (CIS 4.6). On pinning, sources disagree: linters such
  as Hadolint (DL3008 for apt) ask for pinned versions for reproducibility, while a pinned version
  can disappear from a repository that keeps only the current one, which in this repository's
  experience Alpine does (see the pinning trade-off). Pinning also stops automatic security fixes.
  This repository does not pin OS packages and relies on a base-image digest check and a weekly
  no-cache rebuild instead. Note that Docker still reuses a whole `RUN` layer from its cache until
  the instruction or the base digest changes, so patches only arrive when the cache is invalidated
  (`docker build --no-cache --pull`, a new digest, or an edit to the `RUN`). See the trade-offs on
  [pinning](tradeoffs.md#2-pinning-operating-system-package-versions) and
  [updating](tradeoffs.md#3-update-inside-the-image-or-rebuild-from-a-fresh-base).

how_to_check:
  Hadolint DL3008 (pin apt versions) and DL3018 (pin apk versions) check the pinning side of
  the trade-off; Dockle CIS-DI-0007 flags an update instruction used alone. Whether to pin is the
  decision described above.

sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/build/building/best-practices/#run
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-9-integrate-container-scanning-tools-into-your-cicd-pipeline

## DW-DEPS-02: Install language tooling pinned, with its cache out of the layer

strength: SHOULD

spells:
- 5

last_verified: 2026-11-02

statement:
  Keep the installer's download cache out of the layer, either by disabling it or by keeping it
  in a cache mount (DW-BUILD-05); configure the installer to use the interpreter already in the
  base image, and pin its version (this repository pins `uv`). For Python, compile
  bytecode at install time when the root filesystem will be read-only.

why:
  A cache left in a layer adds size that can never be removed, and an unpinned installer makes
  builds differ over time. The uv Docker guide shows both ways: a cache mount, and `--no-cache` or
  `UV_NO_CACHE` for when you are not mounting the cache. This repository disables the cache. If you
  mount it instead, the mount is created for `uid` 0 by default, so for a non-root build user pass
  `uid=` and `gid=` and target that user's cache directory (`uv cache dir` shows it), or the mount
  goes unused and the cache lands in the layer. With a read-only runtime filesystem Python cannot
  write its own `.pyc` files, so without install-time compilation it recompiles every module on
  every start; in this repository that measured 644 ms against 358 ms for dependency imports, for
  about 8 MB more image. Python writes hash-based `.pyc` files when `SOURCE_DATE_EPOCH` is set,
  which makes the bytecode reproducible. Turn compilation off if size matters more than start-up
  time.

how_to_check:
  manual

sources:
- https://docs.docker.com/build/building/best-practices/#run
- https://docs.astral.sh/uv/guides/integration/docker/
- https://docs.python.org/3/library/py_compile.html

## DW-DEPS-03: Verify what you download during the build

strength: SHOULD

last_verified: 2026-11-02

statement:
  When a build downloads a file or source archive directly (with `ADD`, `curl` or `wget`), fetch
  it over HTTPS and check it against an embedded checksum, and against a signature with the
  publisher's full key fingerprint when one is published. Packages that come from a package manager
  are covered by its own verification and, where you have one, a lock file with hashes. `ADD
  --checksum=<hash> <url>` does the checksum check for you: for HTTP sources it takes a
  SHA-256 digest (`sha256:<hash>`, the only supported algorithm) and needs Dockerfile syntax 1.6
  or later; for Git sources it takes the commit SHA (use the full SHA, since the reference also
  accepts a prefix of one or more characters) and needs syntax 1.16 or later.

why:
  The Docker Official Images guidelines ask for all three where possible (HTTPS, a signature check
  against a full key fingerprint, an embedded checksum), allow HTTPS plus a checksum when no
  signature is published, and accept a checksum alone only as a last resort when the site has no
  HTTPS and publishes no signature. A download with no verification is not acceptable there.

how_to_check:
  manual

sources:
- https://github.com/docker-library/official-images/blob/master/README.md
- https://docs.docker.com/reference/dockerfile/#add
- https://github.com/moby/buildkit/releases/tag/dockerfile%2F1.16.0
