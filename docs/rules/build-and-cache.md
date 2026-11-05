# Build and cache

How the image is assembled: layer order, stages, what is copied in and what is taken out.
The first four rules are written from Spell #6, #7, #8 and #10; the rest come from the cited
sources alone.

## DW-BUILD-01: Order layers by how often they change

strength: SHOULD

spells:
- 6

last_verified: 2026-11-02

statement:
  Copy dependency manifests and lockfiles and install dependencies first; copy application code
  afterwards. Install runtime dependencies only (no dev group), and make the build fail if the
  lockfile is out of date.

why:
  Docker reuses a layer until its inputs change, so putting the rarely-changing install step
  before the often-changing code keeps rebuilds fast. Leaving dev tooling out saved about 39 MB in
  this repository (120 MB to 81 MB). A locked install (`uv sync --locked` here) fails when the
  lockfile no longer matches the project, so the image is built from exactly the versions you
  reviewed.

how_to_check:
  manual

sources:
- https://docs.docker.com/build/building/best-practices/#leverage-build-cache
- https://docs.astral.sh/uv/guides/integration/docker/

## DW-BUILD-02: Use multi-stage builds

strength: SHOULD

spells:
- 7

last_verified: 2026-11-02

statement:
  Do the installing and compiling in a build stage and copy only the finished artifacts into the
  runtime stage.

why:
  Build tools, compilers and caches never reach the final image, which makes it smaller and gives
  it less to attack.

how_to_check:
  manual

sources:
- https://docs.docker.com/build/building/best-practices/#use-multi-stage-builds

## DW-BUILD-03: Copy only what the image needs

strength: MUST

spells:
- 8

last_verified: 2026-11-02

statement:
  `COPY` only the specific paths the image needs rather than the whole context, use `COPY` rather
  than `ADD` for local files, and keep tests, docs, `.git` and anything secret out of the image,
  for example with a `.dockerignore` file that keeps them out of the build context.

why:
  Whatever is copied is in the image for good, including secrets copied by accident. For local
  files `COPY` is enough; `ADD` also unpacks local tar archives and can fetch remote URLs, which
  is rarely what you meant (CIS 4.8, 4.9). Docker's best practices suggest a `.dockerignore` file,
  which uses patterns like `.gitignore`, to exclude files not relevant to the build without
  restructuring the repository. For a remote file on purpose, see DW-DEPS-03. See the
  [trade-offs](tradeoffs.md#5-add-or-copy) between `ADD` and `COPY`.

how_to_check:
  Hadolint DL3020 (use `COPY` instead of `ADD` for files and folders); Dockle CIS-DI-0009
  (use `COPY` instead of `ADD`). Dockle also flags a deliberate `ADD --checksum <url>` in the final
  stage (it ignores only the earliest `ADD` in the history); do it in an earlier stage (see the
  trade-offs), or use an exception, or a `RUN curl` in a build stage.

sources:
- https://www.cisecurity.org/benchmark/docker
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-12-utilize-docker-secrets-for-sensitive-data-management
- https://docs.docker.com/reference/dockerfile/#add
- https://docs.docker.com/build/building/best-practices/#exclude-with-dockerignore

## DW-BUILD-04: Prune what the app never runs, then flatten

strength: TRADE-OFF

spells:
- 10

last_verified: 2026-11-02

statement:
  Remove package managers, headers and network tools the application does not use, but keep the
  package database (such as `/lib/apk/db` or `/var/lib/dpkg`), then copy the pruned filesystem
  into a fresh `scratch` stage so the deleted files are gone from every layer. Declare `ENV`,
  `LABEL`, `USER`, `WORKDIR` and the rest again, because `scratch` carries no metadata.

why:
  Deleting files in a later layer saves nothing, since they stay in the layers below and can be
  extracted by anyone who pulls the image. Flattening removes them for real (94 MB to 81 MB here).
  This is defense in depth, not a barrier: an interpreter and a shell remain, so rely on the
  runtime flags for containment. The database stays because vulnerability scanners read it to
  list the OS packages; without it the scan can pass while checking nothing (DW-SUPPLY-05).
  Removing the shell as well is possible but breaks `docker exec
  ... sh` debugging and any check that runs `ls` or `id` in the container, which is why this is a
  trade-off between hardening and operability. See also [base image
  choices](tradeoffs.md#6-which-base-image-default-slim-alpine-or-distroless).

how_to_check:
  manual. Inspect the contents of each layer, with a layer inspector such as `dive` or the layer
  tarballs inside `docker save` output, to confirm the removed files appear in none. `docker
  history` lists instructions and sizes, not files, so it cannot show this.

sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/build/building/multi-stage/
- https://docs.docker.com/build/building/base-images/#create-a-minimal-base-image-using-scratch

## DW-BUILD-05: Keep package-manager downloads in a cache mount

strength: SHOULD

last_verified: 2026-11-04

statement:
  Give the package manager's cache directory to the build with `RUN
  --mount=type=cache,target=<dir>` instead of baking downloads into a layer, in a build stage;
  in the final stage, install runtime packages as usual and clean up in the same layer
  (DW-DEPS-01). Details for apt, non-root users and apk are in the reasons below.

why:
  A cache mount survives between builds without ending up in the image, so repeated builds skip
  re-downloading what has not changed. Cache mounts live in the builder's local storage: the
  Dockerfile reference says they are not included in exported build cache (`--cache-to`), are not
  restored by `--cache-from`, and start empty when each build runs on a new builder, such as a fresh
  CI runner (see DW-BUILD-07). The right directory and options depend on the tool: Docker gives
  examples for a few tools and says to read your tool's own documentation. For apt, use
  `sharing=locked`, which gives it exclusive access to its data; the Dockerfile reference's apt
  example first removes `/etc/apt/apt.conf.d/docker-clean` (a Debian and Ubuntu image setting that
  clears downloaded packages) and sets `Binary::apt::APT::Keep-Downloaded-Packages "true"`, and as
  that is its own `RUN` it persists into whatever image the stage produces. For apk, the Alpine wiki
  says the cache is enabled through `/etc/apk/cache`, so a mount aimed at another directory such as
  `/var/cache/apk` does nothing unless that path is linked there. A cache mount is created with
  `uid` 0 and mode `0755` by default, so when the stage runs as another user, pass `uid=` and `gid=`
  and point `target` at that user's actual cache directory.

how_to_check:
  manual. No linter checks for a cache mount. Hadolint's DL3009, DL3019 and DL3042 check the
  cleanup that DW-DEPS-01 and DW-DEPS-02 ask for, and are reported under those rules; they stay
  quiet for an install with a cache mount on the path each expects (`/var/lib/apt/lists`,
  `/var/cache/apk`, pip's cache). For pip, Hadolint v2.15.1 accepts a cache or tmpfs mount
  whose target contains `.cache/pip` anywhere, under any home directory (`/root/.cache/pip`,
  `/home/app/.cache/pip`), and still fires for a mount on the parent `.cache` or on a
  directory whose path lacks `.cache/pip`.
  DL3019 still fires for a mount on `/etc/apk/cache`, the directory the Alpine wiki names, so
  there it is a false positive. Dockle reads the image history, not the Dockerfile, so it cannot
  see a mount and may still report an `apk add` without `--no-cache` (DKL-DI-0004) or an apt
  install that leaves its lists (DKL-DI-0005).

sources:
- https://docs.docker.com/build/cache/optimize/
- https://docs.docker.com/reference/dockerfile/
- https://wiki.alpinelinux.org/wiki/Local_APK_cache
- https://github.com/hadolint/hadolint

## DW-BUILD-06: Mount a large source tree instead of copying it when it only produces an artifact

strength: SHOULD

last_verified: 2026-11-02

statement:
  When a large build context is only needed to produce an artifact, mount it for that one `RUN`
  with `--mount=type=bind` rather than `COPY`ing it. Write the output outside the mounted path.

why:
  Docker's documentation says that with a large context used only to generate an artifact you are
  better off with bind mounts, because `COPY` makes BuildKit include all of those files in the
  cache even when the final image does not use them. Bind-mounted files exist only for that
  instruction and are not part of the image.

how_to_check:
  manual

sources:
- https://docs.docker.com/build/cache/optimize/
- https://docs.docker.com/build/building/best-practices/#add-or-copy

## DW-BUILD-07: Export the build cache in CI, and choose its mode on purpose

strength: TRADE-OFF

last_verified: 2026-11-02

statement:
  In CI, share cache between runs with `--cache-to` and `--cache-from` (for example
  `type=registry`). The `mode` parameter decides which layers are exported: `min` is the default
  and `max` exports more, including layers of intermediate stages. Try both and keep the one that
  suits your builds, and restrict who can read the cache accordingly.

why:
  CI runners usually start empty, so without an exported cache every run rebuilds everything. A
  larger export can raise the cache hit rate but costs storage and upload time, and Docker says
  `max` caches all layers, even those of intermediate steps, so a build stage's contents (and
  anything you removed only in a later stage, see DW-BUILD-04) end up in the cache. Our suggestion
  is to give the cache reference at least the access control of the most sensitive build stage,
  which for a public image usually means keeping the cache private (this repository uses
  `type=gha`). It does not carry cache mounts (DW-BUILD-05). A persistent self-hosted runner
  keeps its builder's local cache between runs, so it can do without an export; that kept cache
  is then what a periodic no-cache rebuild has to get past (DW-SUPPLY-04).

how_to_check:
  manual

sources:
- https://docs.docker.com/build/cache/backends/
- https://docs.docker.com/build/cache/backends/registry/

## DW-BUILD-08: Cross-compile for other platforms instead of emulating them

strength: SHOULD

last_verified: 2026-11-02

statement:
  When you build images for several CPU architectures, prefer native builders or cross-compilation
  (`FROM --platform=$BUILDPLATFORM` with `TARGETOS`/`TARGETARCH`) over running the whole build
  under QEMU emulation, if your language supports it.

why:
  Docker's multi-platform documentation notes that emulation can be much slower than a native
  build, especially for compute-heavy work such as compilation. Cross-compilation needs a
  toolchain that can target another platform, which is why this is language dependent.

how_to_check:
  manual

sources:
- https://docs.docker.com/build/building/multi-platform/

## DW-BUILD-09: Use SOURCE_DATE_EPOCH when you need reproducible output

strength: SHOULD

last_verified: 2026-11-02

statement:
  Where reproducible builds matter, give the build a `SOURCE_DATE_EPOCH`, as a build argument, as
  a default `ARG` in the global scope, or in the environment of the client (Buildx 0.10 and later
  pass it through), so the timestamps BuildKit records follow it, and add
  `rewrite-timestamp=true` to the image exporter (BuildKit 0.13 and later) so file times inside
  the layers follow it too.

why:
  Timestamps are a common reason two builds of the same source differ. The BuildKit
  reproducibility documentation describes the setting and the exporter option; it does not promise
  a bit-identical image on its own, since the base image, package state and other inputs still
  have to be pinned too.

how_to_check:
  manual. Build the image twice with `--no-cache`, so that the second build cannot reuse the first
  build's layers, and compare the two image manifest digests (`containerimage.digest` in the file
  written by `--metadata-file`). Provenance attestations record build timestamps, so make the
  comparison with attestations turned off, and use the same BuildKit version for both builds, since
  BuildKit's `compatibility-version` option exists because assembly changes can change the digest.

sources:
- https://github.com/moby/buildkit/blob/master/docs/build-repro.md
- https://docs.docker.com/build/metadata/attestations/slsa-provenance/

## DW-BUILD-10: Leave out remote-management and package-management tools

strength: SHOULD

last_verified: 2026-11-02

statement:
  Do not include tools such as SSH or RDP, or system package managers, in the image that runs your
  application unless it genuinely needs them. On a distribution base this is met either by
  choosing a base without them or by pruning (DW-BUILD-04), which brings that rule's trade-off.

why:
  The UK NCSC guidance on building container images says containers should not normally need
  remote management tools like SSH or RDP, because management happens with container tooling
  outside the container, and should not need package management tools, because the contents are
  not expected to change at runtime. Fewer tools also leaves fewer for an attacker to use. See
  DW-BUILD-04 for removing them from an existing image, and for keeping the package database that
  scanners read.

how_to_check:
  manual

sources:
- https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
