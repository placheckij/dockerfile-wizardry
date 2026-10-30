# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                    🧙‍♂️ DOCKERFILE WIZARDRY 🧙‍♂️                          ║
# ║         Security-hardened, optimized Docker image creation           ║
# ║    Following CIS Benchmark & OWASP best practices with a touch      ║
# ║                          of magic! ✨                                 ║
# ╚═══════════════════════════════════════════════════════════════════════╝

# 🎯 Spell #1: Parameterized Base Image
ARG PYTHON_VERSION=3.14.10
ARG ALPINE_VERSION=3.24
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS base

# 🏷️ Spell #2: Metadata Labels (OWASP)
LABEL maintainer="placheckij" \
      version="1.0.0" \
      description="Dockerfile Wizardry - Best Practices Example" \
      org.opencontainers.image.source="https://github.com/placheckij/dockerfile-wizardry"

USER root
# 🛡️ Spell #3: Minimal Packages & Non-Root User (CIS 4.3)
# (only tini - no curl, the health check below uses Python)
# hadolint ignore=DL3018
RUN apk -U upgrade && \
    apk add --no-cache tini && \
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
RUN python -m pip install --no-cache-dir poetry==2.5.*
ENV PATH=/spellbook/.local/bin:$PATH \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_OPTIONS_NO_PIP=true

# 🎯 Spell #6: Layer Caching - Dependencies First (CIS 4.9)
COPY --chown=wizard:wizards ./pyproject.toml ./poetry.lock ./
RUN /spellbook/.local/bin/poetry sync --only main --no-root --no-ansi --no-interaction --no-cache

# ═══════════════════════════════════════════════════════════════════════
# 🚀 Stage 3: Assemble the Runtime Image
# ═══════════════════════════════════════════════════════════════════════
FROM base AS pruned

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

# ✂️ Spell #10: Prune What You Don't Run (CIS 4.3)
# Remove the package manager (pip, apk), build leftovers (C headers, ensurepip,
# IDLE, Tk, pydoc) and network tools (wget, nc, telnet, ...). This is defense in
# depth, not a barrier: Python and the busybox shell are still present.
RUN /usr/local/bin/python -m pip uninstall -y pip && \
    PYLIB=/usr/local/lib/python3.14 && \
    rm -rf /usr/local/include "$PYLIB"/ensurepip "$PYLIB"/idlelib "$PYLIB"/tkinter \
           "$PYLIB"/turtledemo "$PYLIB"/pydoc_data "$PYLIB"/lib-dynload/_tkinter* \
           /usr/local/bin/idle* /usr/local/bin/pydoc* /usr/local/bin/python*-config && \
    rm -f /usr/bin/wget /usr/bin/nc /usr/bin/telnet /usr/bin/ftpget /usr/bin/ftpput \
          /usr/bin/tftp /usr/bin/ssl_client /bin/wget /bin/nc /bin/telnet /bin/ssl_client && \
    rm -rf /sbin/apk /lib/libapk* /lib/apk /var/cache/apk /etc/apk
USER wizard

# ═══════════════════════════════════════════════════════════════════════
# 🪶 Stage 4: Flatten into the Final Image
# ═══════════════════════════════════════════════════════════════════════
# Deleting files in a later layer saves nothing - they stay in the layers below
# and can still be extracted from the image. Copying the pruned filesystem into
# a fresh `scratch` image drops them for real (and shrinks the image ~17 MB).
# scratch starts with no metadata, so ENV, LABEL, USER, ... are declared again.
FROM scratch AS runtime
ARG PYTHON_VERSION
# hadolint ignore=DL3067
COPY --from=pruned / /
ENV PATH=/spellbook/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 \
    PYTHON_VERSION=${PYTHON_VERSION} \
    PYTHONUNBUFFERED=true
LABEL maintainer="placheckij" \
      version="1.0.0" \
      description="Dockerfile Wizardry - Best Practices Example" \
      org.opencontainers.image.source="https://github.com/placheckij/dockerfile-wizardry"
USER wizard
WORKDIR /spellbook

# 📢 Spell #11: Explicit Port Declaration
EXPOSE 8000

# 💓 Spell #12: Health Check (CIS 4.6)
# Python instead of curl: one less binary (and its libraries) in the image.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["/spellbook/.venv/bin/python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=2)"]

# 🛑 Spell #13: Graceful Shutdown Signal
STOPSIGNAL SIGTERM

# ⚡ Spell #14: Signal Handling with Tini (OWASP)
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/spellbook/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ═══════════════════════════════════════════════════════════════════════
# 🎓 For detailed explanations of each spell, see README.md
# 🔐 For production runtime security flags, see RUNTIME_SECURITY.md
# ═══════════════════════════════════════════════════════════════════════
