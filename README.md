# 🧙‍♂️ Dockerfile Wizardry ✨

> _"Any sufficiently advanced Docker optimization is indistinguishable from magic."_

[![GitHub](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://raw.githubusercontent.com/placheckij/dockerfile-wizardry/main/LICENSE)
[![CI](https://github.com/placheckij/dockerfile-wizardry/actions/workflows/ci.yml/badge.svg)](https://github.com/placheckij/dockerfile-wizardry/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-24.0+-blue.svg)](https://www.docker.com/)
[![Hadolint](https://img.shields.io/badge/dockerfile-linted-success.svg)](https://github.com/hadolint/hadolint)
[![Trivy](https://img.shields.io/badge/security-scanned-success.svg)](https://github.com/aquasecurity/trivy)
[![Docker Image Size](https://img.shields.io/badge/image%20size-~81MB-blue.svg)](https://github.com/placheckij/dockerfile-wizardry)

Welcome to Dockerfile Wizardry - where security meets sorcery! This repository demonstrates production-ready Docker image creation following security best practices, optimization techniques, and industry standards (CIS Docker Benchmark, OWASP) while maintaining compact image sizes.

> ⭐ If you find this project useful, please consider giving it a star! It helps others discover it and motivates further development.

## 🎯 The Spellbook's Purpose

Master the ancient arts of Docker image crafting by learning:

- **🛡️ Security Enchantments** - OWASP and CIS Docker Benchmark spells
- **📦 Size Reduction Magic** - Multi-stage builds and Alpine base images
- **⚡ Performance Potions** - Build caching and layer optimization
- **🔮 Best Practices** - Production-ready incantations

Each "spell" in the Dockerfile is numbered and explained, making it easy to understand and apply these techniques to your own projects!

## 🔐 The Fourteen Security Spells

Our Dockerfile demonstrates 14 essential security and optimization "spells". CIS control numbers refer to the **CIS Docker Benchmark v1.9.0** (the numbering changed between versions, so older articles may differ); a monthly CI job warns when a newer version or an updated OWASP cheat sheet appears.

### ⚙️ Spell #1: Parameterized Builds, Pinned by Digest (CIS 4.2, 5.28)
```dockerfile
ARG PYTHON_VERSION=3.14.10
ARG ALPINE_VERSION=3.24
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION}@sha256:eb2c6265... AS base
```
Use ARG for flexible, maintainable version management. The tag says what you intend; the `@sha256:` digest says exactly which bytes you get, so a republished or tampered tag can't change your build.

**Pinning freezes the base image**, so patches stop arriving on their own. A weekly CI job compares the pinned digest with what the tag points to today and fails - with the new digest in the log - when the tag has moved. Bump the digest, rebuild, run the tests.

**Source:** [CIS Docker Benchmark 4.2](https://www.cisecurity.org/benchmark/docker) - Ensure that containers use only trusted base images | [CIS Docker Benchmark 5.28](https://www.cisecurity.org/benchmark/docker) - Ensure that Docker commands always make use of the latest version of their image (its remediation calls for version pinning of base images) | [Dockerfile reference - Understand how ARG and FROM interact](https://docs.docker.com/reference/dockerfile/#understand-how-arg-and-from-interact) | [Docker Best Practices - Pin base image versions](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions)

### 🏷️ Spell #2: Metadata Labels
```dockerfile
LABEL maintainer="placheckij" \
      version="1.0.0" \
      description="Dockerfile Wizardry - Best Practices Example"
```
Provides image traceability, documentation, and supply chain transparency.

**Source:** [OCI Image Spec - Pre-Defined Annotation Keys](https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys) | [Docker Docs - Labels](https://docs.docker.com/reference/dockerfile/#label)

### 🛡️ Spell #3: Minimal Packages (CIS 4.3, 4.6)
```dockerfile
RUN apk -U upgrade && \
    apk add --no-cache tini && \
    rm -rf /var/cache/apk/*
```
Install only what's necessary, upgrade existing packages, and clean up in the same layer.

Package versions are **not** pinned, on purpose: OWASP Rule 9 lists pinned OS packages as a lint check, but Alpine's repositories carry only the current version of each package per release, so a pin breaks the build as soon as a fix is published. The weekly no-cache rebuild and the base-image digest check (Spell #1) are what keep packages fresh instead.

`apk -U upgrade` and `apk add` share one `RUN`, so the package index can't be cached on its own and then go stale before the install runs (CIS 4.6). That is a narrower guarantee than "always up to date": Docker still reuses the **whole** `RUN` layer from its build cache as long as the instruction and the base image digest are unchanged, so new patches only arrive when the cache is invalidated - `docker build --no-cache --pull`, a new base digest (Spell #1), or an edit to the `RUN`. That is why this repo's weekly CI run builds with `--no-cache`.

**Source:** [CIS Docker Benchmark 4.3](https://www.cisecurity.org/benchmark/docker) - Ensure that unnecessary packages are not installed in the container | [CIS Docker Benchmark 4.6](https://www.cisecurity.org/benchmark/docker) - Ensure update instructions are not used alone in Dockerfiles

### 👥 Spell #4: Non-Root User (CIS 4.1)
```dockerfile
RUN addgroup -g 1337 wizards && \
    adduser -D -h /spellbook -G wizards -u 1337 wizard
USER wizard
```
**Never run as root!** Limits the blast radius if a container is compromised.

**Source:** [CIS Docker Benchmark 4.1](https://www.cisecurity.org/benchmark/docker) - Ensure that a user for the container has been created | [OWASP - Run as Non-Root](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user)

### 📚 Spell #5: uv Installation (No Cache)
```dockerfile
RUN python -m pip install --no-cache-dir uv==0.13.6
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1
```
Pin versions and use `--no-cache-dir` to keep layers small. The `UV_*` settings make uv use the Python already in the base image (never download one), compile `.pyc` files at install time, and keep no download cache.

**Why compile bytecode?** uv doesn't by default, and the runtime filesystem can be read-only (see [RUNTIME_SECURITY.md](RUNTIME_SECURITY.md)), so Python could never write the `.pyc` files itself and would recompile every module on every start. Measured here: dependency import time 644 ms → 358 ms and cold start to `/health` about 1.3 s → 0.8 s, for about 8 MB more image (81 MB vs 73 MB). If size matters more than start-up time, set `UV_COMPILE_BYTECODE=0`.

**Reproducible bytecode.** By default `.pyc` headers embed the install time, so two builds of the same commit produce different bytecode. Setting `SOURCE_DATE_EPOCH` makes Python write hash-based `.pyc` files instead (only its presence matters; the value never ends up in the files). Two independent `--no-cache` builds then give a byte-identical `site-packages`, with no measurable change in import time. Neither kind of `.pyc` authenticates the bytecode itself - what protects it from tampering is the read-only filesystem and the permissions in Spell #9.

**Source:** [Docker Best Practices - RUN](https://docs.docker.com/build/building/best-practices/#run) (clean up package caches in the same layer)

### ⚡ Spell #6: Layer Caching Magic (CIS 4.8)
```dockerfile
# Copy dependencies FIRST (changes rarely)
COPY ./pyproject.toml ./uv.lock ./
RUN uv sync --locked --no-dev

# Copy code LATER (changes frequently)
COPY ./spellbook/spells ./spells
```
Leverage Docker's layer caching - dependencies won't rebuild when code changes!

`--no-dev` installs runtime dependencies only. Without it, `uv sync` also installs the dev group (pytest, ruff, ...) into the image - in this repo that's about 39 MB of tooling you never run in production (120 MB → 81 MB). `--locked` makes the build fail if `uv.lock` is out of date, and uv verifies every download against the hashes in the lockfile.

**Source:** [CIS Docker Benchmark 4.8](https://www.cisecurity.org/benchmark/docker) - Ensure that COPY is used instead of ADD in Dockerfiles | [Docker Docs - Leverage Build Cache](https://docs.docker.com/build/building/best-practices/#leverage-build-cache)

### 🏗️ Spell #7: Multi-Stage Builds
```dockerfile
FROM base AS uv
# Install dependencies here

FROM base AS runtime
COPY --from=uv /spellbook/.venv /spellbook/.venv
```
Discard build tools, keep only runtime artifacts. **50-70% size reduction!**

**Source:** [Docker Best Practices - Multi-stage Builds](https://docs.docker.com/build/building/best-practices/#use-multi-stage-builds)

### 🎯 Spell #8: Selective File Copying (CIS 4.8, 4.9)
```dockerfile
# ✅ Copy ONLY what's needed
COPY ./spellbook/spells ./spells
COPY ./spellbook/potions ./potions

# ❌ DON'T copy tests/, docs/, .git/, etc.
```
Prevents accidental secrets and reduces image size. Check `spellbook/tests/` and `spellbook/docs/` - they're excluded!

**Source:** [CIS Docker Benchmark 4.8](https://www.cisecurity.org/benchmark/docker) - Ensure that COPY is used instead of ADD in Dockerfiles | [CIS Docker Benchmark 4.9](https://www.cisecurity.org/benchmark/docker) - Ensure secrets are not stored in Dockerfiles | [OWASP - Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-12-utilize-docker-secrets-for-sensitive-data-management)

### 🔒 Spell #9: Restrictive Permissions
```dockerfile
RUN chown -R root:wizards /spellbook && \
    chmod -R g-w,o-rwx /spellbook && \
    chmod -R 550 /spellbook/spells && \
    chmod 440 /spellbook/main.py
```
Make files read-only and executable only where needed - prevents tampering.

**The app user must not own what it runs.** An owner can always `chmod` its own files back to writable, and a writable directory lets entries be renamed or replaced. So the code, the dependencies and `/spellbook` itself are owned by `root` and reachable by the `wizard` user only through the read-only `wizards` group. This holds even without `--read-only`; CI checks that the app user can't write, `chmod` or replace anything under `/spellbook`. The runtime read-only filesystem in [RUNTIME_SECURITY.md](RUNTIME_SECURITY.md) remains the primary control.

**Source:** [OWASP Rule #8 - Set filesystem and volumes to read-only](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only) (this spell is its build-time side; the `--read-only` runtime flag is the other)

### ✂️ Spell #10: Prune and Flatten (CIS 4.3)
```dockerfile
FROM base AS pruned
# ... build the image, then remove what the app never runs:
RUN /usr/local/bin/python -m pip uninstall -y pip && \
    rm -rf /usr/local/include /usr/local/lib/python3.14/ensurepip ... && \
    rm -f /usr/bin/wget /usr/bin/nc /usr/bin/telnet ... && \
    rm -rf /sbin/apk /lib/libapk* /etc/apk   # keep /lib/apk/db for scanners

FROM scratch AS runtime
COPY --from=pruned / /
# scratch has no metadata: declare ENV, LABEL, USER, WORKDIR, ... again
```
Removes the package managers (`pip`, `apk`), C headers, `ensurepip`, IDLE/Tk, and network tools (`wget`, `nc`, `telnet`, ...), and drops `curl` entirely by using Python for the health check.

**Why flatten?** Deleting files in a later layer saves nothing: they stay in the layers below and anyone who pulls the image can still extract them. Copying the pruned filesystem into a fresh `scratch` image removes them for real - here that's 94 MB → 81 MB, and `apk`, `curl` and `Python.h` no longer appear in any layer.

**This is defense in depth, not a barrier.** Python and the busybox shell are still in the image, so an attacker with code execution can still download things. Rely on the runtime flags in [RUNTIME_SECURITY.md](RUNTIME_SECURITY.md) (read-only filesystem, dropped capabilities) for that. Removing the shell as well is possible, but it breaks `docker exec ... sh` debugging and any CI check that runs `ls` or `id` inside the container.

**Source:** [CIS Docker Benchmark 4.3](https://www.cisecurity.org/benchmark/docker) - Ensure that unnecessary packages are not installed in the container | [Docker Docs - Multi-stage builds](https://docs.docker.com/build/building/multi-stage/) | [Docker Docs - Create a minimal base image using scratch](https://docs.docker.com/build/building/base-images/#create-a-minimal-base-image-using-scratch)

### 🔌 Spell #11: Port Declaration
```dockerfile
EXPOSE 8000
```
**Why?** While EXPOSE doesn't actually publish the port, it serves three critical purposes:
1. **Documentation** - Makes it clear which port the app uses without reading the code
2. **Security Scanning** - Tools like Trivy and Snyk use this to verify port configuration
3. **Container Orchestration** - Helps K8s, Docker Compose, and other tools auto-configure networking

Note: You still need `-p` when running - publish it on loopback, `-p 127.0.0.1:8000:8000`, because a bare `-p 8000:8000` opens the port on all interfaces and Docker bypasses host firewalls such as UFW (OWASP Rule 5a). EXPOSE acts as the "contract" between image and runtime.

**Source:** [Dockerfile Reference - EXPOSE](https://docs.docker.com/reference/dockerfile/#expose)

### 💚 Spell #12: Health Checks (CIS 4.5)
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
    CMD ["/spellbook/.venv/bin/python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=2)"]
```
Enables automatic healing - Docker/K8s will restart unhealthy containers. The check uses Python (already in the image) instead of `curl`, so `curl` and its libraries can be left out. A failed request raises, Python exits non-zero, and Docker marks the container unhealthy.

**Source:** [CIS Docker Benchmark 4.5](https://www.cisecurity.org/benchmark/docker) - Ensure that HEALTHCHECK instructions have been added | [Docker Docs - HEALTHCHECK](https://docs.docker.com/reference/dockerfile/#healthcheck)

### 🛑 Spell #13: Graceful Shutdown
```dockerfile
STOPSIGNAL SIGTERM
```
Ensures proper shutdown signal for cleanup operations.

**Source:** [Dockerfile Reference - STOPSIGNAL](https://docs.docker.com/reference/dockerfile/#stopsignal)

### 🔄 Spell #14: Signal Handling with Tini
```dockerfile
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/spellbook/.venv/bin/uvicorn", "main:app", ...]
```
Prevents zombie processes and ensures graceful shutdowns. Essential for PID 1!

**Source:** [Docker Docs - `docker run --init`](https://docs.docker.com/reference/cli/docker/container/run/#init) | [Tini Documentation](https://github.com/krallin/tini)

## 📦 Image Optimization Techniques

### Multi-Stage Builds
The example uses three stages:
1. **base**: Common dependencies and user setup
2. **uv**: Dependency installation (discarded in final image)
3. **runtime**: Minimal production image with only necessary artifacts

This approach can reduce final image size by 50-70% compared to single-stage builds.

### Alpine Linux Base
```dockerfile
FROM python:3.14.10-alpine3.24 AS base
```
Alpine images are typically 5-10x smaller than Debian-based alternatives.

### Layer Optimization
- Combine RUN commands to reduce layers
- Use `--no-cache` flags to prevent caching package indexes
- Clean up temporary files in the same layer they're created

### Dependency Caching
```dockerfile
# Copy dependency files first for better caching
COPY ./pyproject.toml ./uv.lock ./
RUN uv sync --locked --no-dev
```
Leverages Docker's layer caching to avoid reinstalling dependencies on code changes.

## 🚀 Tips and Tricks

### 1. Use Specific Tags
❌ **Don't**: `FROM python:3.14`  
✅ **Do**: `FROM python:3.14.10-alpine3.24@sha256:<digest>` (pin the digest too - see Spell #1)

Ensures reproducible builds and prevents unexpected changes.

### 2. Leverage .dockerignore
Create a `.dockerignore` file to exclude unnecessary files:
```
.git
.gitignore
.env
*.md
tests/
__pycache__/
*.pyc
.pytest_cache
```

### 3. Order Matters
Place least-changing instructions first:
```dockerfile
# 1. Base image and system packages (rarely change)
# 2. Dependencies (change occasionally)
# 3. Application code (changes frequently)
```

### 4. Use BuildKit
Enable Docker BuildKit for improved caching and parallel builds:
```bash
DOCKER_BUILDKIT=1 docker build -t myapp .
```

### 5. Scan for Vulnerabilities
```bash
docker scout cves myimage:latest
# or
trivy image myimage:latest
```

## 📊 Benchmark Results

Example size and build time comparison for a Python application from this repo, all done on the same hardware/os configuration, no caching (corresponding Dockerfiles can be found in the repo):

| Approach | Image Size | Build Time (no-cache) |
|----------|-----------|----------------------|
| Single-stage (python:3.14-slim) | 253 MB | 5s |
| Single-stage (python:3.14.10-alpine3.24) | 157 MB | 5s |
| Multi-stage, pruned and flattened (python:3.14.10-alpine3.24) | 81 MB | 10s |

Build times vary from run to run and with the machine, so compare the sizes, not the seconds.

The single-stage files install every dependency group, as a naive Dockerfile would. The multi-stage image installs runtime dependencies only (`uv sync --no-dev`), which alone accounts for about 39 MB of the multi-stage image (120 MB → 81 MB).

## 📁 Project Structure

```
dockerfile-wizardry/
├── Dockerfile              # 🧙‍♂️ The main spellbook - study this!
├── Dockerfile.single-stage-slim    # 📉 Benchmark baseline (Debian slim)
├── Dockerfile.single-stage-alpine  # 📉 Benchmark baseline (Alpine)
├── .dockerignore          # 🫥 Invisibility cloak for unwanted files
├── examples/              # 🧪 Hardened Compose + Kubernetes examples, smoke-tested in CI
│   ├── compose.yaml
│   ├── namespace.yaml     #    enforces the Pod Security "restricted" standard
│   └── pod.yaml
├── pyproject.toml         # 📦 Python dependencies
├── uv.lock                # 🔒 Locked versions
└── spellbook/
    ├── main.py            # ✅ Copied to container
    ├── spells/            # ✅ Copied to container
    │   └── incantations.py
    ├── potions/           # ✅ Copied to container
    │   └── brewing.py
    ├── enchantments/      # ✅ Copied to container
    │   └── protective.py
    ├── tests/             # ❌ NOT copied (excluded!)
    │   ├── test_spells.py
    │   └── test_potions.py
    └── docs/              # ❌ NOT copied (excluded!)
        └── ARCHITECTURE.md
```

**Notice**: Tests and docs are excluded from the container - this is **Spell #8** in action!

## 🛠️ Usage & Learning Path

### 1️⃣ Study the Spellbook
```bash
git clone https://github.com/placheckij/dockerfile-wizardry.git
cd dockerfile-wizardry
```

Open `Dockerfile` and read through each numbered spell (1-14). Each has detailed comments explaining the "why" and "how".

### 2️⃣ Build the Image
```bash
# Enable BuildKit for better caching
export DOCKER_BUILDKIT=1

# Cast the build spell
docker build -t wizardry:latest .

# Check the magic - note the compact size!
docker images wizardry:latest
```

### 3️⃣ Run the Container
```bash
# Run the magical application
docker run -p 127.0.0.1:8000:8000 wizardry:latest

# Visit the endpoints
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:8000/spell/fireball
```

### 4️⃣ Verify Security
```bash
# Check that it's running as non-root user
docker run --rm wizardry:latest id
# Should show: uid=1337(wizard) gid=1337(wizards)

# Verify file permissions
docker run --rm wizardry:latest ls -la /spellbook/

# Scan for vulnerabilities
docker scout cves wizardry:latest
# or
trivy image wizardry:latest
```

### 5️⃣ Production Deployment
For production, use additional runtime security flags:
```bash
docker run -d \
  --name wizardry \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=100m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=512m \
  --cpus=1.0 \
  --pids-limit=100 \
  -p 127.0.0.1:8000:8000 \
  --restart=on-failure:5 \
  wizardry:latest
```

See **[RUNTIME_SECURITY.md](RUNTIME_SECURITY.md)** for comprehensive production security guidelines, and [`examples/`](examples/) for a ready-to-run Docker Compose file and Kubernetes Pod that apply them (both are run for real in CI)!

## 🛡️ What CI Checks

Beyond building and testing, the workflow guards the properties this repo claims:
- **Weekly rebuild without cache** and re-scan, so new CVEs and OS patches surface without a push (CIS 4.4).
- **Base image digest freshness** - fails when the pinned digest is stale (Spell #1).
- **Trivy** fails on HIGH/CRITICAL findings, and an assertion makes sure it can actually *see* the image's OS and Python packages (a scanner that sees nothing passes vacuously).
- **Secret scan** of the repository (CIS 4.9).
- **No setuid/setgid files** in the image (CIS 4.7).
- **Read-only application files**: the app user can't write to, `chmod` or replace its code and dependencies (Spell #9).
- **Example smoke tests**: `examples/compose.yaml` is started and its settings verified with `docker inspect`; `examples/namespace.yaml` + `pod.yaml` are applied to a throwaway `kind` cluster, where the script checks what Kubernetes actually enforced (user, capabilities, seccomp, read-only filesystem) and the documented random-UID outcomes. Both run on changes to the examples or the image, and weekly.
- **shellcheck** on the smoke-test scripts.
- **Monthly standards watch** for new CIS Benchmark versions and OWASP cheat sheet changes.

## 🧭 Deliberately Not Included

**Image signing and SBOM attestation (CIS 4.11).** CIS 4.11 asks that signed artifacts are validated. This repo does not sign images or publish an SBOM, on purpose: CI builds the image but never pushes it to a registry, so there is nothing for consumers to verify yet. When you publish it, add keyless signing with [cosign](https://docs.sigstore.dev/cosign/overview/) in the publish workflow (GitHub OIDC identity, no long-lived keys) plus an SBOM attestation, and verify with `cosign verify` at deploy time. It is listed here so the gap is a known choice rather than an oversight.

## 📚 References

- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [OWASP Docker Security](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Dockerfile Reference](https://docs.docker.com/engine/reference/builder/)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- **[Runtime Security Guide](RUNTIME_SECURITY.md)** - Production deployment security

## 🎓 Advanced Wizardry

### Inspect the Build Layers
```bash
# See the multi-stage magic
docker history wizardry:latest

# Compare with a single-stage build
docker build -f Dockerfile.single-stage-alpine -t wizardry:bloated .
docker images | grep wizardry
```

### Measure the Impact
```bash
# Time the build
time docker build -t wizardry:latest .

# Change only spellbook/main.py and rebuild - notice it's fast!
echo "# comment" >> spellbook/main.py
time docker build -t wizardry:latest .
# Dependencies aren't reinstalled - that's Spell #6!
```

## 💬 Support & Contact

If you need assistance, have questions, or want to report issues:

- **GitHub Discussions**: [Join the discussion](https://github.com/placheckij/dockerfile-wizardry/discussions) - Ask questions, share ideas, or discuss implementation
- **GitHub Issues**: [Report bugs or request features](https://github.com/placheckij/dockerfile-wizardry/issues)
- **Email**: [jakub@plachecki.dev](mailto:jakub@plachecki.dev)
- **LinkedIn**: [Connect with me](https://www.linkedin.com/in/jakubplachecki)

Contributions, feedback, and suggestions are welcome!

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Third-Party Components

This project incorporates the following open-source components:

**Docker Base Images:**
- [Python Official Docker Images](https://hub.docker.com/_/python) - PSF License
- [Alpine Linux](https://alpinelinux.org/) - various open source licenses

**Python Dependencies:**
- [FastAPI](https://fastapi.tiangolo.com/) - MIT License
- [Uvicorn](https://uvicorn.dev/) - BSD-3-Clause License
- [uv](https://docs.astral.sh/uv/) - MIT or Apache-2.0 License

**Build & Security Tools:**
- [Tini](https://github.com/krallin/tini) - MIT License
- [Hadolint](https://github.com/hadolint/hadolint) - GPL-3.0 License
- [Trivy](https://github.com/aquasecurity/trivy) - Apache License 2.0

All third-party components are used in accordance with their respective licenses.

---

**Disclaimer**: Always adapt these practices to your specific security requirements and compliance needs. Regular security audits and vulnerability scanning are essential.
