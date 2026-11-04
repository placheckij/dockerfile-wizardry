# Good: a statically linked Go binary on distroless static, cross-compiled on the build
# platform. Linted only, never built, so it has no application source next to it. The
# digests were resolved with `docker buildx imagetools inspect` on 2026-11-03 and are not
# refreshed (nothing builds this file, so nothing notices when the tags move).
ARG GO_VERSION=1.26
ARG DEBIAN_RELEASE=trixie

# Hadolint asks every stage for a HEALTHCHECK, but a build stage never runs as a
# container
# hadolint ignore=DL3057
FROM --platform=$BUILDPLATFORM golang:${GO_VERSION}-${DEBIAN_RELEASE}@sha256:a050dcceee6eb9bf110151662dfac7662f3bec40927c7dee48731e3d92083d42 AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
# modules first, from go.mod and go.sum only; downloads stay in the cache mount
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=bind,source=go.mod,target=go.mod \
    --mount=type=bind,source=go.sum,target=go.sum \
    go mod download
# the source is mounted, not copied, since only the binary is kept
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=bind,target=. \
    CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -o /out/app ./cmd/app

FROM gcr.io/distroless/static-debian13:nonroot@sha256:25ac8f0c3b2334a9eb05452266bd4697864a8c8ef0ef71e5e6480d7f92868329 AS runtime
# example values: this fixture stands for an imaginary service, not a published image
LABEL org.opencontainers.image.title="example-go-service" \
      org.opencontainers.image.description="Example Go web service" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.authors="Example Team <team@example.com>" \
      org.opencontainers.image.source="https://example.com/example-go-service" \
      org.opencontainers.image.licenses="MIT"
# root owns the binary; the nonroot group can run it but not change it
COPY --from=build --chown=0:65532 --chmod=0550 /out/app /app
# 65532 is the `nonroot` user distroless images define
USER 65532:65532
EXPOSE 8080
STOPSIGNAL SIGTERM
# no HEALTHCHECK: distroless static has no shell or curl to run one (see expected-findings.txt)
# no init in the image: run with `docker run --init` or an orchestrator equivalent
# (see expected-findings.txt)
ENTRYPOINT ["/app"]
