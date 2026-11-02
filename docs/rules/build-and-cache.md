# Build and cache

How the image is assembled: layer order, stages, what is copied in and what is taken out.
Written from Spell #6, #7, #8 and
#10.

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
  than `ADD` for local files, and keep tests, docs, `.git` and anything secret out of the image.

why:
  Whatever is copied is in the image for good, including secrets copied by accident. `ADD` can
  fetch remote files and unpack archives, which is rarely what you meant (CIS 4.8, 4.9).

how_to_check:
  Hadolint DL3020 (use `COPY` instead of `ADD` for files and folders); Dockle CIS-DI-0009
  (use `COPY` instead of `ADD`).

sources:
- https://www.cisecurity.org/benchmark/docker
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-12-utilize-docker-secrets-for-sensitive-data-management
- https://docs.docker.com/reference/dockerfile/#add

## DW-BUILD-04: Prune what the app never runs, then flatten

strength: TRADE-OFF

spells:
- 10

last_verified: 2026-11-02

statement:
  Remove package managers, headers and network tools the application does not use, then copy
  the pruned filesystem into a fresh `scratch` stage so the deleted files are gone from every
  layer. Declare `ENV`, `LABEL`, `USER`, `WORKDIR` and the rest again, because `scratch` carries
  no metadata.

why:
  Deleting files in a later layer saves nothing, since they stay in the layers below and can be
  extracted by anyone who pulls the image. Flattening removes them for real (94 MB to 81 MB
  here). This is defense in depth, not a barrier: an interpreter and a shell remain, so rely on
  the runtime flags for containment. Removing the shell as well is possible but breaks
  `docker exec ... sh` debugging and any check that runs `ls` or `id` in the container, which
  is why this is a trade-off between hardening and operability.

how_to_check:
  manual. Inspect each layer (for example with `docker history` or `dive`) to confirm the
  removed files appear in none.

sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/build/building/multi-stage/
- https://docs.docker.com/build/building/base-images/#create-a-minimal-base-image-using-scratch
