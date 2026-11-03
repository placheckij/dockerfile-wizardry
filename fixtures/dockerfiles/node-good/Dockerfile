# Good: a Node.js service with production dependencies installed in a build stage.
# Linted only, never built, so it has no application source next to it. The digest was
# resolved with `docker buildx imagetools inspect` on 2026-11-03 and is not refreshed
# (nothing builds this file, so nothing notices when the tag moves).
ARG NODE_VERSION=24
ARG NODE_VARIANT=slim

# Hadolint asks every stage for a HEALTHCHECK, but a build stage never runs as a
# container; the runtime stage below has one
# hadolint ignore=DL3057
FROM node:${NODE_VERSION}-${NODE_VARIANT}@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS build
WORKDIR /app
# dependencies first, from the lockfile only; npm's download cache stays in the mount
RUN --mount=type=cache,target=/root/.npm \
    --mount=type=bind,source=package.json,target=package.json \
    --mount=type=bind,source=package-lock.json,target=package-lock.json \
    npm ci --omit=dev

FROM node:${NODE_VERSION}-${NODE_VARIANT}@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c AS runtime
ENV NODE_ENV=production
WORKDIR /app
# root owns the code and dependencies; the app user can read but not change them
COPY --from=build /app/node_modules ./node_modules
COPY package.json ./
COPY src ./src
# uid and gid 1000 are the `node` user the official image creates
USER 1000:1000
EXPOSE 3000
STOPSIGNAL SIGTERM
# the image's own Node.js makes the request (fetch is built in), so no curl is needed
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/health').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
# run with `docker run --init` (or an orchestrator equivalent) for an init as PID 1
ENTRYPOINT ["node", "src/server.js"]
