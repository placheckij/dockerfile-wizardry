# Secrets

How credentials reach a build without ending up in the image or its metadata.


## DW-SECRET-01: Never pass secrets through ARG, ENV or COPY; mount them

strength: MUST

last_verified: 2026-11-03

statement:
  Give a build its secrets with `RUN --mount=type=secret` (or an SSH mount), never with `ARG`, `ENV`
  or files copied into the image. A secret mount defaults to `uid` 0 and mode `0400`, so when the
  build step runs as another user, pass `uid=` (and `gid=` or `mode=` if needed) so that user can
  read it. A missing secret is skipped unless you add `required=true`.

why:
  Docker's documentation says build arguments and environment variables are inappropriate for
  passing secrets because they persist in the final image. Provenance attestations never include
  the contents of secret mounts, but the `max` mode does expose the values of build arguments, and
  Docker lists the identities of secrets among the details that `min` mode leaves out, so with
  `max` even the names of your secrets can end up in published metadata. Anything copied into the
  image becomes part of it, and the NCSC guidance singles out temporary secrets used during the
  build, which must not be stored in the resulting image.

how_to_check:
  Docker build check SecretsUsedInArgOrEnv (`docker build --check`) and Hadolint DL3064, which
  report `ENV` and `ARG` keys that look sensitive, so they match names only; Dockle CIS-DI-0010,
  which checks environment variables and credential files, and in practice also flags
  sensitive-looking `KEY=value` words in the final image's history, which is where a build argument
  used by a `RUN` shows up; a secret scanner over the repository.

sources:
- https://docs.docker.com/build/building/secrets/
- https://docs.docker.com/build/metadata/attestations/slsa-provenance/
- https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/
- https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md
- https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
- https://www.cisecurity.org/benchmark/docker
- https://github.com/hadolint/hadolint
