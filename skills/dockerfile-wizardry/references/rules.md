This file is generated from [docs/rules/](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/) and must not be edited by hand: change the rulebook, then run `python3 .github/scripts/check_rules.py --write`. "This repository" below means placheckij/dockerfile-wizardry, where the rulebook lives, not the project the skill is used on.

# Dockerfile rules

## DW-BASE-01: Pin the base image by digest

Strength: SHOULD. Last verified: 2026-11-02.

Reference the base image as `tag@sha256:<digest>`, and keep the version in `ARG`s so it is
changed in one place. Keep the human-readable tag next to the digest so a reader can tell
what the digest is.

Why: A tag can be republished, so the same Dockerfile can build on different bytes tomorrow. A digest
names exactly one image. The cost is that pinning freezes the base: patches stop arriving on
their own, so pair the pin with something that proposes new digests (Dependabot or Renovate) or
with a CI job that fails when the tag has moved. See the trade-offs on [tag or
digest](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/tradeoffs.md#1-tag-or-digest-for-the-base-image).

How to check: Hadolint DL3006 (tag the image) and DL3007 (do not use `latest`) catch missing or floating
tags; a missing digest is checked manually or by a CI job that compares the pinned digest with
the tag's current one.

Sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/build/building/best-practices/#pin-base-image-versions
- https://docs.docker.com/reference/dockerfile/#understand-how-arg-and-from-interact

## DW-BASE-02: Label the image with metadata

Strength: SHOULD. Last verified: 2026-11-02.

Add `LABEL`s that say who maintains the image, which version it is and what it is for. Prefer
the OCI-defined keys (`org.opencontainers.image.*`, for example `.source`, `.version`,
`.licenses`) over private ones, so registries and scanners can read them.

Why: Labels make an image traceable to its source and owner, which helps when you need to find out
what is running and who to ask about it.

How to check: manual. Hadolint's `label-schema` option can enforce which labels exist and what type their
values are.

Sources:
- https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
- https://docs.docker.com/reference/dockerfile/#label

## DW-BUILD-01: Order layers by how often they change

Strength: SHOULD. Last verified: 2026-11-02.

Copy dependency manifests and lockfiles and install dependencies first; copy application code
afterwards. Install runtime dependencies only (no dev group), and make the build fail if the
lockfile is out of date.

Why: Docker reuses a layer until its inputs change, so putting the rarely-changing install step
before the often-changing code keeps rebuilds fast. Leaving dev tooling out saved about 39 MB in
this repository (120 MB to 81 MB). A locked install (`uv sync --locked` here) fails when the
lockfile no longer matches the project, so the image is built from exactly the versions you
reviewed.

How to check: manual

Sources:
- https://docs.docker.com/build/building/best-practices/#leverage-build-cache
- https://docs.astral.sh/uv/guides/integration/docker/

## DW-BUILD-02: Use multi-stage builds

Strength: SHOULD. Last verified: 2026-11-02.

Do the installing and compiling in a build stage and copy only the finished artifacts into the
runtime stage.

Why: Build tools, compilers and caches never reach the final image, which makes it smaller and gives
it less to attack.

How to check: manual

Sources:
- https://docs.docker.com/build/building/best-practices/#use-multi-stage-builds

## DW-BUILD-03: Copy only what the image needs

Strength: MUST. Last verified: 2026-11-02.

`COPY` only the specific paths the image needs rather than the whole context, use `COPY` rather
than `ADD` for local files, and keep tests, docs, `.git` and anything secret out of the image,
for example with a `.dockerignore` file that keeps them out of the build context.

Why: Whatever is copied is in the image for good, including secrets copied by accident. For local
files `COPY` is enough; `ADD` also unpacks local tar archives and can fetch remote URLs, which
is rarely what you meant (CIS 4.8, 4.9). Docker's best practices suggest a `.dockerignore` file,
which uses patterns like `.gitignore`, to exclude files not relevant to the build without
restructuring the repository. For a remote file on purpose, see DW-DEPS-03. See the
[trade-offs](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/tradeoffs.md#5-add-or-copy) between `ADD` and `COPY`.

How to check: Hadolint DL3020 (use `COPY` instead of `ADD` for files and folders); Dockle CIS-DI-0009
(use `COPY` instead of `ADD`). Dockle also flags a deliberate `ADD --checksum <url>` in the final
stage (it ignores only the earliest `ADD` in the history); do it in an earlier stage (see the
trade-offs), or use an exception, or a `RUN curl` in a build stage.

Sources:
- https://www.cisecurity.org/benchmark/docker
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-12-utilize-docker-secrets-for-sensitive-data-management
- https://docs.docker.com/reference/dockerfile/#add
- https://docs.docker.com/build/building/best-practices/#exclude-with-dockerignore

## DW-BUILD-04: Prune what the app never runs, then flatten

Strength: TRADE-OFF. Last verified: 2026-11-02.

Remove package managers, headers and network tools the application does not use, but keep the
package database (such as `/lib/apk/db` or `/var/lib/dpkg`), then copy the pruned filesystem
into a fresh `scratch` stage so the deleted files are gone from every layer. Declare `ENV`,
`LABEL`, `USER`, `WORKDIR` and the rest again, because `scratch` carries no metadata.

Why: Deleting files in a later layer saves nothing, since they stay in the layers below and can be
extracted by anyone who pulls the image. Flattening removes them for real (94 MB to 81 MB here).
This is defense in depth, not a barrier: an interpreter and a shell remain, so rely on the
runtime flags for containment. The database stays because vulnerability scanners read it to
list the OS packages; without it the scan can pass while checking nothing (DW-SUPPLY-05).
Removing the shell as well is possible but breaks `docker exec
... sh` debugging and any check that runs `ls` or `id` in the container, which is why this is a
trade-off between hardening and operability. See also [base image
choices](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/tradeoffs.md#6-which-base-image-default-slim-alpine-or-distroless).

How to check: manual. Inspect the contents of each layer, with a layer inspector such as `dive` or the layer
tarballs inside `docker save` output, to confirm the removed files appear in none. `docker
history` lists instructions and sizes, not files, so it cannot show this.

Sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/build/building/multi-stage/
- https://docs.docker.com/build/building/base-images/#create-a-minimal-base-image-using-scratch

## DW-BUILD-05: Keep package-manager downloads in a cache mount

Strength: SHOULD. Last verified: 2026-11-04.

Give the package manager's cache directory to the build with `RUN
--mount=type=cache,target=<dir>` instead of baking downloads into a layer, in a build stage;
in the final stage, install runtime packages as usual and clean up in the same layer
(DW-DEPS-01). Details for apt, non-root users and apk are in the reasons below.

Why: A cache mount survives between builds without ending up in the image, so repeated builds skip
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

How to check: manual. No linter checks for a cache mount. Hadolint's DL3009, DL3019 and DL3042 check the
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

Sources:
- https://docs.docker.com/build/cache/optimize/
- https://docs.docker.com/reference/dockerfile/
- https://wiki.alpinelinux.org/wiki/Local_APK_cache
- https://github.com/hadolint/hadolint

## DW-BUILD-06: Mount a large source tree instead of copying it when it only produces an artifact

Strength: SHOULD. Last verified: 2026-11-02.

When a large build context is only needed to produce an artifact, mount it for that one `RUN`
with `--mount=type=bind` rather than `COPY`ing it. Write the output outside the mounted path.

Why: Docker's documentation says that with a large context used only to generate an artifact you are
better off with bind mounts, because `COPY` makes BuildKit include all of those files in the
cache even when the final image does not use them. Bind-mounted files exist only for that
instruction and are not part of the image.

How to check: manual

Sources:
- https://docs.docker.com/build/cache/optimize/
- https://docs.docker.com/build/building/best-practices/#add-or-copy

## DW-BUILD-07: Export the build cache in CI, and choose its mode on purpose

Strength: TRADE-OFF. Last verified: 2026-11-02.

In CI, share cache between runs with `--cache-to` and `--cache-from` (for example
`type=registry`). The `mode` parameter decides which layers are exported: `min` is the default
and `max` exports more, including layers of intermediate stages. Try both and keep the one that
suits your builds, and restrict who can read the cache accordingly.

Why: CI runners usually start empty, so without an exported cache every run rebuilds everything. A
larger export can raise the cache hit rate but costs storage and upload time, and Docker says
`max` caches all layers, even those of intermediate steps, so a build stage's contents (and
anything you removed only in a later stage, see DW-BUILD-04) end up in the cache. Our suggestion
is to give the cache reference at least the access control of the most sensitive build stage,
which for a public image usually means keeping the cache private (this repository uses
`type=gha`). It does not carry cache mounts (DW-BUILD-05).

How to check: manual

Sources:
- https://docs.docker.com/build/cache/backends/
- https://docs.docker.com/build/cache/backends/registry/

## DW-BUILD-08: Cross-compile for other platforms instead of emulating them

Strength: SHOULD. Last verified: 2026-11-02.

When you build images for several CPU architectures, prefer native builders or cross-compilation
(`FROM --platform=$BUILDPLATFORM` with `TARGETOS`/`TARGETARCH`) over running the whole build
under QEMU emulation, if your language supports it.

Why: Docker's multi-platform documentation notes that emulation can be much slower than a native
build, especially for compute-heavy work such as compilation. Cross-compilation needs a
toolchain that can target another platform, which is why this is language dependent.

How to check: manual

Sources:
- https://docs.docker.com/build/building/multi-platform/

## DW-BUILD-09: Use SOURCE_DATE_EPOCH when you need reproducible output

Strength: SHOULD. Last verified: 2026-11-02.

Where reproducible builds matter, give the build a `SOURCE_DATE_EPOCH`, as a build argument, as
a default `ARG` in the global scope, or in the environment of the client (Buildx 0.10 and later
pass it through), so the timestamps BuildKit records follow it, and add
`rewrite-timestamp=true` to the image exporter (BuildKit 0.13 and later) so file times inside
the layers follow it too.

Why: Timestamps are a common reason two builds of the same source differ. The BuildKit
reproducibility documentation describes the setting and the exporter option; it does not promise
a bit-identical image on its own, since the base image, package state and other inputs still
have to be pinned too.

How to check: manual. Build the image twice with `--no-cache`, so that the second build cannot reuse the first
build's layers, and compare the two image manifest digests (`containerimage.digest` in the file
written by `--metadata-file`). Provenance attestations record build timestamps, so make the
comparison with attestations turned off, and use the same BuildKit version for both builds, since
BuildKit's `compatibility-version` option exists because assembly changes can change the digest.

Sources:
- https://github.com/moby/buildkit/blob/master/docs/build-repro.md
- https://docs.docker.com/build/metadata/attestations/slsa-provenance/

## DW-BUILD-10: Leave out remote-management and package-management tools

Strength: SHOULD. Last verified: 2026-11-02.

Do not include tools such as SSH or RDP, or system package managers, in the image that runs your
application unless it genuinely needs them. On a distribution base this is met either by
choosing a base without them or by pruning (DW-BUILD-04), which brings that rule's trade-off.

Why: The UK NCSC guidance on building container images says containers should not normally need
remote management tools like SSH or RDP, because management happens with container tooling
outside the container, and should not need package management tools, because the contents are
not expected to change at runtime. Fewer tools also leaves fewer for an attacker to use. See
DW-BUILD-04 for removing them from an existing image, and for keeping the package database that
scanners read.

How to check: manual

Sources:
- https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images

## DW-DEPS-01: Install only the packages you need, in one layer

Strength: TRADE-OFF. Last verified: 2026-11-03.

Install only what the running container needs, run the package index update and the install in
the same `RUN`, and remove package caches in that same layer, unless you keep them in a cache
mount (DW-BUILD-05), which is not part of the layer and should not be deleted. Whether to pin
each OS package to an exact version is a trade-off, described below.

Why: Every extra package is attack surface and size (CIS 4.3). An index update in its own layer can be
cached and go stale before the install runs (CIS 4.6). On pinning, sources disagree: linters such
as Hadolint (DL3008 for apt) ask for pinned versions for reproducibility, while a pinned version
can disappear from a repository that keeps only the current one, which in this repository's
experience Alpine does (see the pinning trade-off). Pinning also stops automatic security fixes.
This repository does not pin OS packages and relies on a base-image digest check and a weekly
no-cache rebuild instead. Note that Docker still reuses a whole `RUN` layer from its cache until
the instruction or the base digest changes, so patches only arrive when the cache is invalidated
(`docker build --no-cache --pull`, a new digest, or an edit to the `RUN`). See the trade-offs on
[pinning](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/tradeoffs.md#2-pinning-operating-system-package-versions) and
[updating](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/tradeoffs.md#3-update-inside-the-image-or-rebuild-from-a-fresh-base).

How to check: Hadolint DL3008 (pin apt versions) and DL3018 (pin apk versions) check the pinning side of the
trade-off. Hadolint DL3015 (apt without `--no-install-recommends`) checks for extra packages, and
DL3009 (apt lists not deleted) and DL3019 (apk without `--no-cache`) check the cache cleanup;
Dockle CIS-DI-0007 flags an `apt-get update` used alone (apt only). Whether to pin is the
decision described above.

Sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/build/building/best-practices/#run
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-9-integrate-container-scanning-tools-into-your-cicd-pipeline
- https://github.com/hadolint/hadolint

## DW-DEPS-02: Install language tooling pinned, with its cache out of the layer

Strength: SHOULD. Last verified: 2026-11-03.

Keep the installer's download cache out of the layer, either by disabling it or by keeping it
in a cache mount (DW-BUILD-05); configure the installer to use the interpreter already in the
base image, and pin its version (this repository pins `uv`). For Python, compile
bytecode at install time when the root filesystem will be read-only.

Why: A cache left in a layer adds size that can never be removed, and an unpinned installer makes
builds differ over time. The uv Docker guide shows both ways: a cache mount, and `--no-cache` or
`UV_NO_CACHE` for when you are not mounting the cache. This repository disables the cache. If you
mount it instead, the mount is created for `uid` 0 by default, so for a non-root build user pass
`uid=` and `gid=` and target that user's cache directory (`uv cache dir` shows it); a wrong
`target` leaves the mount unused, so the cache lands in the layer, and a right one the user cannot
write to fails the install. With a read-only runtime filesystem Python cannot write its own `.pyc`
files, so without install-time compilation it recompiles every installed module on every start
(the standard library of the official Python image is not precompiled either, per the uv guide,
and needs its own `compileall`); in this repository that measured 644 ms against 358 ms for
dependency imports, for about 8 MB more image. Python writes hash-based `.pyc` files when
`SOURCE_DATE_EPOCH` is set, which makes the bytecode reproducible. Turn compilation off if size
matters more than start-up time.

How to check: manual. Hadolint DL3042 reports a `pip install` that keeps pip's download cache in the layer; it
checks pip only, and not whether the installer is pinned.

Sources:
- https://docs.docker.com/build/building/best-practices/#run
- https://docs.astral.sh/uv/guides/integration/docker/
- https://docs.python.org/3/library/py_compile.html
- https://github.com/hadolint/hadolint

## DW-DEPS-03: Verify what you download during the build

Strength: SHOULD. Last verified: 2026-11-02.

When a build downloads a file or source archive directly (with `ADD`, `curl` or `wget`), fetch
it over HTTPS and check it against an embedded checksum, and against a signature with the
publisher's full key fingerprint when one is published. Packages that come from a package manager
are covered by its own verification and, where you have one, a lock file with hashes. `ADD
--checksum=<hash> <url>` does the checksum check for you (details below).

Why: The Docker Official Images guidelines ask for all three where possible (HTTPS, a signature check
against a full key fingerprint, an embedded checksum), allow HTTPS plus a checksum when no
signature is published, and accept a checksum alone only as a last resort when the site has no
HTTPS and publishes no signature. A download with no verification is not acceptable there.
For `ADD --checksum`, HTTP sources take a SHA-256 digest (`sha256:<hash>`, the only supported
algorithm) and need Dockerfile syntax 1.6 or later; Git sources take the commit SHA, which should
be the full SHA since the reference also accepts a prefix of one or more characters, and need
syntax 1.16 or later.

How to check: manual

Sources:
- https://github.com/docker-library/official-images/blob/master/README.md
- https://docs.docker.com/reference/dockerfile/#add
- https://github.com/moby/buildkit/releases/tag/dockerfile%2F1.16.0

## DW-HEALTH-01: Declare the port the application listens on

Strength: SHOULD. Last verified: 2026-11-02.

Add `EXPOSE <port>` for the port the application uses. When running the container, publish the
port on loopback (`-p 127.0.0.1:8000:8000`) unless it is meant to be reachable from other
hosts.

Why: `EXPOSE` does not publish anything; the Dockerfile reference calls it documentation between
whoever builds the image and whoever runs it about which ports are meant to be published. A bare
`-p 8000:8000` opens the port on all interfaces, and Docker's own firewall rules bypass host
firewalls such as UFW (OWASP Rule 5a).

How to check: manual

Sources:
- https://docs.docker.com/reference/dockerfile/#expose
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-5a-be-careful-when-mapping-container-ports-to-the-host-with-firewalls-like-ufw

## DW-HEALTH-02: Add a health check

Strength: SHOULD. Last verified: 2026-11-04.

Add a `HEALTHCHECK` that exercises the application, using a tool that exists in the image. A
failed check must exit non-zero.

Why: CIS 4.5 asks for it: Docker then reports whether the application inside is working (`healthy` or
`unhealthy`), not only whether the process is still running. Using the language runtime already
in the image avoids shipping `curl` and its libraries just for the check. Whether to rely on it
is partly your platform's call, since an orchestrator can use its own probes instead; Hadolint
ships its missing-`HEALTHCHECK` rule disabled by default. See the
[trade-offs](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/tradeoffs.md#4-a-healthcheck-in-the-image-or-probes-in-the-platform).

How to check: Hadolint DL3057 (missing `HEALTHCHECK`; ignored by default, so enable it); Dockle CIS-DI-0006.
Only the final stage needs a `HEALTHCHECK`, but DL3057 is reported for every stage without
one, so on a build stage's `FROM` it is a false positive.

Sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/reference/dockerfile/#healthcheck
- https://github.com/hadolint/hadolint

## DW-HEALTH-03: Set the stop signal

Strength: SHOULD. Last verified: 2026-11-02.

Set `STOPSIGNAL` to the signal your application handles for a clean shutdown (`SIGTERM` for
most servers), and make sure the process actually handles it.

Why: `docker stop` sends this signal first and kills the process after a timeout. A process that
ignores it loses in-flight work. The default is `SIGTERM` when the instruction is not set, so
for most servers `STOPSIGNAL SIGTERM` makes that choice explicit rather than changing it.

How to check: manual

Sources:
- https://docs.docker.com/reference/dockerfile/#stopsignal

## DW-HEALTH-04: Run a minimal init as PID 1

Strength: SHOULD. Last verified: 2026-11-02.

Use an init such as `tini` (or `docker run --init`) as the entrypoint, with the application
started in exec form.

Why: PID 1 has special signal and child-reaping behaviour. Without an init, orphaned child
processes can accumulate as zombies and signals may not reach the application, which delays
or breaks graceful shutdown.

How to check: manual

Sources:
- https://docs.docker.com/reference/cli/docker/container/run/#init
- https://github.com/krallin/tini

## DW-HEALTH-05: Use exec form, and exec in wrapper scripts, so signals reach the application

Strength: SHOULD. Last verified: 2026-11-03.

Write `ENTRYPOINT` and `CMD` in exec (JSON array) form. If the entrypoint is a shell script,
finish it with `exec <your-app>` so the application replaces the shell as the process that
receives signals.

Why: In shell form the executable runs as a child of a shell, which does not pass signals on, so the
application may never see `SIGTERM` and is killed after the stop timeout instead of shutting
down cleanly. The same happens when a wrapper script starts the application without `exec`.
Docker's build check `JSONArgsRecommended` flags the shell form for this reason.

How to check: Docker build check JSONArgsRecommended (`docker build --check`) and Hadolint DL3025 (JSON
notation for `CMD` and `ENTRYPOINT`). Neither looks inside a wrapper script, and a `SHELL`
instruction suppresses the build check's warning, so the `exec` in a script has to be checked by
reading it.

Sources:
- https://hynek.me/articles/docker-signals/
- https://docs.docker.com/reference/build-checks/json-args-recommended/
- https://github.com/hadolint/hadolint

## DW-SECRET-01: Never pass secrets through ARG, ENV or COPY; mount them

Strength: MUST. Last verified: 2026-11-03.

Give a build its secrets with `RUN --mount=type=secret` (or an SSH mount), never with `ARG`, `ENV`
or files copied into the image. A secret mount defaults to `uid` 0 and mode `0400`, so when the
build step runs as another user, pass `uid=` (and `gid=` or `mode=` if needed) so that user can
read it. A missing secret is skipped unless you add `required=true`.

Why: Docker's documentation says build arguments and environment variables are inappropriate for
passing secrets because they persist in the final image. Provenance attestations never include
the contents of secret mounts, but the `max` mode does expose the values of build arguments, and
Docker lists the identities of secrets among the details that `min` mode leaves out, so with
`max` even the names of your secrets can end up in published metadata. Anything copied into the
image becomes part of it, and the NCSC guidance singles out temporary secrets used during the
build, which must not be stored in the resulting image.

How to check: Docker build check SecretsUsedInArgOrEnv (`docker build --check`) and Hadolint DL3064, which
report `ENV` and `ARG` keys that look sensitive, so they match names only; Dockle CIS-DI-0010,
which checks environment variables and credential files, and in practice also flags
sensitive-looking `KEY=value` words in the final image's history, which is where a build argument
used by a `RUN` shows up; a secret scanner over the repository.

Sources:
- https://docs.docker.com/build/building/secrets/
- https://docs.docker.com/build/metadata/attestations/slsa-provenance/
- https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/
- https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md
- https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
- https://www.cisecurity.org/benchmark/docker
- https://github.com/hadolint/hadolint

## DW-SUPPLY-01: Attach an SBOM and provenance to the images you publish

Strength: SHOULD. Last verified: 2026-11-02.

Build published images with attestations: `--sbom=true` for a software bill of materials and
`--provenance=mode=max` for build provenance, or `mode=min` if build arguments might hold
anything sensitive.

Why: Attestations let consumers see what is inside an image and how it was built. Docker says that
when possible you should prefer `mode=max` because it holds much more detail, and warns that it
exposes the values of build arguments; `min` leaves out build argument values, the identities of
secrets and rich layer metadata, and Docker calls it safe for all builds. Pair `max` with
DW-SECRET-01, and use `min` when you cannot be sure or do not want to publish those details.

How to check: manual

Sources:
- https://docs.docker.com/build/metadata/attestations/sbom/
- https://docs.docker.com/build/metadata/attestations/slsa-provenance/

## DW-SUPPLY-02: Sign published images and verify them before deploying

Strength: SHOULD. Last verified: 2026-11-02.

Sign images you publish (for example with cosign) and verify the signature, against the identity
you expect, in the deployment path rather than trusting a tag. Keep the signing and verification
tooling current.

Why: Verification checks a signature against an expected identity, so a consumer can reject an image
that was not signed by it. The tooling itself has had bugs: cosign v3.1.3 resolved
GHSA-fx35-mq7g-6g98, a verification bypass using an unexpected public key in a legacy bundle. This
repository does not publish images; the [README](https://github.com/placheckij/dockerfile-wizardry/blob/main/README.md#-deliberately-not-included)
explains what it would take.

How to check: manual

Sources:
- https://docs.sigstore.dev/cosign/signing/signing_with_containers/
- https://docs.sigstore.dev/cosign/verifying/verify/
- https://github.com/sigstore/cosign/releases/tag/v3.1.3

## DW-SUPPLY-03: Pin GitHub Actions to full commit SHAs

Strength: SHOULD. Last verified: 2026-11-02.

Reference third-party GitHub Actions by their full commit SHA, not by a mutable tag.

Why: The Trivy supply chain advisory (GHSA-69fq-xp46-6x23, CVE-2026-33634, March 2026) recommends
pinning GitHub Actions to full, immutable commit SHA hashes and not using mutable version tags,
after malicious releases and action tags were published. It also shows that pinning the top
level is not the whole job: a `trivy-action` pinned to a commit from before 2025-04-09 would
itself have been safe but would have run a malicious `setup-trivy` during the exposure window, so
check what a pinned action fetches in turn.

How to check: manual

Sources:
- https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23

## DW-SUPPLY-04: Rebuild and replace instead of patching in place, and do not let cache hide updates

Strength: SHOULD. Last verified: 2026-11-02.

Apply security updates by building a new image and replacing the running container, and make
sure your build cache does not stop updates from being picked up. For example, run a periodic
`docker build --no-cache --pull`: `--pull` fetches a newer base image when `FROM` names a tag,
but with a digest-pinned `FROM` (DW-BASE-01) you update the digest instead, and only a build
without cache reruns the layers that install packages when the base is unchanged. Automated
base-image digest updates complement that build; they do not replace it, because a fix to a
package you install yourself does not change the base image.

Why: The NCSC guidance says security updates are typically applied by building a new image rather
than updating containers in place, and that build caching should not prevent security updates.
Docker notes that pinning a base image to a digest means opting out of automated security fixes,
and Renovate recommends pinning Docker images to an exact digest while it proposes updates; see
[tag or digest](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/tradeoffs.md#1-tag-or-digest-for-the-base-image) and
[updating](https://github.com/placheckij/dockerfile-wizardry/blob/main/docs/rules/tradeoffs.md#3-update-inside-the-image-or-rebuild-from-a-fresh-base).

How to check: manual. Docker Scout's `No outdated base images` policy checks base image freshness.

Sources:
- https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
- https://docs.docker.com/build/building/best-practices/#pin-base-image-versions
- https://docs.renovatebot.com/docker/

## DW-SUPPLY-05: Scan the static image, and check removed files are really gone

Strength: SHOULD. Last verified: 2026-11-02.

Scan the built image's contents for known vulnerabilities and misconfiguration without running it
(and for malware, if you accept more supply chain risk), and confirm that files you removed during
the build are not still present in a layer.

Why: The NCSC guidance asks for automated scanning to detect malware, known vulnerabilities and
misconfiguration (while noting that malware scanning brings little benefit if you minimise image
contents and secure your supply chain), says vulnerability scans should analyse a static image so
you should never need to run the container to scan it for vulnerabilities, and says you should be
sure that files removed during the build are entirely removed from the final image, which matters
most for temporary secrets. A scan can only report what it can see: keep the OS package database
in the image, and check that the scanner lists packages (see DW-BUILD-04).

How to check: A scanner such as Trivy covers known vulnerabilities, misconfiguration and secrets (this
repository runs it in CI); its documentation does not describe malware detection, which the NCSC
guidance also asks for, so that needs a separate tool if you want it. To confirm removed files
are gone, inspect the contents of each layer as described in DW-BUILD-04.

Sources:
- https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
- https://trivy.dev/latest/docs/

## DW-SUPPLY-06: Keep Docker Engine and BuildKit patched, and use only trusted frontends

Strength: SHOULD. Last verified: 2026-11-02.

Keep Docker Engine and BuildKit up to date, and use BuildKit frontends only from publishers you
trust, including any image named in a `# syntax=` line.

Why: BuildKit's GHSA-7236-3392-c5c6 (fixed in BuildKit 0.31.1, shipped in Docker Engine 29.6.1)
describes a custom frontend that could send a crafted request disabling the Seccomp and AppArmor
protections of the build container. The advisory's workaround is to use only BuildKit frontends
from trusted providers. The Dockerfile reference says the `syntax` directive declares which
Dockerfile syntax version to use, and that BuildKit uses a bundled version of the frontend when
it is not set. The Engine 29.9.0 release note refers to "the gRPC server that BuildKit runs for
frontend containers, such as images referenced by a `# syntax=` directive", so an image named
there is a frontend you are trusting. Pinning it by digest, as for base images, is our
suggestion, not something the sources state; a pin freezes the frontend, so update the digest
automatically as DW-BASE-01 and DW-SUPPLY-04 describe.

How to check: manual

Sources:
- https://github.com/advisories/GHSA-7236-3392-c5c6
- https://docs.docker.com/engine/release-notes/29/
- https://docs.docker.com/reference/dockerfile/#syntax

## DW-USER-01: Run as a non-root user

Strength: MUST. Last verified: 2026-11-04.

Create a dedicated user and group with explicit numeric IDs and switch to it by number,
`USER <uid>:<gid>`, before the final `CMD`/`ENTRYPOINT`. Never leave the container running
as root.

Why: Code execution inside the container then starts with the privileges of an unprivileged user,
not root, which limits what a compromise can reach (CIS 4.1, OWASP Rule 2). The uid must be
numeric because a name is mapped to an id only inside the container; the image config holds
just the name, which the host may not be able to resolve. With `runAsNonRoot: true` and no
`runAsUser`, the Kubernetes kubelet therefore refuses to start a container whose image names
its user ("image has non-numeric user (…), cannot verify user is non-root"). Give the gid as
a number as well: a group name, like a user name, is looked up in files inside the image
(Docker documents this for `COPY --chown`); and a user without a primary group (for example,
a uid with no `/etc/passwd` entry) runs with the root group. Giving a group, by name or number,
also drops the user's other group memberships, so give the runtime user what it needs
through that one group.

How to check: Hadolint DL3002 (last user should not be root), DL3066 (non-numeric user id, which the host
may not resolve); Dockle CIS-DI-0001 (a user has been created). DL3066 checks only the uid,
and accepts any uid taken from an `ARG` whatever its value, so check by reading that both
the uid and the gid are numbers. The Hadolint codes are findings only on the `USER` the
container runs as: the final stage's last `USER`, or, when the final stage sets none, the
last `USER` along the chain of stages it is built `FROM`. Hadolint v2.15.1 also reports
DL3002 on a build stage that ends as root and DL3066 on every `USER` given by name; on those
other lines they are not findings under this rule. A `USER` that only applies during the
build can be written `USER 0`, which DL3066 accepts.

Sources:
- https://www.cisecurity.org/benchmark/docker
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user
- https://github.com/hadolint/hadolint
- https://docs.docker.com/reference/dockerfile/#user
- https://docs.docker.com/reference/dockerfile/#copy---chown
- https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/
- https://github.com/kubernetes/kubernetes/blob/v1.37.2/pkg/kubelet/kuberuntime/security_context_others.go#L50

## DW-USER-02: The runtime user must not own or be able to change what it runs

Strength: SHOULD. Last verified: 2026-11-02.

Make application code and dependencies owned by `root`, readable (and executable where needed)
by the runtime user through a group, and not writable by anyone at runtime. Do the same for
the application directory itself.

Why: An owner can always `chmod` its own files back to writable, and a writable directory lets
entries be renamed or replaced, so a compromised process could tamper with its own code. OWASP
Rule 8 asks for a read-only filesystem at runtime; making the files root-owned is this
repository's build-time complement, which keeps the protection even when the runtime flag is
missing. The runtime flag remains the primary control.

How to check: manual. This repository's CI runs a check that the application user cannot write, `chmod` or
replace anything under the application directory.

Sources:
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only
