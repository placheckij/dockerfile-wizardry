# Worked example: auditing `debian-apt-naive` with the skill

Command, run from the repository root on 2026-11-03 with Claude Code 2.1.309 (`claude --version`); the model was `claude-opus-4-8`. The output below is the run's `result` field, unedited.

```sh
claude -p --setting-sources project --plugin-dir . --no-session-persistence \
  --permission-mode dontAsk \
  --tools Read Grep Glob Bash Skill \
  --allowedTools "Bash(docker *)" "Bash(hadolint *)" "Bash(command -v *)" "Bash(which *)" "Bash(grep *)" "Bash(head *)" "Bash(tail *)" "Bash(echo *)" "Bash(cd *)" "Bash(awk *)" "Bash(cat *)" "Bash(uv --version)" "Bash(ls *)" "Bash(diff *)" \
  --disallowedTools "Read(./fixtures/**/expected-findings.txt)" "Bash(*expected-findings*)" "Bash(docker push *)" "Bash(docker rm *)" "Bash(docker rmi *)" "Bash(docker image rm *)" "Bash(docker system *)" "Bash(docker volume *)" \
  --output-format json \
  -- "Audit fixtures/dockerfiles/debian-apt-naive/Dockerfile with the dockerfile-wizardry skill. Report only; do not edit files."
```

The tool list and permissions keep the run from changing files: there is no Edit or Write tool, Bash is limited to Docker (destructive subcommands denied), the linters, `diff` and a few read-only commands, and the fixture's `expected-findings.txt` is hidden so the audit cannot copy it. Anything else the run tries is denied, not asked. `Bash(diff *)` is new in this run, since SKILL.md now asks for hunks written by `diff -u`.

The run loaded the user-level Claude Code configuration (CLAUDE.md and personal skills) in addition to this plugin.

## Output

# Audit: `fixtures/dockerfiles/debian-apt-naive/Dockerfile`

Report only — no files were changed. There is no `.dockerignore` (neither a root one nor a `Dockerfile.dockerignore`), but nothing is `COPY`ed from the context, so it has no effect here. The image runs `curl --version` once and exits, so the server-shaped health rules matter less; I note that on each.

**Linters:** `hadolint` is not installed, so I checked its codes by reading and name them below. `docker build --check` ran and reported **no warnings** (the exec-form `ENTRYPOINT`/`CMD` satisfy `JSONArgsRecommended`, and there are no `ARG`/`ENV` secrets for `SecretsUsedInArgOrEnv`).

## Findings

| Rule | Line | Finding | Severity |
|------|------|---------|----------|
| DW-BASE-01 | 3 | `debian:trixie-slim` has a tag but no digest | should fix |
| DW-BASE-02 | 3 | No `LABEL` metadata | should fix |
| DW-DEPS-01 | 5 | Keeps recommended packages and apt lists; versions unpinned | decide |
| DW-BUILD-04 | 5 | apt/dpkg kept, image not flattened | decide |
| DW-BUILD-10 | 3,5 | slim base keeps apt and dpkg in the image that only runs curl | should fix |
| DW-HEALTH-02 | — | No `HEALTHCHECK` | should fix |
| DW-HEALTH-03 | — | No `STOPSIGNAL` | should fix |
| DW-HEALTH-04 | 8 | No init as PID 1 | should fix |
| DW-USER-01 | 7 | `USER root` is last, and by name not a numeric id | **must fix** |
| DW-USER-02 | 7 | Runtime user (root) owns and can change everything it runs | should fix |

### DW-USER-01 — run as a non-root user (must fix), line 7
`USER root` is the last `USER`, so the container runs as root; it is also a name, not a numeric id the host can resolve (hadolint DL3002, DL3066). Code execution inside then starts with root's privileges instead of an unprivileged user's (CIS 4.1, OWASP Rule 2).
Source: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user

### DW-USER-02 — runtime user must not own what it runs (should fix), line 7
As root, the process owns and can rewrite every file it runs. Switching to a numeric non-root user that owns nothing it runs is the build-time complement to a read-only runtime filesystem (OWASP Rule 8). There is no copied application directory here, so the single `USER` change below covers both DW-USER-01 and DW-USER-02.
Source: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only

### DW-BASE-01 — pin the base image by digest (should fix), line 3
`FROM debian:trixie-slim` floats: the tag can be republished onto different bytes. I resolved the current digest with `docker buildx imagetools inspect debian:trixie-slim` → `sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4` (the multi-platform index). A digest freezes the base, so pair it with Dependabot/Renovate and periodic no-cache rebuilds (DW-SUPPLY-04, trade-offs §1).
Source: https://docs.docker.com/build/building/best-practices/#pin-base-image-versions

### DW-BASE-02 — label the image (should fix), line 3
No `LABEL`s, so the image is not traceable to its source or owner. Add OCI keys (`org.opencontainers.image.*`).
Source: https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys

### DW-HEALTH-04 — minimal init as PID 1 (should fix), line 8
`curl` runs as PID 1 with no init, so orphaned children can become zombies and signals may not be handled. Run it behind `tini` (which the diff also installs). Marginal for a one-shot command, but cheap.
Source: https://github.com/krallin/tini

### DW-HEALTH-03 — set the stop signal (should fix)
No `STOPSIGNAL`; adding `STOPSIGNAL SIGTERM` makes the default explicit.
Source: https://docs.docker.com/reference/dockerfile/#stopsignal

### DW-HEALTH-02 — add a health check (should fix)
No `HEALTHCHECK` (hadolint DL3057, off by default). This matters little for a one-shot `curl --version` that exits immediately — a health check is meant for a long-running process — but the rule is a SHOULD, so I report it and show a minimal one; consider dropping it if this stays a one-shot.
Source: https://docs.docker.com/reference/dockerfile/#healthcheck

### DW-BUILD-10 — leave out package-management tools (should fix), lines 3,5
The slim base ships apt and dpkg, which the running container (just `curl`) does not need; fewer tools leave fewer for an attacker. On a distribution base this is met by a base without them or by pruning (DW-BUILD-04), which brings that rule's trade-off. The `--no-install-recommends` + list cleanup below shrink the surface but do not remove apt/dpkg themselves.
Source: https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images

### DW-DEPS-01 — install only what you need, in one layer (decide)
The `RUN` keeps recommended packages (hadolint DL3015) and leaves the apt lists in the layer (DL3009); versions are unpinned (DL3008). Two parts are clear improvements and are in the diff: `--no-install-recommends` and `rm -rf /var/lib/apt/lists/*` in the same layer. Pinning is the genuine trade-off (**decide**): Hadolint (DL3008) wants pinned versions for reproducibility, but a pin can vanish from a repo that keeps only current versions and blocks automatic security fixes. This repo's default is **not** to pin and to rely on a base-image digest check plus a weekly no-cache rebuild — so the diff leaves versions unpinned with a `# hadolint ignore=DL3008` and its reason. See trade-offs §2.
Source: https://www.cisecurity.org/benchmark/docker

### DW-BUILD-04 — prune then flatten (decide)
A TRADE-OFF, not a fault: you could remove apt/dpkg (keeping the package database `/var/lib/dpkg` for scanners) and flatten into `scratch`. That hardens but breaks `docker exec ... sh` and anything running `ls`/`id`. Left to you; the diff does not do it. See trade-offs §6.
Source: https://docs.docker.com/build/building/multi-stage/

## Proposed diff (covers the fixes above)

Because the file is nine lines and the fixes overlap, here is one diff that applies on its own; comments name the rule each line serves. It does not prune/flatten (DW-BUILD-04) or pin package versions (the DW-DEPS-01 decision). `tini` is installed in the same `RUN` that the init line depends on.

```diff
--- a/Dockerfile
+++ b/Dockerfile
@@ -1,9 +1,30 @@
-# Bad on purpose: an apt install that keeps recommended packages and the package lists,
-# and a container that runs as root. Linted only, never built.
-FROM debian:trixie-slim
+# Runs curl once and exits. Built here only to show the hardened shape.
+ARG DEBIAN_VERSION=trixie-slim
+# DW-BASE-01: tag kept beside the digest so a reader can see what it is
+FROM debian:${DEBIAN_VERSION}@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4
 
-RUN apt-get update && apt-get install -y curl ca-certificates
+# DW-BASE-02: OCI metadata
+LABEL org.opencontainers.image.source="https://github.com/placheckij/dockerfile-wizardry" \
+      org.opencontainers.image.description="curl in a debian-slim image" \
+      org.opencontainers.image.licenses="MIT"
 
-USER root
-ENTRYPOINT ["curl"]
+# DW-DEPS-01: drop recommended packages and remove the apt lists in the same layer.
+# DW-HEALTH-04: tini is installed here so it can be the init below.
+# Versions left unpinned (DL3008) on purpose; see trade-offs section 2.
+# hadolint ignore=DL3008
+RUN apt-get update \
+    && apt-get install -y --no-install-recommends curl ca-certificates tini \
+    && rm -rf /var/lib/apt/lists/*
+
+# DW-USER-01, DW-USER-02: run as a numeric non-root user that owns nothing it runs
+USER 10001:10001
+
+# DW-HEALTH-03: make the default explicit
+STOPSIGNAL SIGTERM
+
+# DW-HEALTH-02: marginal for a one-shot command, kept to satisfy the rule
+HEALTHCHECK CMD ["curl", "--version"]
+
+# DW-HEALTH-04, DW-HEALTH-05: exec form behind a minimal init
+ENTRYPOINT ["tini", "--", "curl"]
 CMD ["--version"]
```

## Rules that pass
- **DW-HEALTH-05** — `ENTRYPOINT`/`CMD` are already exec (JSON array) form; no wrapper script.

## Rules that do not apply
- **DW-BUILD-01** (no dependency manifest or application source), **DW-BUILD-02** (nothing is compiled; the installed packages are the runtime), **DW-BUILD-03** (no `COPY`/`ADD`), **DW-BUILD-05** (single final stage, no build stage to cache for — the layer concern is folded into DW-DEPS-01), **DW-BUILD-06** (no large context), **DW-BUILD-08/09** (no multi-platform or reproducibility need stated), **DW-DEPS-02** (no language tooling), **DW-DEPS-03** (no direct download; curl comes from apt), **DW-HEALTH-01** (one-shot command, no listening port), **DW-SECRET-01** (no secrets).

## Would you like me to apply the diff?
I can apply all of it, or only the must-fix (DW-USER-01/02). I'd re-run `docker build --check` afterward; hadolint isn't installed, so I'd offer to install it rather than do so unasked.

## Limits — not checked
- **Runtime settings** (`docker run`/Compose/Kubernetes flags) — none provided.
- **Registry & publishing**: SBOM, provenance, signing (DW-SUPPLY-01/02).
- **CI pipeline**: cache export (DW-BUILD-07), action pinning (DW-SUPPLY-03), scheduled rebuilds (DW-SUPPLY-04), image scanning (DW-SUPPLY-05), Engine/BuildKit versions (DW-SUPPLY-06) — no workflow files given.
- **The built image**: whether removed files are gone from every layer (DW-BUILD-04/DW-SUPPLY-05) needs the image, not the Dockerfile.
- **Human judgement**: the TRADE-OFF rules (DW-BUILD-04, DW-DEPS-01), which packages curl truly needs, and the `manual`-checked rules read by eye only.
- `hadolint` was not run (not installed); its codes above were determined by reading.

**One must-fix remains open (DW-USER-01), so this Dockerfile does not pass the checks** — it fails DW-USER-01, and the should-fix findings (DW-BASE-01/02, DW-BUILD-10, DW-HEALTH-02/03/04, DW-USER-02) and the DW-DEPS-01 / DW-BUILD-04 decisions are still open. The rules were last verified on the dates shown with each rule; sources may have changed since.

## Review

Reviewed by hand against `expected-findings.txt` (9 rules) and the rulebook.

**Expected findings.** All nine are reported, each with the severity its strength gives:
DW-USER-01 (must fix); DW-BASE-01, DW-BASE-02, DW-BUILD-10, DW-HEALTH-02, DW-HEALTH-03,
DW-HEALTH-04 and DW-USER-02 (should fix); DW-DEPS-01 (decide). It also shows DW-BUILD-04
as a decision. Since this run, SKILL.md says that only DW-DEPS-01's pinning part is a
decision, so the recommended packages and kept apt lists would now be should fix; the run
called those parts clear improvements and fixed them in the diff. For DW-HEALTH-02 and -04 it adds a note that they matter less for a
one-shot command, as SKILL.md asks.

**Rule ids.** Every id it cites exists in `references/rules.md` (checked by script).

**Linters.** `docker build --check` ran and reported no warnings. Hadolint is not
installed on this machine, so the run says so and names the Hadolint codes by reading,
each under the rule that names it: DL3002 and DL3066 under DW-USER-01, DL3015, DL3009 and
DL3008 under DW-DEPS-01, DL3057 under DW-HEALTH-02. DW-USER-01 has since come to call
DL3066 advisory; the must-fix stands on `USER root` alone.

**Digests and versions.** The digest for `debian:trixie-slim`
(`sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4`) matches
`docker buildx imagetools inspect debian:trixie-slim` run afterwards. No package version
or checksum is claimed.

**Trade-offs.** DW-DEPS-01 is shown as a decision, with both sides of trade-offs §2. Its
parts that nobody contests (`--no-install-recommends`, removing the apt lists) are called
clear improvements and go into the diff, and versions stay unpinned. The reason sits on
the line above `# hadolint ignore=DL3008`, which sits directly above the `RUN`.
DW-BUILD-04 is a decision and is not applied.

**Wording.** No "secure" claim. DW-HEALTH-05 is the only rule it lists as passing, and it
does pass. The close names the open must-fix finding and says the file does not pass.

**The proposed diff.** One combined diff, as SKILL.md asks when fixes overlap. Run against
a copy of the fixture outside the repository, `git apply --check -v` printed `Checking
patch Dockerfile...` and exited 0, and `patch --dry-run -p1` also applies it. After the
diff was applied, the result lints clean: pinned Hadolint v2.15.1 with `--info DL3057`
reported nothing, and `docker buildx build --call check` gave "Check complete, no
warnings found." The JSON does not record tool calls, so it does not show whether `diff`
wrote the hunk; the run had no permission denials.

**What it missed or got wrong.**
- The diff headers name `a/Dockerfile`, not the path the run was given
  (`fixtures/dockerfiles/debian-apt-naive/Dockerfile`), so from the repository root,
  where the run started, `git apply` tries the root `Dockerfile` and fails. It applies
  only from inside the fixture directory, which is where it was checked above. SKILL.md's
  `diff` recipe hard-coded `Dockerfile` at the time; it now takes the file's path.
- It offers to apply "only the must-fix (DW-USER-01/02)", but DW-USER-02 is a SHOULD, and
  its own table rates it should fix. DW-USER-01 is the only must-fix.
- The diff sets `USER 10001:10001` without creating that user and group. That runs, but
  DW-USER-01 asks for a dedicated user and group with those ids.
- The `HEALTHCHECK` runs `curl --version`, which tests nothing. DW-HEALTH-02 asks for a
  check that exercises the application. The run calls the check marginal and suggests
  dropping it.
- The `LABEL` values (this repository's URL, MIT) are guesses, and this time the run does
  not call them placeholders.
- Two comment lines carry two ids each (`DW-USER-01, DW-USER-02` and
  `DW-HEALTH-04, DW-HEALTH-05`), where the skill asks for one id per line.
- It calls the no-pin choice "this repo's default", with a weekly no-cache rebuild. That
  describes the rulebook repository's own practice, which the rule text mentions, not
  anything the audited project has set up.

**Earlier runs.** An earlier run marked DW-HEALTH-02 "does not apply" to a one-shot
command, and in the previous committed run three of four diffs did not apply: two had
hand-counted hunk lines, and one had no context after the change. SKILL.md now defines "does not apply" and asks for
`diff -u` to write the hunks; this run's diff applies.
