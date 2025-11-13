# 🧙‍♂️ Dockerfile Wizardry ✨

> _"Any sufficiently advanced Docker optimization is indistinguishable from magic."_

[![GitHub](https://img.shields.io/badge/license-MIT-brightgreen.svg)](https://raw.githubusercontent.com/placheckij/dockerfile-wizardry/main/LICENSE)
[![CI](https://github.com/placheckij/dockerfile-wizardry/actions/workflows/ci.yml/badge.svg)](https://github.com/placheckij/dockerfile-wizardry/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-24.0+-blue.svg)](https://www.docker.com/)
[![Hadolint](https://img.shields.io/badge/dockerfile-linted-success.svg)](https://github.com/hadolint/hadolint)
[![Trivy](https://img.shields.io/badge/security-scanned-success.svg)](https://github.com/aquasecurity/trivy)
[![Docker Image Size](https://img.shields.io/badge/image%20size-~150MB-blue.svg)](https://github.com/placheckij/dockerfile-wizardry)

Welcome to Dockerfile Wizardry - where security meets sorcery! This repository demonstrates production-ready Docker image creation following security best practices, optimization techniques, and industry standards (CIS Docker Benchmark, OWASP) while maintaining compact image sizes.

> ⭐ If you find this project useful, please consider giving it a star! It helps others discover it and motivates further development.

## 🎯 The Spellbook's Purpose

Master the ancient arts of Docker image crafting by learning:

- **🛡️ Security Enchantments** - OWASP and CIS Docker Benchmark spells
- **📦 Size Reduction Magic** - Multi-stage builds and Alpine base images
- **⚡ Performance Potions** - Build caching and layer optimization
- **🔮 Best Practices** - Production-ready incantations

Each "spell" in the Dockerfile is numbered and explained, making it easy to understand and apply these techniques to your own projects!

## 🔐 The Thirteen Security Spells

Our Dockerfile demonstrates 13 essential security and optimization "spells":

### ⚙️ Spell #1: Parameterized Builds
```dockerfile
ARG PYTHON_VERSION=3.12.12
ARG ALPINE_VERSION=3.22
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS base
```
Use ARG for flexible, maintainable version management.

**Source:** [Docker Best Practices - Using Build Arguments](https://docs.docker.com/build/building/best-practices/#using-build-arguments)

### 🏷️ Spell #2: Metadata Labels (OWASP)
```dockerfile
LABEL maintainer="placheckij" \
      version="1.0.0" \
      description="Dockerfile Wizardry - Best Practices Example"
```
Provides image traceability, documentation, and supply chain transparency.

**Source:** [OWASP Docker Security - Image Labeling](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-a-user)

### 🛡️ Spell #3: Minimal Packages (CIS 4.2)
```dockerfile
RUN apk -U upgrade && \
    apk add --no-cache curl tini && \
    rm -rf /var/cache/apk/*
```
Install only what's necessary, upgrade existing packages, and clean up in the same layer.

**Source:** [CIS Docker Benchmark 4.2](https://www.cisecurity.org/benchmark/docker) - Ensure that unnecessary packages are not installed in the container

### 👥 Spell #4: Non-Root User (CIS 4.1)
```dockerfile
RUN addgroup -g 1337 wizards && \
    adduser -D -h /spellbook -G wizards -u 1337 wizard
USER wizard
```
**Never run as root!** Limits the blast radius if a container is compromised.

**Source:** [CIS Docker Benchmark 4.1](https://www.cisecurity.org/benchmark/docker) - Ensure that a user for the container has been created | [OWASP - Run as Non-Root](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user)

### 📚 Spell #5: Poetry Installation (No Cache)
```dockerfile
RUN python -m pip install --no-cache-dir poetry==2.2.*
```
Pin versions and use `--no-cache-dir` to keep layers small.

**Source:** [Docker Best Practices - Minimize Layers](https://docs.docker.com/build/building/best-practices/#minimize-the-number-of-layers)

### ⚡ Spell #6: Layer Caching Magic (CIS 4.9)
```dockerfile
# Copy dependencies FIRST (changes rarely)
COPY ./pyproject.toml ./poetry.lock ./
RUN poetry sync --no-root --no-ansi --no-interaction --no-cache

# Copy code LATER (changes frequently)
COPY ./src/spells ./spells
```
Leverage Docker's layer caching - dependencies won't rebuild when code changes!

**Source:** [CIS Docker Benchmark 4.9](https://www.cisecurity.org/benchmark/docker) - Ensure that COPY is used instead of ADD | [Docker Docs - Leverage Build Cache](https://docs.docker.com/build/building/best-practices/#leverage-build-cache)

### 🏗️ Spell #7: Multi-Stage Builds
```dockerfile
FROM base AS poetry
# Install dependencies here

FROM base AS runtime
COPY --from=poetry /spellbook/.venv /spellbook/.venv
```
Discard build tools, keep only runtime artifacts. **50-70% size reduction!**

**Source:** [Docker Best Practices - Multi-stage Builds](https://docs.docker.com/build/building/best-practices/#use-multi-stage-builds)

### 🎯 Spell #8: Selective File Copying (CIS 4.9)
```dockerfile
# ✅ Copy ONLY what's needed
COPY ./src/spells ./spells
COPY ./src/potions ./potions

# ❌ DON'T copy tests/, docs/, .git/, etc.
```
Prevents accidental secrets and reduces image size. Check `src/tests/` and `src/docs/` - they're excluded!

**Source:** [CIS Docker Benchmark 4.9](https://www.cisecurity.org/benchmark/docker) - Use COPY instead of ADD | [OWASP - Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-6-do-not-store-secrets-in-images)

### 🔒 Spell #9: Restrictive Permissions (OWASP)
```dockerfile
RUN chmod -R 550 /spellbook/spells && \
    chmod 440 /spellbook/main.py
```
Make files read-only and executable only where needed - prevents tampering.

**Source:** [OWASP - Filesystem Permissions](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only)

### 🔌 Spell #10: Port Declaration
```dockerfile
EXPOSE 8000
```
**Why?** While EXPOSE doesn't actually publish the port, it serves three critical purposes:
1. **Documentation** - Makes it clear which port the app uses without reading the code
2. **Security Scanning** - Tools like Trivy and Snyk use this to verify port configuration
3. **Container Orchestration** - Helps K8s, Docker Compose, and other tools auto-configure networking

Note: You still need `-p 8000:8000` when running, but EXPOSE acts as the "contract" between image and runtime.

**Source:** [Dockerfile Reference - EXPOSE](https://docs.docker.com/reference/dockerfile/#expose)

### 💚 Spell #11: Health Checks (CIS 4.7)
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8000/health || exit 1
```
Enables automatic healing - Docker/K8s will restart unhealthy containers.

**Source:** [CIS Docker Benchmark 4.7](https://www.cisecurity.org/benchmark/docker) - Ensure that HEALTHCHECK instructions have been added | [Docker Docs - HEALTHCHECK](https://docs.docker.com/reference/dockerfile/#healthcheck)

### 🛑 Spell #12: Graceful Shutdown
```dockerfile
STOPSIGNAL SIGTERM
```
Ensures proper shutdown signal for cleanup operations.

**Source:** [Docker Best Practices - Signal Handling](https://docs.docker.com/develop/dev-best-practices/#how-to-keep-your-images-small) | [Dockerfile Reference - STOPSIGNAL](https://docs.docker.com/reference/dockerfile/#stopsignal)

### 🔄 Spell #13: Signal Handling with Tini (OWASP)
```dockerfile
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/spellbook/.venv/bin/uvicorn", "main:app", ...]
```
Prevents zombie processes and ensures graceful shutdowns. Essential for PID 1!

**Source:** [OWASP - Use Init Process](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-9-use-static-analysis-tools) | [Tini Documentation](https://github.com/krallin/tini)

## 📦 Image Optimization Techniques

### Multi-Stage Builds
The example uses three stages:
1. **base**: Common dependencies and user setup
2. **poetry**: Dependency installation (discarded in final image)
3. **runtime**: Minimal production image with only necessary artifacts

This approach can reduce final image size by 50-70% compared to single-stage builds.

### Alpine Linux Base
```dockerfile
FROM python:3.12.12-alpine3.22 AS base
```
Alpine images are typically 5-10x smaller than Debian-based alternatives.

### Layer Optimization
- Combine RUN commands to reduce layers
- Use `--no-cache` flags to prevent caching package indexes
- Clean up temporary files in the same layer they're created

### Dependency Caching
```dockerfile
# Copy dependency files first for better caching
COPY ./pyproject.toml ./poetry.lock ./
RUN poetry sync --no-root --no-ansi --no-interaction --no-cache
```
Leverages Docker's layer caching to avoid reinstalling dependencies on code changes.

## 🚀 Tips and Tricks

### 1. Use Specific Tags
❌ **Don't**: `FROM python:3.12`  
✅ **Do**: `FROM python:3.12.12-alpine3.22`

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
docker scan myimage:latest
# or
trivy image myimage:latest
```

## 📊 Benchmark Results

Example size comparison for a Python application:

| Approach | Image Size | Build Time |
|----------|-----------|------------|
| Single-stage (Debian) | 1.2 GB | 3m 45s |
| Single-stage (Alpine) | 450 MB | 2m 30s |
| Multi-stage (Alpine) | 180 MB | 2m 15s |

## � Project Structure

```
dockerfile-wizardry/
├── Dockerfile              # 🧙‍♂️ The main spellbook - study this!
├── .dockerignore          # 🫥 Invisibility cloak for unwanted files
├── pyproject.toml         # 📦 Python dependencies
├── poetry.lock            # 🔒 Locked versions
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

**Notice**: Tests and docs are excluded from the container - this is **Spell #7** in action!

## 🛠️ Usage & Learning Path

### 1️⃣ Study the Spellbook
```bash
git clone https://github.com/placheckij/dockerfile-wizardry.git
cd dockerfile-wizardry
```

Open `Dockerfile` and read through each numbered spell (1-10). Each has detailed comments explaining the "why" and "how".

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
docker run -p 8000:8000 wizardry:latest

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
  --cap-add=NET_BIND_SERVICE \
  --security-opt=no-new-privileges:true \
  --memory=512m \
  --cpus=1.0 \
  -p 8000:8000 \
  wizardry:latest
```

See **[RUNTIME_SECURITY.md](RUNTIME_SECURITY.md)** for comprehensive production security guidelines!

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
docker build -f Dockerfile.single-stage -t wizardry:bloated .
docker images | grep wizardry
```

### Measure the Impact
```bash
# Time the build
time docker build -t wizardry:latest .

# Change only spellbook/main.py and rebuild - notice it's fast!
echo "# comment" >> spellbook/main.py
time docker build -t wizardry:latest .
# Dependencies aren't reinstalled - that's Spell #5!
```

## 💬 Support & Contact

If you need assistance, have questions, or want to report issues:

- **GitHub Discussions**: [Join the discussion](https://github.com/placheckij/dockerfile-wizardry/discussions) - Ask questions, share ideas, or discuss implementation
- **GitHub Issues**: [Report bugs or request features](https://github.com/placheckij/dockerfile-wizardry/issues)
- **Email**: [jakub@plachecki.dev](mailto:jakub@plachecki.dev)
- **LinkedIn**: [Connect with me](https://www.linkedin.com/in/jakubplachecki)

Contributions, feedback, and suggestions are welcome!

##  License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Third-Party Components

This project incorporates the following open-source components:

**Docker Base Images:**
- [Python Official Docker Images](https://hub.docker.com/_/python) - PSF License
- [Alpine Linux](https://alpinelinux.org/) - various open source licenses

**Python Dependencies:**
- [FastAPI](https://fastapi.tiangolo.com/) - MIT License
- [Uvicorn](https://www.uvicorn.org/) - BSD-3-Clause License
- [Poetry](https://python-poetry.org/) - MIT License

**Build & Security Tools:**
- [Tini](https://github.com/krallin/tini) - MIT License
- [Hadolint](https://github.com/hadolint/hadolint) - GPL-3.0 License
- [Trivy](https://github.com/aquasecurity/trivy) - Apache License 2.0

All third-party components are used in accordance with their respective licenses.

---

**Disclaimer**: Always adapt these practices to your specific security requirements and compliance needs. Regular security audits and vulnerability scanning are essential.
