# Worked example: auditing `debian-apt-naive` with the skill

Command, run from the repository root on 2026-11-03 with Claude Code 2.1.309 (`claude --version`); the model was `claude-opus-4-8`. The output below is the run's `result` field, unedited.

```sh
claude -p --setting-sources project --plugin-dir . --no-session-persistence \
  --permission-mode dontAsk \
  --tools Read Grep Glob Bash Skill \
  --allowedTools "Bash(docker *)" "Bash(hadolint *)" "Bash(command -v *)" "Bash(which *)" "Bash(grep *)" "Bash(head *)" "Bash(tail *)" "Bash(echo *)" "Bash(cd *)" "Bash(awk *)" "Bash(cat *)" "Bash(uv --version)" "Bash(ls *)" \
  --disallowedTools "Read(./fixtures/**/expected-findings.txt)" "Bash(*expected-findings*)" "Bash(docker push *)" "Bash(docker rm *)" "Bash(docker rmi *)" "Bash(docker image rm *)" "Bash(docker system *)" "Bash(docker volume *)" \
  --output-format json \
  -- "Audit fixtures/dockerfiles/debian-apt-naive/Dockerfile with the dockerfile-wizardry skill. Report only; do not edit files."
```

The tool list and permissions keep the run from changing files: there is no Edit or Write tool, Bash is limited to Docker (destructive subcommands denied), the linters and a few read-only commands, and the fixture's `expected-findings.txt` is hidden so the audit cannot copy it. Anything else the run tries is denied, not asked.

## Output

## Audit: `fixtures/dockerfiles/debian-apt-naive/Dockerfile`

**Inputs reviewed:** the Dockerfile (single stage, lines 1–9). No `.dockerignore` and no `<Dockerfile>.dockerignore` exist in the build context — but the Dockerfile has no `COPY`/`ADD`, so nothing is pulled from the context. No entrypoint/wrapper script (`ENTRYPOINT` runs `curl` directly).

**Linters:** Hadolint is **not installed**, so its codes (DL3002, DL3008, DL3057, …) were checked by reading. Docker's build check ran:

```
docker build --check -f Dockerfile .  →  Check complete, no warnings found.
```

That clears `SecretsUsedInArgOrEnv` (DW-SECRET-01) and `JSONArgsRecommended` (DW-HEALTH-05).

### Findings

| Rule | Line | Finding | Severity |
|------|------|---------|----------|
| DW-BASE-01 | 3 | Base image pinned by tag only, no digest | should fix |
| DW-BASE-02 | 3 | No image metadata labels | should fix |
| DW-BUILD-04 | 5 | apt package manager kept; not pruned/flattened | decide |
| DW-BUILD-10 | 5 | apt (package manager) left in the final image | should fix |
| DW-DEPS-01 | 5 | Recommended packages kept and apt lists not removed in-layer; pinning is a decision | decide |
| DW-HEALTH-02 | — | No `HEALTHCHECK` | should fix |
| DW-HEALTH-03 | — | No `STOPSIGNAL` | should fix |
| DW-HEALTH-04 | 8 | No init as PID 1 | should fix |
| DW-USER-01 | 7 | Final stage runs as root (`USER root`) | must fix |

---

**DW-USER-01 — runs as root (must fix), line 7.**
Code execution inside the container starts with root's privileges rather than an unprivileged user, so a compromise reaches further (CIS 4.1, OWASP Rule 2). `USER root` is set explicitly. A numeric UID needs no `/etc/passwd` entry for `curl` to run.
Source: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user

```diff
--- a/Dockerfile
+++ b/Dockerfile
@@ -4,6 +4,6 @@
 
 RUN apt-get update && apt-get install -y curl ca-certificates
 
-USER root
+USER 10001:10001
 ENTRYPOINT ["curl"]
 CMD ["--version"]
```

**DW-BASE-01 — pin the base by digest (should fix), line 3.**
A tag can be republished, so the same Dockerfile can build on different bytes tomorrow; a digest names exactly one image. I resolved the current digest with `docker buildx imagetools inspect debian:trixie-slim` (top-level `Digest:`). A digest freezes the base, so pair it with Dependabot/Renovate and periodic no-cache rebuilds (DW-SUPPLY-04, trade-offs §1).
Source: https://docs.docker.com/build/building/best-practices/#pin-base-image-versions

```diff
--- a/Dockerfile
+++ b/Dockerfile
@@ -1,3 +1,5 @@
 # Bad on purpose: an apt install that keeps recommended packages and the package lists,
 # and a container that runs as root. Linted only, never built.
-FROM debian:trixie-slim
+ARG DEBIAN_VERSION=trixie-slim
+# DW-BASE-01: tag kept beside the digest so a reader can tell what it is
+FROM debian:${DEBIAN_VERSION}@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4
```

**DW-BASE-02 — label the image (should fix), line 3.**
Labels make an image traceable to its source and owner. Use the OCI keys; the values below are placeholders to replace.
Source: https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys

```diff
--- a/Dockerfile
+++ b/Dockerfile
@@ -3,3 +3,8 @@
 FROM debian:trixie-slim
+
+LABEL org.opencontainers.image.source="https://github.com/placheckij/dockerfile-wizardry" \
+      org.opencontainers.image.description="curl on debian slim" \
+      org.opencontainers.image.licenses="MIT"
 
 RUN apt-get update && apt-get install -y curl ca-certificates
```

**DW-DEPS-01 — install only what you need, in one layer (decide), line 5.**
The index update and install are already in one `RUN` (good). Two things the rule's statement calls for are missing: recommended packages are kept (no `--no-install-recommends`), and the apt lists are left in the layer (no `rm -rf /var/lib/apt/lists/*`) — both add size and attack surface. Whether to pin each package version is the genuine trade-off: Hadolint DL3008 asks for pins for reproducibility, but a pinned version can disappear from a repo that keeps only the current one, and a pin stops automatic security fixes (trade-offs §2). This skill's default is **not** to pin apt versions and to rely on a base-digest check plus periodic no-cache rebuilds. Severity is "decide" because the rule is a TRADE-OFF; the recommends/lists cleanup below is the non-controversial part.
Source: https://docs.docker.com/build/building/best-practices/#run

```diff
--- a/Dockerfile
+++ b/Dockerfile
@@ -4,3 +4,4 @@
 
-RUN apt-get update && apt-get install -y curl ca-certificates
+RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
+    && rm -rf /var/lib/apt/lists/*
```

**DW-BUILD-10 — leave out package-management tools (should fix), line 5.**
The NCSC guidance says images should not normally ship package managers, because contents are not expected to change at runtime, and fewer tools leaves fewer for an attacker. apt stays in this image. On a distribution base this is met either by a base without a package manager or by pruning — which is the DW-BUILD-04 trade-off below, so there is no clean one-line diff; it is the same decision.
Source: https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images

**DW-BUILD-04 — prune then flatten (decide), line 5.**
Removing apt and headers and copying the pruned filesystem into a fresh `scratch` stage removes those files from every layer (keeping the dpkg database `/var/lib/dpkg` for scanners). This is defense in depth with an operability cost — removing the shell breaks `docker exec … sh` debugging. State both sides and choose; it is not counted as a violation (trade-offs §6).
Source: https://docs.docker.com/build/building/multi-stage/

**DW-HEALTH-02 / 03 / 04 — health check, stop signal, init as PID 1 (should fix).**
None are present (no `HEALTHCHECK`, no `STOPSIGNAL`, `ENTRYPOINT`/`CMD` run `curl` directly with no `tini`/`--init`). **Note:** this image runs `curl` as a one-shot command that exits, not a long-running service, so these three fit it poorly — a health check has nothing to probe, graceful-shutdown signalling barely applies, and PID-1 child-reaping is moot. I report them per the skill rather than drop them; for a real server they would each warrant a fix (e.g. `STOPSIGNAL SIGTERM`, a `HEALTHCHECK` using a binary in the image, `tini` as the init).
Sources: https://docs.docker.com/reference/dockerfile/#healthcheck · https://github.com/krallin/tini

---

### Rules that pass
- **DW-HEALTH-05** — `ENTRYPOINT` and `CMD` are exec (JSON array) form; Docker build check raised no `JSONArgsRecommended`.
- **DW-SECRET-01** — no secrets via `ARG`/`ENV`/`COPY`; `SecretsUsedInArgOrEnv` clean.

### Rules that do not apply
- **DW-BUILD-01** — no dependency manifest/lockfile or application code to order.
- **DW-BUILD-02** — nothing is compiled; `curl` (an apt package) is the runtime payload, so there is no build artifact to separate.
- **DW-BUILD-03** — no `COPY`/`ADD` (so no `.dockerignore` needed either).
- **DW-BUILD-06** — no large source tree copied.
- **DW-BUILD-08** — no multi-platform/emulated build.
- **DW-BUILD-05** — no build stage with package-manager downloads to cache; final-stage install cleanup is covered under DW-DEPS-01.
- **DW-DEPS-02** — no language tooling installer (uv/pip/etc.).
- **DW-DEPS-03** — the build downloads no file directly; apt handles its own verification.
- **DW-HEALTH-01** — one-shot `curl`, listens on no port.
- **DW-USER-02** — no application code/dependencies are copied to be owned; moot until code exists (and until DW-USER-01 is fixed).

### Limits (not checkable from these files)
- **Runtime settings** (`docker run` flags, Compose/Kubernetes) — none provided.
- **DW-BUILD-07, DW-SUPPLY-03** (CI cache, action pinning) — no workflow files provided.
- **DW-SUPPLY-01, DW-SUPPLY-02** (SBOM, provenance, signing) — publishing not in scope.
- **DW-SUPPLY-04, DW-SUPPLY-06** (rebuild cadence, Engine/BuildKit versions, frontend trust) — manual/operational; no `# syntax=` line, so BuildKit uses its bundled frontend.
- **DW-SUPPLY-05, DW-BUILD-04 verification** — confirming removed files are gone from every layer needs the built image, not the Dockerfile.
- **DW-BUILD-09** — whether reproducible output matters is human judgement; not indicated here.
- Hadolint was unavailable, so its codes were read by eye rather than run.

### Checks it fails
Per the skill, I won't call this Dockerfile secure. One **must-fix** finding is open — **DW-USER-01** (runs as root) — plus should-fix findings **DW-BASE-01, DW-BASE-02, DW-BUILD-10, DW-HEALTH-02/03/04** and two decisions (**DW-BUILD-04, DW-DEPS-01**).

Report only — no files were edited. Want me to show which of these would resolve the fixture's intended labels, or draft the fixed Dockerfile without applying it?

## Review

Reviewed by hand against `expected-findings.txt` and the rulebook.

**Expected findings.** All four are reported: DW-DEPS-01 (decide), DW-USER-01 (must fix),
DW-HEALTH-02 and DW-BASE-01 (should fix). It also reports DW-BASE-02, DW-BUILD-10,
DW-HEALTH-03 and DW-HEALTH-04, and DW-BUILD-04 as a decision; the fixture's list does not
name these.

**Rule ids.** Every id it cites exists in `references/rules.md`.

**Digests and versions.** The digest for `debian:trixie-slim`
(`sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4`) matches
`docker buildx imagetools inspect debian:trixie-slim` run afterwards. No package version
or checksum is claimed.

**Trade-offs.** DW-DEPS-01 is shown as a decision, with both sides of trade-offs §2 and the
skill's default (do not pin). This is where the rulebook limits the result: DW-DEPS-01 is
TRADE-OFF as a whole, so the parts that are not contested here (`--no-install-recommends`,
removing the apt lists; Hadolint DL3015 and DL3009) also appear under "decide". The run
says plainly that those two are the uncontested part. DW-BUILD-04 is a decision as well,
and DW-BUILD-10 is linked to it.

**Wording.** No "secure" claim. The rules it lists as passing, DW-HEALTH-05 and
DW-SECRET-01, do pass (`docker build --check` ran and reported no warnings). The close
names the open must-fix finding.

**What it missed or got wrong.**
- Its DW-DEPS-01 diff does not add the `# hadolint ignore=DL3008` line with a reason that
  the skill's defaults ask for when versions stay unpinned.
- Its DW-USER-01 diff only sets `USER 10001:10001`. That runs, but the rule says to create
  a dedicated user and group with those ids.
- Hadolint is not installed on this machine, so DL3066 (`USER` by name rather than numeric
  id), which no rule names, was not reported, not even as "not from the rulebook".
- The `LABEL` values in the DW-BASE-02 diff (this repository's URL, MIT) are guesses; the
  run calls them placeholders.

**Changes to SKILL.md from earlier runs.** One earlier run marked DW-HEALTH-02 "does not
apply" because the image runs a one-shot command. SKILL.md now reserves "does not apply"
for rules with nothing in the Dockerfile to check, and this run reports DW-HEALTH-02,
DW-HEALTH-03 and DW-HEALTH-04 as findings with a note that they matter little for a
one-shot command.
