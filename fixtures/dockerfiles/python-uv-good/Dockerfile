# Good: a Python service whose dependencies are installed with uv in a build stage.
# Linted only, never built, so it has no application source next to it. The digests were
# resolved with `docker buildx imagetools inspect` on 2026-11-03 and are not refreshed
# (nothing builds this file, so nothing notices when the tags move).
ARG PYTHON_VERSION=3.14
ARG DEBIAN_RELEASE=trixie

# Hadolint asks every stage for a HEALTHCHECK, but a build stage never runs as a
# container; the runtime stage below has one
# hadolint ignore=DL3057
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_RELEASE}@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966 AS build
# uv is copied from its own image, pinned like the base
COPY --from=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 /uv /usr/local/bin/uv
# use the base image's Python, compile the installed dependencies to .pyc now (the runtime
# filesystem can be read-only; the application code copied later is not compiled), and copy
# from the cache mount instead of hardlinking into it
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app
# dependencies first, from the lockfile only; the download cache stays in the mount
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

FROM python:${PYTHON_VERSION}-slim-${DEBIAN_RELEASE}@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966 AS runtime
# example values: this fixture stands for an imaginary service, not a published image
LABEL org.opencontainers.image.title="example-python-service" \
      org.opencontainers.image.description="Example Python web service" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.authors="Example Team <team@example.com>" \
      org.opencontainers.image.source="https://example.com/example-python-service" \
      org.opencontainers.image.licenses="MIT"
# The slim base keeps apt, dpkg and pip in this stage: a deliberate choice, not an
# oversight. Removing them (DW-BUILD-10) means pruning and flattening, the DW-BUILD-04
# trade-off, or another base (trade-offs §6); see expected-findings.txt
# root owns the code and dependencies; the app user reads them through its group and
# cannot change them
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home app \
    && install -d -o root -g app -m 0750 /app
WORKDIR /app
COPY --from=build --chown=root:app --chmod=u=rwX,g=rX,o= /app/.venv /app/.venv
COPY --chown=root:app --chmod=u=rwX,g=rX,o= src/app ./app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM
# the image's own Python makes the request, so no curl is needed
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
# no init in the image: run with `docker run --init` or an orchestrator equivalent
# (see expected-findings.txt)
ENTRYPOINT ["python", "-m", "app"]
