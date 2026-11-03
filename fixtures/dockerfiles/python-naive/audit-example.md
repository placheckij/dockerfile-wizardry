# Worked example: auditing `python-naive` with the skill

Command, run from the repository root on 2026-11-03 with Claude Code 2.1.309 (`claude --version`); the model was `claude-opus-4-8`. The output below is the run's `result` field, unedited.

```sh
claude -p --setting-sources project --plugin-dir . --no-session-persistence \
  --permission-mode dontAsk \
  --tools Read Grep Glob Bash Skill \
  --allowedTools "Bash(docker *)" "Bash(hadolint *)" "Bash(command -v *)" "Bash(which *)" "Bash(grep *)" "Bash(head *)" "Bash(tail *)" "Bash(echo *)" "Bash(cd *)" "Bash(awk *)" "Bash(cat *)" "Bash(uv --version)" "Bash(ls *)" \
  --disallowedTools "Read(./fixtures/**/expected-findings.txt)" "Bash(*expected-findings*)" "Bash(docker push *)" "Bash(docker rm *)" "Bash(docker rmi *)" "Bash(docker image rm *)" "Bash(docker system *)" "Bash(docker volume *)" \
  --output-format json \
  -- "Audit fixtures/dockerfiles/python-naive/Dockerfile with the dockerfile-wizardry skill. Report only; do not edit files."
```

The tool list and permissions keep the run from changing files: there is no Edit or Write tool, Bash is limited to Docker (destructive subcommands denied), the linters and a few read-only commands, and the fixture's `expected-findings.txt` is hidden so the audit cannot copy it. Anything else the run tries is denied, not asked.

## Output

I have everything I need. `hadolint` isn't installed and the `docker build --check` invocation was blocked by the environment, so the linter-backed codes below were verified by reading, not by running the tools. The digest lookup for the base image did succeed. Here's the audit.

---

# Audit — `fixtures/dockerfiles/python-naive/Dockerfile`

**Context note:** the build context (`fixtures/dockerfiles/python-naive/`) contains only the Dockerfile and `expected-findings.txt` — there is **no `.dockerignore`** in it (the repo-root `.dockerignore` only applies if the whole repo is the build context). The file's own header says it is lint-only and never built, and it references `requirements.txt`/`app.py` that aren't present; I audited it as written.

## Findings

| Rule | Line | Finding | Severity |
|------|------|---------|----------|
| DW-BASE-01 | 3 | `FROM python:latest` — floating `latest`, no version tag, no digest | should fix |
| DW-BASE-02 | — | No OCI `LABEL` metadata | should fix |
| DW-BUILD-01 | 10–11 | Whole context copied before install, so any code change busts the dependency layer | should fix |
| DW-BUILD-02 | 3–14 | Single stage; pip and build tooling ship in the runtime image | should fix |
| DW-BUILD-03 | 10 | `ADD . /app` copies the entire context (incl. `.git`, secrets, tests) with `ADD`; no `.dockerignore` | **must fix** |
| DW-BUILD-04 | — | Pruning/flattening not done | decide |
| DW-BUILD-05 | 11 | `pip install` bakes its download cache into the layer | should fix |
| DW-BUILD-10 | 3 | Full `python:latest` ships apt + pip the app doesn't run | should fix |
| DW-DEPS-02 | 11 | pip cache left in the layer; installer unpinned, no hashes, no bytecode compile | should fix |
| DW-HEALTH-02 | — | No `HEALTHCHECK` | should fix |
| DW-HEALTH-03 | — | No `STOPSIGNAL` | should fix |
| DW-HEALTH-04 | 14 | No init as PID 1 | should fix |
| DW-HEALTH-05 | 14 | `CMD python app.py` in shell form — signals won't reach the app | should fix |
| DW-SECRET-01 | 7 | `ARG API_TOKEN` — secret-shaped build arg | **must fix** |
| DW-USER-01 | — | No `USER`; container runs as root | **must fix** |
| DW-USER-02 | — | Code is root-owned and run by root (writable by the running process) | should fix |

---

### DW-BUILD-03 — Copy only what the image needs (must fix), line 10
`ADD . /app` pulls the entire build context into the image for good — including `.git`, local envs and anything secret — and uses `ADD` where `COPY` is meant for local files (Hadolint DL3020 / Dockle CIS-DI-0009). With no `.dockerignore` in this context, nothing is held back.
Source: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-12-utilize-docker-secrets-for-sensitive-data-management

Add a `.dockerignore` next to the build context:

```diff
--- /dev/null
+++ b/fixtures/dockerfiles/python-naive/.dockerignore
@@ -0,0 +1,15 @@
+# DW-BUILD-03: keep VCS, secrets, local envs, caches, tests and docs out of the context
+.git
+.gitignore
+**/__pycache__
+**/*.pyc
+.venv
+venv
+.env
+*.env
+*.pem
+*.key
+tests
+docs
+Dockerfile*
```

The `ADD . /app` → scoped `COPY` change is folded into the rewrite diff below.

### DW-SECRET-01 — Never pass secrets through ARG/ENV/COPY (must fix), line 7
Build arguments persist in image metadata, and Docker's build check `SecretsUsedInArgOrEnv` flags sensitive-looking names like `API_TOKEN` regardless of whether a value is set here. A token needed at build time belongs in a `RUN --mount=type=secret`.
Source: https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/

The rewrite diff removes the `ARG`. If a real token is ever needed during the build, mount it:
```dockerfile
RUN --mount=type=secret,id=api_token \
    API_TOKEN="$(cat /run/secrets/api_token)" ...
```

### DW-USER-01 / DW-USER-02 — Run as non-root, not owning the code (must fix / should fix)
With no `USER`, the process runs as root; a compromise starts with root in the container, and root owns and can rewrite its own code. Fix: a numeric non-root user, code left root-owned and group-readable.
Source: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user

### DW-BASE-01 — Pin by digest (should fix), line 3
A tag like `latest` can be republished onto different bytes tomorrow; a digest names one image. I resolved the current multi-platform index digest for `python:3.13-slim`: `sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1`. Because the project declares no Python version, `3.13` is my choice — confirm it. A digest freezes the base, so pair it with Dependabot/Renovate and periodic `--no-cache --pull` rebuilds (DW-SUPPLY-04).
Source: https://docs.docker.com/build/building/best-practices/#pin-base-image-versions

### DW-BASE-02, DW-BUILD-01/02/05/10, DW-DEPS-02, DW-HEALTH-02/03/04/05 (should fix)
These are addressed together by restructuring into a multi-stage build with metadata, cached pip downloads, a slim base, a health check, an init and exec-form startup. Key sources: multi-stage https://docs.docker.com/build/building/best-practices/#use-multi-stage-builds ; cache mounts https://docs.docker.com/build/cache/optimize/ ; health check https://docs.docker.com/reference/dockerfile/#healthcheck ; init https://github.com/krallin/tini ; exec form https://docs.docker.com/reference/build-checks/json-args-recommended/ .

Consolidated rewrite (also carries the DW-BUILD-03 `COPY` scoping and DW-SECRET-01/USER fixes). Adapt `app.py`, the health URL, labels and `requirements.txt` to your project:

```diff
--- a/fixtures/dockerfiles/python-naive/Dockerfile
+++ b/fixtures/dockerfiles/python-naive/Dockerfile
@@ -1,14 +1,54 @@
-# Bad on purpose: a first-draft Python image. Every expected finding is listed in
-# expected-findings.txt next to this file. Linted only, never built.
-FROM python:latest
-
-# a token as a build argument ends up in the image metadata (no value here, so the
-# repository's secret scan has nothing to find)
-ARG API_TOKEN
-
-WORKDIR /app
-ADD . /app
-RUN pip install -r requirements.txt
-
-EXPOSE 8000
-CMD python app.py
+# syntax=docker/dockerfile:1
+
+ARG PYTHON_VERSION=3.13-slim
+
+# DW-BASE-01: pin by digest, tag kept beside it. TODO: confirm 3.13 (the project
+# declares none) and automate digest updates + periodic no-cache rebuilds (DW-SUPPLY-04).
+FROM python:${PYTHON_VERSION}@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS build
+
+WORKDIR /app
+
+# DW-BUILD-01: dependencies before source so this layer caches until requirements change
+COPY requirements.txt .
+# DW-BUILD-05, DW-DEPS-02: pip cache in a mount, install into a prefix we copy to runtime
+RUN --mount=type=cache,target=/root/.cache/pip \
+    pip install --prefix=/install -r requirements.txt
+
+FROM python:${PYTHON_VERSION}@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS runtime
+
+# DW-BASE-02: OCI metadata (replace with your values)
+LABEL org.opencontainers.image.source="https://example.com/OWNER/REPO" \
+      org.opencontainers.image.version="0.1.0" \
+      org.opencontainers.image.licenses="Apache-2.0"
+
+# DW-HEALTH-04: tini installed here so the ENTRYPOINT binary exists in the image
+# not pinning apt versions is a deliberate choice (trade-offs §2)
+# hadolint ignore=DL3008
+RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
+    --mount=type=cache,target=/var/lib/apt,sharing=locked \
+    apt-get update && apt-get install -y --no-install-recommends tini
+
+WORKDIR /app
+
+COPY --from=build /install /usr/local
+# DW-BUILD-03: copy only the code the image needs, not the whole context
+# DW-USER-02: code stays root-owned and not writable by the runtime user
+COPY app.py ./
+
+EXPOSE 8000
+
+# DW-HEALTH-02: health check using the python already in the image
+HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
+    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/').status == 200 else 1)"]
+
+# DW-HEALTH-03: SIGTERM is already the default; stated here, and the app must handle it
+STOPSIGNAL SIGTERM
+
+# DW-USER-01: dedicated non-root numeric user
+RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
+USER 10001:10001
+
+# DW-HEALTH-04/05: init as PID 1, app in exec form so signals reach it
+ENTRYPOINT ["tini", "--"]
+CMD ["python", "app.py"]
```

Not from the rulebook: consider a `requirements.txt` with hashes (`pip install --require-hashes`) and compiling bytecode (`python -m compileall`) if you move to a read-only root filesystem (DW-DEPS-02 touches the latter).

### DW-BUILD-04 — Prune then flatten (decide, trade-off)
Not a violation. **For:** deleting unused package managers/tools and flattening into `scratch` removes them from every layer (defense in depth). **Against:** it breaks `docker exec sh` debugging and `ls`/`id` checks, and you must re-declare all metadata. Weigh hardening against operability (trade-offs §6 also covers going distroless instead). See https://docs.docker.com/build/building/multi-stage/

---

## Passes the listed checks
- **DW-HEALTH-01** — `EXPOSE 8000` is present (line 13).

## Does not apply
- **DW-BUILD-06** (no large source-only tree), **DW-BUILD-08** (no multi-arch build), **DW-DEPS-01** (no OS-package install in the file as written), **DW-DEPS-03** (no direct `curl`/`wget`/`ADD`-URL download).

## Limits — not checked from these files
- **Linters not run:** `hadolint` is not installed and the `docker build --check` call was blocked, so DL3006/DL3007 (DW-BASE-01), DL3020 (DW-BUILD-03), DL3002 (DW-USER-01), DL3057 (DW-HEALTH-02), `JSONArgsRecommended` (DW-HEALTH-05) and `SecretsUsedInArgOrEnv` (DW-SECRET-01) were verified by reading only. The base-image digest lookup did run and is quoted above.
- **CI / publishing / process:** DW-BUILD-07, DW-BUILD-09, DW-SUPPLY-01, -02, -03, -04, -05, -06 need the workflow files, the built image, or the engine environment — none provided here.
- **Human judgement:** the trade-off rule DW-BUILD-04, and which packages the app truly needs.

## This Dockerfile does not pass
Three must-fix findings are open — **DW-BUILD-03**, **DW-SECRET-01**, **DW-USER-01** — plus the should-fix items above and the DW-BUILD-04 decision. I have not called it secure or compliant; the rulebook doesn't cover everything that would take.

I made no edits (report-only, as asked). Want me to write the fixed `Dockerfile` and `.dockerignore` to a different path, or leave the fixture untouched?

## Review

Reviewed by hand against `expected-findings.txt` and the rulebook.

**Expected findings.** All eight are reported, each with the severity its strength gives:
DW-BASE-01, DW-SECRET-01, DW-BUILD-03, DW-BUILD-01, DW-DEPS-02, DW-HEALTH-05,
DW-HEALTH-02 and DW-USER-01. The run also reports DW-BASE-02, DW-BUILD-02, DW-BUILD-05,
DW-BUILD-10, DW-HEALTH-03, DW-HEALTH-04 and DW-USER-02, which the file also breaks but
the fixture's list does not name.

**Rule ids.** Every id it cites exists in `references/rules.md`.

**Digests and versions.** The one digest it gives, for `python:3.13-slim`, matches
`docker buildx imagetools inspect python:3.13-slim` run afterwards. Python 3.13 is its own
choice (the fixture declares no version), and it says so and asks for confirmation. No
other version or checksum is claimed.

**Trade-offs.** DW-BUILD-04 is shown as a decision with both sides and is not counted as a
violation. DW-DEPS-01 does not apply to the original file (no OS packages); the
rewrite's `tini` install is covered below.

**Wording.** No "secure" claim. "Passes the listed checks" is used only for DW-HEALTH-01,
which does pass, and the close names the three open must-fix findings.

**What it missed or got wrong.**
- `docker build --check` did not run. The run's first call combined several commands and
  set `DOCKER_BUILDKIT=1` in front of `docker build`, which the allowlist above does not
  match, so it was denied; the run said so rather than guessing, but did not retry the
  plain command. Hadolint is not installed on this machine. All linter codes were
  therefore checked by reading. This is a limit of the test setup more than of the skill.
- In the proposed runtime stage it puts the apt download directories in cache mounts but
  does not remove Debian's `docker-clean` setting, so the `/var/cache/apt` mount keeps
  nothing; DW-BUILD-05 says to install final-stage packages as usual and clean up in the
  same layer.
- `useradd --uid 10001` gives no explicit group id; it relies on Debian creating a group
  with the same number. DW-USER-01 asks for explicit numeric ids for both.
- Neither diff applies as written. `git apply --check` on a copy of the fixture rejects
  both as corrupt: the `.dockerignore` hunk declares `+1,15` but adds 14 lines, and the
  rewrite declares `+1,54` but adds 53.
- It says the slim multi-stage rewrite addresses DW-BUILD-10, but the `python:3.13-slim`
  runtime stage still has `apt-get`, `dpkg` and `pip`. Only pruning (DW-BUILD-04) or a
  base without them would meet the rule.
- The rewrite installs `tini` with apt, unpinned, under `# hadolint ignore=DL3008`. That
  is the skill's no-pin default for DW-DEPS-01, but the summary never names it as a
  choice, as the skill's defaults ask.
- The rewrite does not comment sparingly: almost every instruction has a `# DW-...` line
  above it, and two of those lines carry two ids (`DW-BUILD-05, DW-DEPS-02` and
  `DW-HEALTH-04/05`), where the skill asks for one id per line.

**Changes to SKILL.md from earlier runs.** Earlier runs of this fixture guessed why a
digest lookup failed ("no network") when it had been denied or not run, wrote comments at
the end of Dockerfile lines (which a Dockerfile does not support), proposed
`ENTRYPOINT ["tini", "--"]` without installing `tini`, and wrote hunks without line
numbers. SKILL.md now covers each of these. This run has no guessed failure reasons, no
end-of-line comments and installs `tini`, and its hunks carry line numbers, but the
numbers are wrong (see above), so the diffs still do not apply.
