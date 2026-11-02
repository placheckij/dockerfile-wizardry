# Dependencies

What goes into the image besides your code: operating-system packages and language tooling.
Written from [Spell #3](../../README.md) and [Spell #5](../../README.md).

## DW-DEPS-01: Install only the packages you need, in one layer

strength: TRADE-OFF

spells:
- 3

last_verified: 2026-11-02

statement:
  Install only what the running container needs, run the package index update and the install
  in the same `RUN`, and remove package caches in that same layer. Whether to pin each OS
  package to an exact version is a trade-off, described below.

why:
  Every extra package is attack surface and size (CIS 4.3). An index update in its own layer can
  be cached and go stale before the install runs (CIS 4.6). On pinning, sources disagree:
  linters such as Hadolint (DL3008 for apt) ask for pinned versions for reproducibility, while
  repositories that keep only the current version of a package (Alpine does) break a pinned
  build as soon as a fix is published. Pinning also stops automatic security fixes. This
  repository does not pin OS packages and relies on a base-image digest check and a weekly
  no-cache rebuild instead. Note that Docker still reuses a whole `RUN` layer from its cache
  until the instruction or the base digest changes, so patches only arrive when the cache is
  invalidated (`docker build --no-cache --pull`, a new digest, or an edit to the `RUN`).

how_to_check:
  Hadolint DL3008 (apt pin) is the pinning side of the trade-off; Dockle CIS-DI-0007 flags an
  update instruction used alone. Choosing between them is a decision for your situation.

sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/build/building/best-practices/#run

## DW-DEPS-02: Install language tooling pinned, without caches

strength: SHOULD

spells:
- 5

last_verified: 2026-11-02

statement:
  Pin the version of the installer you add to the image (here `uv`), keep its download cache out
  of the layer, and configure it to use the interpreter already in the base image. For Python,
  compile bytecode at install time when the root filesystem will be read-only.

why:
  An unpinned installer makes builds differ over time. A cache left in a layer adds size that
  can never be removed. With a read-only runtime filesystem Python cannot write its own `.pyc`
  files, so without install-time compilation it recompiles every module on every start; in this
  repository that measured 644 ms against 358 ms for dependency imports. Setting
  `SOURCE_DATE_EPOCH` makes the bytecode reproducible. The size cost of bytecode is about 8 MB
  here; turn it off if size matters more than start-up time.

how_to_check:
  manual

sources:
- https://docs.docker.com/build/building/best-practices/#run
