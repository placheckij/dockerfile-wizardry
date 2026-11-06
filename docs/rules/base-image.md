# Base image

Which image you build on, and how you identify it. DW-BASE-01 and DW-BASE-02 are written from
the README's Spell #1 and Spell #2; the code is in the
[Dockerfile](../../Dockerfile).

## DW-BASE-01: Pin the base image by digest

strength: SHOULD

spells:
- 1

last_verified: 2026-11-02

statement:
  Reference the base image as `tag@sha256:<digest>`, and keep the version in `ARG`s so it is
  changed in one place. Keep the human-readable tag next to the digest so a reader can tell
  what the digest is.

why:
  A tag can be republished, so the same Dockerfile can build on different bytes tomorrow. A digest
  names exactly one image. The cost is that pinning freezes the base: patches stop arriving on
  their own, so pair the pin with something that proposes new digests (Dependabot or Renovate) or
  with a CI job that fails when the tag has moved. Neither helps when the tag itself is no longer
  rebuilt, so pin a tag that still is (DW-BASE-03). See the trade-offs on [tag or
  digest](tradeoffs.md#1-tag-or-digest-for-the-base-image).

how_to_check:
  Hadolint DL3006 (tag the image) and DL3007 (do not use `latest`) catch missing or floating
  tags; a missing digest is checked manually or by a CI job that compares the pinned digest with
  the tag's current one.

sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/build/building/best-practices/#pin-base-image-versions
- https://docs.docker.com/reference/dockerfile/#understand-how-arg-and-from-interact

## DW-BASE-02: Label the image with metadata

strength: SHOULD

spells:
- 2

last_verified: 2026-11-02

statement:
  Add `LABEL`s that say who maintains the image, which version it is and what it is for. Prefer
  the OCI-defined keys (`org.opencontainers.image.*`, for example `.source`, `.version`,
  `.licenses`) over private ones, so registries and scanners can read them.

why:
  Labels make an image traceable to its source and owner, which helps when you need to find out
  what is running and who to ask about it.

how_to_check:
  manual. Hadolint's `label-schema` option can enforce which labels exist and what type their
  values are.

sources:
- https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
- https://docs.docker.com/reference/dockerfile/#label

## DW-BASE-03: Build on a tag that is still rebuilt

strength: SHOULD

last_verified: 2026-11-06

statement:
  Base the image on a tag its publisher still maintains: the current release, or a tag that
  follows it (`3.12-slim` rather than `3.12.4-slim` once 3.12.5 is out). Check this before
  pinning the tag by digest (DW-BASE-01).

why:
  The Docker Official Images FAQ says a release stops being supported once the next one ships,
  and that its tag is typically left available for pulling but "will simply never get rebuilt
  after that point". Such a tag no longer moves, so `--pull` finds nothing newer, a digest pin of
  it looks current forever, and checks that compare the pinned digest with the tag's current one
  pass: Docker Scout's `No outdated base images` policy flags an image only when the tag it was
  built from points to a different digest. The base then misses every fix shipped since.

how_to_check:
  For a tag that names a patch release (`3.12.4-slim-bookworm`), compare its current digest with
  that of its release-line tag, the same tag with the patch number dropped and any variant kept
  (`3.12-slim-bookworm`); different digests mean it is no longer rebuilt. A tag that already names
  a release line (`alpine:3.23`) has no such comparison, and a broader tag (`3-slim`) moving to a
  newer minor or major version says nothing about the release line you use. To check the release
  line itself, print when the base image was built with
  `docker buildx imagetools inspect <image>:<tag> --format '{{ (index .Image "linux/amd64").Created }}'`
  (name the platform you build for; use `{{ .Image.Created }}` for a single-platform image). The
  FAQ says Debian-based Official Images are republished at least monthly, so one that is months
  older is most likely no longer rebuilt; other bases follow their own schedules, and a
  reproducible build may carry a fixed date such as 1970-01-01. Confirm with the supported tags
  on the image's Docker Hub page.

sources:
- https://github.com/docker-library/faq#what-do-you-mean-by-supported
- https://github.com/docker-library/faq#why-does-my-security-scanner-show-that-an-image-has-cves
- https://docs.docker.com/scout/policy/#no-outdated-base-images
