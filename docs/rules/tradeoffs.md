# Trade-offs

Some Dockerfile choices have no single right answer: reputable sources disagree, or the best option depends on your situation. This page sets out each side with its source, then says what to weigh. The [rules](README.md) link here instead of picking a side for you.

## 1. Tag or digest for the base image

**The choice.** `FROM python:3.14-alpine3.24` follows a tag; `FROM python:3.14-alpine3.24@sha256:<digest>` names exact bytes.

**For tags.** Docker's best-practices page points out that image tags are mutable: a publisher can point a tag at a new image, so a rebuild automatically picks up fixes (and, equally, surprises).

**For digests.** The same page says that pinning to a digest guarantees you always use the same image version, even if the publisher replaces the tag, and that this helps supply chain integrity. Renovate's documentation recommends pinning Docker images to an exact digest. Kubernetes uses only the digest when an image reference has both a tag and a digest, and advises avoiding `:latest` in production.

**The cost of digests.** Docker notes that looking up and updating digests by hand is tedious, and that you are opting out of automated security fixes. It suggests the Docker Scout policy `No outdated base images`, or an update bot, to compensate.

**What to weigh.** If you can automate digest updates (a bot, or a CI job that fails when the tag has moved), pin and automate. If you cannot, a tag with regular rebuilds (`docker build --pull`) keeps you patched at the price of less repeatability. Keeping the tag next to the digest, as this repository does, means a reader can still tell what the digest is. See [DW-BASE-01](base-image.md) and [DW-SUPPLY-04](supply-chain.md).

Sources: [Docker: pin base image versions](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions), [Renovate: digest pinning](https://docs.renovatebot.com/docker/), [Kubernetes: images](https://kubernetes.io/docs/concepts/containers/images/).

## 2. Pinning operating-system package versions

**The choice.** `apt-get install package=1.3.*` (or an exact `apk` version) against taking whatever the repository offers.

**For pinning.** Docker's best-practices page says that version pinning forces the build to retrieve a particular version regardless of what is in the cache, and can reduce failures due to unanticipated changes in required packages. Hadolint checks for it with DL3008 (apt) and DL3018 (apk).

**Against pinning.** A pin stays where you put it until you change it, so fixes stop arriving on their own, and a repository that removes old versions breaks a pinned build. In this repository's experience Alpine keeps only the current version of each package per release, which is why [DW-DEPS-01](dependencies.md) does not pin; that is an observation about this project, not a cited source.

**An alternative (our suggestion).** Build from a dated snapshot of the distribution archive, which fixes the whole repository state instead of each package. snapshot.debian.org documents the URL form for Debian, but it does not describe this use, and old snapshots can be unavailable.

**What to weigh.** Pin if you rebuild on a schedule and update pins with it; do not pin if you rely on rebuilds to pick up fixes and your repository drops old versions.

Sources: [Docker: apt-get and version pinning](https://docs.docker.com/build/building/best-practices/#apt-get), [Hadolint rules](https://github.com/hadolint/hadolint).

## 3. Update inside the image, or rebuild from a fresh base

**The choice.** Run `apk upgrade` or `apt-get upgrade` during the build, against relying on a freshly pulled base image.

**For upgrading in the build.** It picks up patches the base image does not have yet. This repository runs `apk -U upgrade` in the same layer as its package install ([DW-DEPS-01](dependencies.md)).

**Against.** Dockle's DKL-DI-0003 flags `apt-get dist-upgrade`, and its notes refer to Docker's former advice to avoid `upgrade` and `dist-upgrade`. The NCSC guidance says updates are typically applied by building a new image rather than updating in place, and that build caching must not stop updates from landing.

**What to weigh.** Whichever you choose, make sure the layer that holds the update is rebuilt: Docker reuses a whole `RUN` layer from its cache until the instruction or the base digest changes, so use `--pull`, a periodic build without cache, or a changed digest. See [DW-SUPPLY-04](supply-chain.md).

Sources: [Dockle checkpoints](https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md), [NCSC: building container images](https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images).

## 4. A HEALTHCHECK in the image, or probes in the platform

**In the image.** CIS 4.5 and Dockle's CIS-DI-0006 ask for a `HEALTHCHECK`, so that Docker can report whether the application is working. It travels with the image.

**In the platform.** Kubernetes defines liveness, readiness and startup probes on the Pod, separately from the image. Hadolint lists its missing-`HEALTHCHECK` rule (DL3057) at severity `Ignore`.

**What to weigh.** An image that will run outside an orchestrator benefits from its own `HEALTHCHECK`; one that only runs in Kubernetes needs the probes either way. Nothing stops you from having both. See [DW-HEALTH-02](health-and-signals.md).

Sources: [Dockle checkpoints](https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md), [Kubernetes probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/), [Hadolint rules](https://github.com/hadolint/hadolint).

## 5. ADD or COPY

**COPY.** Docker's best-practices page says you will mostly want `COPY`, and Hadolint (DL3020) and Dockle (CIS-DI-0009) flag `ADD` where `COPY` would do.

**ADD.** `ADD` can fetch remote HTTPS and Git URLs and extract tar files from the build context. For remote files `ADD --checksum=sha256:<hash>` verifies the download (SHA-256 only, Dockerfile syntax 1.6 or later).

**What to weigh.** Use `COPY` for local files. For a remote file, either `ADD --checksum` or `RUN curl` followed by a checksum and signature check is reasonable; the important part is that the download is verified ([DW-DEPS-03](dependencies.md), [DW-BUILD-03](build-and-cache.md)).

Sources: [Docker: ADD or COPY](https://docs.docker.com/build/building/best-practices/#add-or-copy), [Dockerfile reference: ADD](https://docs.docker.com/reference/dockerfile/#add).

## 6. Which base image: default, slim, Alpine or distroless

**Default and slim.** For Python, the official image's own README says that unless you are working in an environment where only the `python` image will be deployed and you have space constraints, they highly recommend the default image. The `slim` variant contains only the minimal Debian packages needed to run Python.

**Alpine.** The same README calls Alpine much smaller and useful when final image size is your primary concern, with the caveat that it uses musl libc instead of glibc, so some software runs into issues. A well-known article argues that Alpine can make Python builds much slower; it also notes that PEP 656 now lets pip and PyPI support musl wheels, so the penalty is smaller than it was.

**Distroless.** Google's distroless images contain only your application and its runtime dependencies, with no package managers or shells, and offer a `:debug` variant with a busybox shell for troubleshooting. The NCSC guidance gives the security argument: fewer tools in the image leaves fewer for a successful attacker.

**What to weigh.** Smaller and emptier images reduce attack surface and size but make building native dependencies and debugging harder; the default image is the least surprising. Choose by how much you value size and attack surface against build simplicity and the ability to debug in place. This repository uses Alpine and then flattens the result ([DW-BUILD-04](build-and-cache.md)). Hardened-image products are not covered here.

Sources: [Docker library: Python image variants](https://github.com/docker-library/docs/blob/master/python/README.md), [Python Speed: Alpine and Python](https://pythonspeed.com/articles/alpine-docker-python/), [distroless](https://github.com/GoogleContainerTools/distroless), [NCSC: building container images](https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images).
