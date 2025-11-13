# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                    🧙‍♂️ DOCKERFILE WIZARDRY 🧙‍♂️                          ║
# ║         Security-hardened, optimized Docker image creation           ║
# ║    Following CIS Benchmark & OWASP best practices with a touch      ║
# ║                          of magic! ✨                                 ║
# ╚═══════════════════════════════════════════════════════════════════════╝

# 🎯 Spell #1: Parameterized Base Image
ARG PYTHON_VERSION=3.12.12
ARG ALPINE_VERSION=3.22
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS base

# 🏷️ Spell #2: Metadata Labels (OWASP)
LABEL maintainer="placheckij" \
      version="1.0.0" \
      description="Dockerfile Wizardry - Best Practices Example" \
      org.opencontainers.image.source="https://github.com/placheckij/dockerfile-wizardry"

USER root
# 🛡️ Spell #3: Minimal Packages & Non-Root User (CIS 4.2)
# hadolint ignore=DL3018
RUN apk -U upgrade && \
    apk add --no-cache curl tini && \
    rm -rf /var/cache/apk/* && \
    addgroup -g 1337 wizards && \
    adduser -D -h /spellbook -G wizards -u 1337 wizard

ENV PYTHONUNBUFFERED=true

# 🔐 Spell #4: Non-Root User (CIS 4.1, OWASP)
USER wizard
WORKDIR /spellbook

# ═══════════════════════════════════════════════════════════════════════
# 📚 Stage 2: Dependency Installation
# ═══════════════════════════════════════════════════════════════════════
FROM base AS poetry
# 📦 Spell #5: Install Poetry Without Cache
RUN python -m pip install --no-cache-dir poetry==2.2.*
ENV PATH=/spellbook/.local/bin:$PATH \
    POETRY_VIRTUALENVS_IN_PROJECT=true

# 🎯 Spell #6: Layer Caching - Dependencies First (CIS 4.9)
COPY --chown=wizard:wizards ./pyproject.toml ./poetry.lock ./
RUN /spellbook/.local/bin/poetry sync --no-root --no-ansi --no-interaction --no-cache

# ═══════════════════════════════════════════════════════════════════════
# 🚀 Stage 3: Runtime Image
# ═══════════════════════════════════════════════════════════════════════
FROM base AS runtime
ENV PATH=/spellbook/.venv/bin:$PATH

# 🔮 Spell #7: Multi-Stage Build - Copy Only Runtime Dependencies
COPY --chown=wizard:wizards --from=poetry /spellbook/.venv /spellbook/.venv

# ✨ Spell #8: Selective File Copying (CIS 4.9)
COPY --chown=wizard:wizards ./spellbook/spells ./spells
COPY --chown=wizard:wizards ./spellbook/potions ./potions
COPY --chown=wizard:wizards ./spellbook/enchantments ./enchantments
COPY --chown=wizard:wizards ./spellbook/main.py ./
COPY --chown=wizard:wizards ./pyproject.toml ./

# 🔒 Spell #9: Restrictive File Permissions (OWASP)
USER root
RUN chmod -R 550 /spellbook/spells /spellbook/potions /spellbook/enchantments && \
    chmod 440 /spellbook/main.py /spellbook/pyproject.toml
USER wizard

# 📢 Spell #10: Explicit Port Declaration
EXPOSE 8000

# 💓 Spell #11: Health Check (CIS 4.7)
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 🛑 Spell #12: Graceful Shutdown Signal
STOPSIGNAL SIGTERM

# ⚡ Spell #13: Signal Handling with Tini (OWASP)
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/spellbook/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ═══════════════════════════════════════════════════════════════════════
# 🎓 For detailed explanations of each spell, see README.md
# 🔐 For production runtime security flags, see RUNTIME_SECURITY.md
# ═══════════════════════════════════════════════════════════════════════
