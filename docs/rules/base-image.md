# Base image

Which image you build on, and how you identify it. Rules in this file are written from the
README's Spell #1 and Spell #2; the code is in the
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
  with a CI job that fails when the tag has moved. See the trade-offs on [tag or
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

## DW-BASE-03: Keep Docker Engine and BuildKit patched, and use only trusted frontends

strength: SHOULD

last_verified: 2026-11-02

statement:
  Keep Docker Engine and BuildKit up to date, and use BuildKit frontends only from publishers you
  trust, including any image named in a `# syntax=` line.

why:
  BuildKit's GHSA-7236-3392-c5c6 (fixed in BuildKit 0.31.1, shipped in Docker Engine 29.6.1)
  describes a custom frontend that could send a crafted request disabling the Seccomp and AppArmor
  protections of the build container. The advisory's workaround is to use only BuildKit frontends
  from trusted providers. The Dockerfile reference says the `syntax` directive declares which
  Dockerfile syntax version to use, and that BuildKit uses a bundled version of the frontend when
  it is not set. The Engine 29.9.0 release note describes the gRPC server that BuildKit runs for
  frontend containers as serving "images referenced by a `# syntax=` directive", so an image named
  there is a frontend you are trusting. Pinning it by digest, as for base images, is our
  suggestion, not something the sources state.

how_to_check:
  manual

sources:
- https://github.com/advisories/GHSA-7236-3392-c5c6
- https://docs.docker.com/engine/release-notes/29/
- https://docs.docker.com/reference/dockerfile/#syntax
