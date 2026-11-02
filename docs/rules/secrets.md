# Secrets

How credentials reach a build without ending up in the image or its metadata.


## DW-SECRET-01: Never pass secrets through ARG, ENV or COPY; mount them

strength: MUST

last_verified: 2026-11-02

statement:
  Give a build its secrets with `RUN --mount=type=secret` (or an SSH mount), never with `ARG`,
  `ENV` or files copied into the image.

why:
  Docker's documentation says build arguments and environment variables are inappropriate for
  passing secrets because they persist in the final image. Secret mounts are not included in
  provenance attestations, while the `max` provenance mode exposes the values of build arguments,
  so a secret passed as an argument can leak through metadata as well as through layers. A secret
  `COPY`ed in ends up in one of the layers.

how_to_check:
  Docker build check SecretsUsedInArgOrEnv (`docker build --check`); a secret scanner over the
  repository and the image; Dockle CIS-DI-0010.

sources:
- https://docs.docker.com/build/building/secrets/
- https://docs.docker.com/build/metadata/attestations/slsa-provenance/
- https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/
- https://www.cisecurity.org/benchmark/docker
