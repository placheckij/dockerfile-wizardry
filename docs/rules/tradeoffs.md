# Trade-offs

Some Dockerfile choices have no single right answer: reputable sources disagree, or the best option depends on your situation. This page sets out each side with its source, then says what to weigh. Rules link here where a choice has its own section; some rules still recommend one side and link here for the other.

## 1. Tag or digest for the base image

**The choice.** `FROM python:3.14-alpine3.24` follows a tag; `FROM python:3.14-alpine3.24@sha256:<digest>` names exact bytes.

**For tags.** Docker's best-practices page points out that image tags are mutable: a publisher can point a tag at a new image, so a rebuild automatically picks up fixes (and, equally, surprises).

**For digests.** The same page says that pinning to a digest guarantees you always use the same image version, even if the publisher replaces the tag, and that this helps supply chain integrity. Renovate's documentation recommends pinning Docker images to an exact digest. Kubernetes uses only the digest when an image reference has both a tag and a digest, and advises avoiding `:latest` in production.

**The cost of digests, and Docker's answer.** Docker notes that looking up and updating digests by hand is tedious, and that you are opting out of automated security fixes. Its suggestion is the Docker Scout policy `No outdated base images`, or GitHub Dependabot with the `docker` ecosystem, which raises pull requests that update base image tags and digests on a schedule; Docker calls that better than a tag that changes the version automatically, because you are in control and have an audit trail.

**What to weigh.** If you can automate digest updates (a bot, or a CI job that fails when the tag has moved), pin and automate. If you cannot, a tag with regular rebuilds keeps you patched at the price of less repeatability; use `--pull` to fetch the newest base image and an occasional `--no-cache` build so the layers that install packages are rerun too. Keeping the tag next to the digest, as this repository does, means a reader can still tell what the digest is. See [DW-BASE-01](base-image.md) and [DW-SUPPLY-04](supply-chain.md).

Sources: [Docker: pin base image versions](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions), [Renovate: digest pinning](https://docs.renovatebot.com/docker/), [Kubernetes: images](https://kubernetes.io/docs/concepts/containers/images/).

## 2. Pinning operating-system package versions

**The choice.** `apt-get install package=1.3.*` (or an exact `apk` version) against taking whatever the repository offers.

**For pinning.** Docker's best-practices page says that version pinning forces the build to retrieve a particular version regardless of what is in the cache, and can reduce failures due to unanticipated changes in required packages. Hadolint checks for it with DL3008 (apt) and DL3018 (apk).

**Against pinning.** A pin stays where you put it until you change it, so fixes stop arriving on their own, and a repository that removes old versions breaks a pinned build. In this repository's experience Alpine keeps only the current version of each package per release, which is why [DW-DEPS-01](dependencies.md) does not pin; that is an observation about this project, not a cited source.

**An alternative (our suggestion).** Build from a dated snapshot of the distribution archive, which fixes the whole repository state instead of each package. snapshot.debian.org describes itself as useful for a specific environment that an application may require and documents the URL form for Debian archives at a given date; it does not describe a container build, and its page notes that apt needs `check-valid-until=no` for older snapshots and records that snapshots from an import failure were lost.

**What to weigh.** Pin if you rebuild on a schedule and update pins with it; do not pin if you rely on rebuilds to pick up fixes and your repository drops old versions.

Sources: [Docker: apt-get and version pinning](https://docs.docker.com/build/building/best-practices/#apt-get), [Hadolint rules](https://github.com/hadolint/hadolint), [snapshot.debian.org](https://snapshot.debian.org/).

## 3. Update inside the image, or rebuild from a fresh base

**The choice.** Run `apk upgrade` or `apt-get upgrade` during the build, against relying on a freshly pulled base image and a plain install.

**For upgrading in the build.** It picks up patches the base image does not have yet. This repository runs `apk -U upgrade` in the same layer as its package install (see its Dockerfile). Docker's current best-practices page gives no advice either way.

**For relying on the base image.** Dockle's DKL-DI-0003 flags `apt-get dist-upgrade`, and its notes refer to Docker's former advice to avoid `upgrade` and `dist-upgrade`, which Dockle shows struck through, so treat it as a linter rule rather than current Docker guidance. The NCSC guidance says updates are typically applied by building a new image rather than updating containers in place; a build-time upgrade also produces a new image, so that advice supports both approaches, and its real warning is that build caching must not stop updates from landing.

**What to weigh.** Whichever you choose, make sure the layer that holds the update is rebuilt: Docker reuses a layer from the build cache while its instruction and inputs are unchanged, and `--pull` only checks for a newer base image, so it does not rerun a package-install layer when the base is unchanged. Use a periodic `--no-cache` build (with `--pull`) or a changed base digest to rerun those layers. See [DW-SUPPLY-04](supply-chain.md).

Sources: [Dockle checkpoints](https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md), [NCSC: building container images](https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images), [Docker: optimize cache usage](https://docs.docker.com/build/cache/optimize/).

## 4. A HEALTHCHECK in the image, or probes in the platform

**In the image.** CIS 4.5 and Dockle's CIS-DI-0006 ask for a `HEALTHCHECK` (Dockle numbers its checks after an older benchmark, CIS Docker 1.13.0 v1.0.0, so the two numbers differ), so that Docker can report whether the application is working. It travels with the image.

**In the platform.** Kubernetes defines liveness, readiness and startup probes on the Pod, separately from the image. Hadolint lists its missing-`HEALTHCHECK` rule (DL3057) at severity `Ignore`.

**What to weigh.** An image that will run outside an orchestrator benefits from its own `HEALTHCHECK`; one that only runs in Kubernetes needs the probes either way. Nothing stops you from having both. See [DW-HEALTH-02](health-and-signals.md).

Sources: [Dockle checkpoints](https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md), [Kubernetes probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/), [Hadolint rules](https://github.com/hadolint/hadolint).

## 5. ADD or COPY

**COPY.** Docker's best-practices page says you will mostly want `COPY` for copying files from one stage to another in a multi-stage build, and that for files needed by a single `RUN` you can often use a bind mount instead. Hadolint (DL3020) flags `ADD` of plain local files where `COPY` would do, and Dockle (CIS-DI-0009) flags `ADD` in the image history.

**ADD.** The same page says `ADD` is best for when you need to download a remote artifact as part of your build, and better than fetching with `wget` and `tar` because it gives a more precise build cache and has built-in checksum validation. `ADD --checksum=sha256:<hash>` verifies the download (for HTTP sources SHA-256 only, Dockerfile syntax 1.6 or later; for Git sources the commit SHA, syntax 1.16 or later).

**What to weigh.** Use `COPY` for files from your own build context or an earlier stage. For a remote file, Docker prefers `ADD --checksum`; Hadolint's DL3020 only flags `ADD` of plain local files, not URLs or archives, so it does not object to that. Dockle's CIS-DI-0009 does not make that distinction: it looks for `ADD` in the final image's history, so an `ADD --checksum <url>` in the final stage is flagged (Dockle skips only the earliest `ADD` in the history) and needs a documented exception. Docker's own example avoids that by doing the `ADD --checksum` in a separate `FROM scratch AS src` stage and using the result with `RUN --mount=from=src`, so the `ADD` never reaches the final image's history; a `RUN curl` with its own checksum and signature check, run in a build stage and copied over with `COPY --from`, is the other alternative (curl itself stays out of the final image, see [DW-HEALTH-02](health-and-signals.md)). The important part is that the download is verified ([DW-DEPS-03](dependencies.md), [DW-BUILD-03](build-and-cache.md)).

Sources: [Docker: ADD or COPY](https://docs.docker.com/build/building/best-practices/#add-or-copy), [Dockerfile reference: ADD](https://docs.docker.com/reference/dockerfile/#add), [Dockle checkpoints](https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md), [Hadolint rules](https://github.com/hadolint/hadolint), [Hadolint DL3020 source](https://github.com/hadolint/hadolint/blob/master/src/Hadolint/Rule/DL3020.hs).

## 6. Which base image: default, slim, Alpine or distroless

**Default and slim.** For Python, the official image's own README says that unless you are working in an environment where only the `python` image will be deployed and you have space constraints, they highly recommend the default image. The `slim` variant contains only the minimal Debian packages needed to run Python.

**Alpine.** The same README calls Alpine much smaller and useful when final image size is your primary concern, with the caveat that it uses musl libc instead of glibc, so software often runs into issues, depending on how much it assumes about its libc. A well-known article argues that Alpine can make Python builds much slower; it also notes that PEP 656 now lets pip and PyPI support musl wheels, so the penalty is smaller than it was.

**Distroless.** Google's distroless images contain only your application and its runtime dependencies, with no package managers or shells, and offer a `:debug` variant with a busybox shell for troubleshooting. The NCSC guidance gives the security argument: fewer tools in the image leaves fewer for a successful attacker.

**What to weigh.** Smaller and emptier images reduce attack surface and size but make building native dependencies and debugging harder; the default image is the least surprising. Choose by how much you value size and attack surface against build simplicity and the ability to debug in place. This repository uses Alpine and then flattens the result ([DW-BUILD-04](build-and-cache.md)). Hardened-image products are not covered here.

Sources: [Docker library: Python image variants](https://github.com/docker-library/docs/blob/master/python/README.md), [Python Speed: Alpine and Python](https://pythonspeed.com/articles/alpine-docker-python/), [distroless](https://github.com/GoogleContainerTools/distroless), [NCSC: building container images](https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images).
