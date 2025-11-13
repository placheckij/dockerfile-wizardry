# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                    🧙‍♂️ DOCKERFILE WIZARDRY 🧙‍♂️                          ║
# ║         Security-hardened, optimized Docker image creation           ║
# ║    Following CIS Benchmark & OWASP best practices with a touch      ║
# ║                          of magic! ✨                                 ║
# ╚═══════════════════════════════════════════════════════════════════════╝

# 🎯 Spell #11: Parameterized Base Image (Build Flexibility)
# Use ARG to make versions configurable and easier to update
ARG PYTHON_VERSION=3.12.12
ARG ALPINE_VERSION=3.22
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS base

# 🏷️ Spell #1: Metadata Labels (OWASP recommendation)
LABEL maintainer="placheckij" \
      version="1.0.0" \
      description="Dockerfile Wizardry - Best Practices Example" \
      org.opencontainers.image.source="https://github.com/placheckij/dockerfile-wizardry"

USER root
# 🛡️ Spell #2: Minimal Packages & Non-Root User (CIS 4.2)
# Cast everything in a single layer to reduce image size
RUN apk -U upgrade && \
    apk add --no-cache curl tini && \
    rm -rf /var/cache/apk/* && \
    addgroup -g 1337 wizards && \
    adduser -D -h /spellbook -G wizards -u 1337 wizard

ENV PYTHONUNBUFFERED=true

# 🔐 Spell #3: Switch to Non-Root User (CIS 4.1, OWASP)
# Never run as root - limit the blast radius of potential attacks
USER wizard
WORKDIR /spellbook

# ═══════════════════════════════════════════════════════════════════════
# 📚 Stage 2: The Poetry Grimoire - Dependency Installation
# ═══════════════════════════════════════════════════════════════════════
FROM base AS poetry
# 📦 Spell #4: Install Poetry (no cache = smaller layers)
RUN python -m pip install --no-cache-dir poetry==2.2.*
ENV PATH=/spellbook/.local/bin:$PATH \
    POETRY_VIRTUALENVS_IN_PROJECT=true

# 🎯 Spell #5: Copy ONLY Dependency Files First (CIS 4.9)
# This leverages Docker's layer caching - code changes won't rebuild dependencies
COPY --chown=wizard:wizards ./pyproject.toml ./poetry.lock ./
RUN /spellbook/.local/bin/poetry sync --no-root --no-ansi --no-interaction --no-cache

# ═══════════════════════════════════════════════════════════════════════
# 🚀 Stage 3: The Final Incantation - Runtime Image
# ═══════════════════════════════════════════════════════════════════════
FROM base AS runtime
ENV PATH=/spellbook/.venv/bin:$PATH

# 🔮 Spell #6: Copy Virtual Environment from Poetry Stage
# Multi-stage magic - keep only what we need, discard the rest
COPY --chown=wizard:wizards --from=poetry /spellbook/.venv /spellbook/.venv

# ✨ Spell #7: Copy ONLY Required Application Files (CIS 4.9)
# Notice: We DON'T copy tests/, docs/, .git/, or other unnecessary files
# This keeps the image lean and prevents accidental secret inclusion
COPY --chown=wizard:wizards ./spellbook/spells ./spells
COPY --chown=wizard:wizards ./spellbook/potions ./potions
COPY --chown=wizard:wizards ./spellbook/enchantments ./enchantments
COPY --chown=wizard:wizards ./spellbook/main.py ./
COPY --chown=wizard:wizards ./pyproject.toml ./

# 🔒 Spell #8: Restrictive File Permissions (OWASP)
# Make files read-only and executable where needed - prevents tampering
USER root
RUN chmod -R 550 /spellbook/spells /spellbook/potions /spellbook/enchantments && \
    chmod 440 /spellbook/main.py /spellbook/pyproject.toml
USER wizard

# 📢 Spell #12: Explicit Port Declaration (Documentation & Security)
# Declare which port the app listens on - helps with security scanning
# While it doesn't publish the port (-p does that), it serves as:
# 1. Documentation for users/tools about intended port usage
# 2. Metadata for security scanners to validate configuration
# 3. Hint for orchestrators (K8s, Compose) for network setup
EXPOSE 8000

# �💓 Spell #13: Health Check Enchantment (CIS 4.7)
# Enables automatic healing - Docker/K8s will restart if the spell fails
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 🛑 Spell #14: Graceful Shutdown Signal (Production Stability)
# Ensures the app receives proper shutdown signal for cleanup
STOPSIGNAL SIGTERM

# ⚡ Spell #15: Signal Handling with Tini (OWASP)
# Prevents zombie processes and ensures graceful shutdowns
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/spellbook/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ═══════════════════════════════════════════════════════════════════════
# 🎓 Wizardry Lessons Learned:
# • Multi-stage builds reduce final image size by 50-70%
# • Alpine base keeps images compact (5-10x smaller than Debian)
# • Non-root users limit security blast radius
# • Copying dependencies before code leverages Docker cache
# • Restrictive permissions prevent tampering
# • Health checks enable self-healing
# • ARG makes builds flexible and maintainable
# 
# 🔐 Additional Runtime Security (apply when running):
# • docker run --read-only --tmpfs /tmp wizardry:latest
# • docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE wizardry:latest
# • docker run --security-opt=no-new-privileges wizardry:latest
# • docker run --memory=512m --cpus=1.0 wizardry:latest
# • Use secrets: docker build --secret id=mysecret,src=secret.txt .
# • Enable content trust: export DOCKER_CONTENT_TRUST=1
# ═══════════════════════════════════════════════════════════════════════
