# Worked example: auditing `debian-apt-naive` with the skill

Command, run from the repository root on 2026-11-22 with Claude Code 2.1.323 (`claude --version`); the model was `claude-opus-5-5`. The output below is the run's `result` field, unedited.

```sh
claude -p --setting-sources project --plugin-dir . --no-session-persistence \
  --permission-mode dontAsk \
  --tools Read Grep Glob Bash Skill \
  --allowedTools "Bash(docker *)" "Bash(hadolint *)" "Bash(command -v *)" "Bash(which *)" "Bash(grep *)" "Bash(head *)" "Bash(tail *)" "Bash(echo *)" "Bash(cd *)" "Bash(awk *)" "Bash(cat *)" "Bash(uv --version)" "Bash(ls *)" "Bash(diff *)" \
  --disallowedTools "Read(./fixtures/**/expected-findings.txt)" "Bash(*expected-findings*)" "Bash(docker push *)" "Bash(docker rm *)" "Bash(docker rmi *)" "Bash(docker image rm *)" "Bash(docker system *)" "Bash(docker volume *)" \
  --output-format stream-json --verbose \
  -- "Audit fixtures/dockerfiles/debian-apt-naive/Dockerfile with the dockerfile-wizardry skill. Report only; do not edit files."
```

The tool list and permissions keep the run from changing files: there is no Edit or Write tool, Bash is limited to Docker (destructive subcommands denied), the linters, `diff` and a few read-only commands, and the fixture's `expected-findings.txt` is hidden so the audit cannot copy it. Anything else the run tries is denied, not asked. `stream-json` records each tool call, so the review below can say which commands ran.

The run's init event lists this plugin, at version 0.2.0 plus the unreleased changes on `main`, and Claude Code's built-in plugins.

## Output

# Audit: `fixtures/dockerfiles/debian-apt-naive/Dockerfile`

The file breaks one must-fix rule (DW-USER-01) and seven should-fix rules. Nothing was edited.

Before you apply anything: this fixture is meant to be bad. CI runs `.github/scripts/check_fixtures.py` on it, and that script needs Hadolint and the build checks to report exactly the codes in `expected-findings.txt`. Applying these fixes would break that CI check unless the fixture's labels are changed too.

**Linters.** I couldn't run Hadolint: it isn't installed and its Docker image isn't pulled locally. I checked those rules by reading the file, so every Hadolint code below says "would fire" and none of them was actually run. `docker build --check` did run and reported no warnings.

**Base image.** `debian:trixie-slim` names its release line and was built on 2026-11-04, so it is still being rebuilt. Its current digest is `sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2`.

| Rule | Line | Finding | Severity |
|------|------|---------|----------|
| DW-BASE-01 | 3 | Base image is not pinned by digest | should fix |
| DW-BASE-02 | – | No `LABEL`s, so no OCI metadata | should fix |
| DW-BUILD-04 | – | Image is not pruned or flattened; the file keeps the full base (apt, dpkg, shell) | decide |
| DW-BUILD-10 | 3 | The final image keeps `apt` and `dpkg` from the Debian base | should fix (no diff) |
| DW-DEPS-01 | 5 | Recommended packages get installed: no `--no-install-recommends` (DL3015 would fire) | should fix |
| DW-DEPS-01 | 5 | apt lists stay in the layer: no `rm -rf /var/lib/apt/lists/*` (DL3009 would fire) | should fix |
| DW-DEPS-01 | 5 | Package versions are not pinned (DL3008 would fire) | decide |
| DW-HEALTH-02 | – | No `HEALTHCHECK` (DL3057 would fire if enabled) | should fix |
| DW-HEALTH-03 | – | No `STOPSIGNAL` | should fix |
| DW-HEALTH-04 | 8 | No init: `curl` runs as PID 1 | should fix |
| DW-USER-01 | 7 | `USER root`: the container runs as root (DL3002 would fire; DL3066 probably would too, since `root` is a name) | must fix |
| DW-USER-02 | 7 | Because it runs as root, the process owns and can change the `curl` it runs | should fix |

## Why each one matters

- **DW-BASE-01:** a tag can be republished, so the same file can build different bytes later. A digest names exactly one image. Pair the pin with Dependabot or Renovate and periodic rebuilds (DW-SUPPLY-04, trade-offs §1). Source: https://docs.docker.com/build/building/best-practices/#pin-base-image-versions
- **DW-BASE-02:** labels let you trace an image back to its source and owner. I left out `org.opencontainers.image.version` because there's no version to use. Source: https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
- **DW-BUILD-04, decide:** the file keeps everything.
  - For pruning and flattening: deleted files are really gone and there are fewer tools to abuse.
  - Against: it's harder to debug and the metadata has to be declared again.
  - No diff unless you ask.
- **DW-BUILD-10:** NCSC says a container shouldn't need package managers at runtime. Your options are a base without one (trade-offs §6) or pruning (DW-BUILD-04). It's your choice, so there's no diff. Source: https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
- **DW-DEPS-01:** every extra package adds size and attack surface, and lists left behind stay in the layer for good. Source: https://docs.docker.com/build/building/best-practices/#run
  - Pinning is the decide part (trade-offs §2, Pinning operating-system package versions).
    - For: reproducible builds.
    - Against: pinned versions disappear from the repository and you stop getting automatic fixes.
  - The file doesn't pin, which matches the skill's default.
  - Hadolint runs on this file in CI, so the diff adds `# hadolint ignore=DL3008` with its reason.
- **DW-HEALTH-02 / 03 / 04:** without them, Docker can't report whether the application works, shutdown is left to the default signal, and there's no PID 1 to reap zombies and pass signals on.
  - For a one-shot `curl --version` all three matter little, but they are still findings.
  - Sources: https://docs.docker.com/reference/dockerfile/#healthcheck, https://docs.docker.com/reference/dockerfile/#stopsignal, https://github.com/krallin/tini
  - The diff installs `tini` from apt, so the binary its entrypoint calls exists in the image.
- **DW-USER-01:** if the process is compromised, the attacker starts as root. The diff creates user and group 10001 and switches to them by number. Source: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user
- **DW-USER-02:** once the user is 10001, `/usr/bin/curl` stays owned by root and that user can't change it. Source: https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only

## Combined diff

One diff covers DW-BASE-01, DW-BASE-02, DW-DEPS-01 (recommends and lists), DW-HEALTH-02, DW-HEALTH-03, DW-HEALTH-04, DW-USER-01 and DW-USER-02. It's a single diff because all the changes are within three lines of each other.

I wrote the hunk header by hand because the command that generates it was denied, so check it before using `git apply`. The comment on lines 1–2 would also be out of date after the fix.

```diff
--- a/fixtures/dockerfiles/debian-apt-naive/Dockerfile
+++ b/fixtures/dockerfiles/debian-apt-naive/Dockerfile
@@ -1,9 +1,22 @@
 # Bad on purpose: an apt install that keeps recommended packages and the package lists,
 # and a container that runs as root. Linted only, never built.
-FROM debian:trixie-slim
+FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
 
-RUN apt-get update && apt-get install -y curl ca-certificates
+LABEL org.opencontainers.image.source="https://github.com/placheckij/dockerfile-wizardry" \
+      org.opencontainers.image.description="curl on Debian trixie-slim" \
+      org.opencontainers.image.licenses="MIT"
 
-USER root
-ENTRYPOINT ["curl"]
+# Versions are not pinned: the base digest is updated and the image rebuilt instead (trade-offs §2)
+# hadolint ignore=DL3008
+RUN apt-get update \
+ && apt-get install -y --no-install-recommends curl ca-certificates tini \
+ && rm -rf /var/lib/apt/lists/*
+
+RUN groupadd --system --gid 10001 app \
+ && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
+
+HEALTHCHECK CMD ["curl", "--version"]
+STOPSIGNAL SIGTERM
+USER 10001:10001
+ENTRYPOINT ["/usr/bin/tini", "--", "curl"]
 CMD ["--version"]
```

## Passing and not applicable

- **Pass:**
  - DW-BASE-03
  - DW-HEALTH-05: `ENTRYPOINT` and `CMD` use exec form and there's no wrapper script.
  - DW-SECRET-01: no `ARG`, `ENV` or `COPY`, and the build check found no warnings.
- **Don't apply:**
  - DW-BUILD-01, DW-BUILD-02, DW-BUILD-05: there are no manifests, nothing to compile and no build stage.
  - DW-BUILD-03: no `COPY` or `ADD`.
  - DW-BUILD-06: no source tree.
  - DW-BUILD-08: single platform.
  - DW-DEPS-02: no language tooling.
  - DW-DEPS-03: nothing is downloaded directly.
  - DW-HEALTH-01: `curl` doesn't listen on a port.

## Summary

The Dockerfile **passes the listed checks** DW-BASE-03, DW-HEALTH-05 and DW-SECRET-01.

It **fails**:
- DW-USER-01 (must fix)
- DW-BASE-01, DW-BASE-02, DW-BUILD-10, DW-DEPS-01 (recommends, lists), DW-HEALTH-02, DW-HEALTH-03, DW-HEALTH-04, DW-USER-02 (should fix)

Still to decide: DW-BUILD-04 and DW-DEPS-01 (pinning).

Which rule ids should I apply? I'd also need to know whether `expected-findings.txt` should be updated with them or the fixture left bad on purpose. If you want, I can also build the image before and after the fixes and compare them; this needs network access to pull the base.

## Not checked

- **Hadolint:** not run, so its codes come from reading the file.
- **Publishing (DW-SUPPLY-01, DW-SUPPLY-02):** the file says it is never built and no workflow pushes it, so it looks unpublished. Please confirm.
- **CI rules (DW-BUILD-07, DW-SUPPLY-03 to DW-SUPPLY-06):** no workflow builds or scans this image. CI only lints it, and the Trivy config scan skips it.
- **Reproducible builds (DW-BUILD-09):** you haven't said whether reproducible output matters.
- **Built image:** whether removed files are gone from every layer needs the image, which wasn't built.
- **Runtime settings:** not covered by the rulebook.
- **Manual rules:** checked by reading only.

## Review

Reviewed by hand against `expected-findings.txt` (9 rules) and the rulebook.

**Expected findings.** All nine are reported, each with the severity its strength gives:
DW-USER-01 (must fix); DW-BASE-01, DW-BASE-02, DW-BUILD-10, DW-HEALTH-02, DW-HEALTH-03,
DW-HEALTH-04 and DW-USER-02 (should fix). DW-DEPS-01 gets one row per part: the
recommended packages and kept apt lists are should fix, and only version pinning is a
decision, as SKILL.md now says. DW-BUILD-04 is shown as a decision. DW-BUILD-10 is
reported at its severity without a diff, naming pruning or another base as the options,
since only a trade-off can fix it. For the health rules it notes that they matter little
for a one-shot command but are still findings.

**DW-BASE-01.** The fix writes the base reference out in `FROM`
(`debian:trixie-slim@sha256:...`), as the rule now asks. The previous recording built it
from `ARG DEBIAN_VERSION`, which the rule now fails.

**Rule ids.** Every id it cites exists in `references/rules.md` (checked by script).

**Linters.** `docker build --check` ran and reported no warnings. Hadolint is not
installed on this machine, so the run says so and names the codes by reading, each under
its rule. Pinned Hadolint v2.15.1 with `--info DL3057`, run afterwards on the fixture,
reports exactly the codes it named: DL3057, DL3008, DL3015, DL3009, DL3066 and DL3002.
The run hedged on DL3066 ("probably would"); it does fire.

**Digests and versions.** The digest for `debian:trixie-slim`
(`sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2`) matches
`docker buildx imagetools inspect debian:trixie-slim` run afterwards, and the build date
it read for DW-BASE-03 (2026-11-04) is what that command prints. No package version or
checksum is claimed.

**Trade-offs.** Versions stay unpinned, with the reason on the line above
`# hadolint ignore=DL3008` and that line directly above the `RUN`. The ignore line is
allowed because CI runs Hadolint on this file (`check_fixtures.py`), and the run cites
that. DW-BUILD-04 is not applied.

**Wording.** No "secure" claim. It lists DW-BASE-03, DW-HEALTH-05 and DW-SECRET-01 as
passing, and each does. The close names the open must-fix finding and says the file
fails. It also warns that applying the fixes would break `check_fixtures.py`, since the
fixture is bad on purpose.

**The proposed diff.** The run's `diff -u` call was denied: it was one compound command
(`head -3 LICENSE; f=...; diff -u ... <<'EOF' ...; echo`) that this setup's permission
rules did not match. The run then read `LICENSE` with Read, wrote the hunk by hand and
said so. The headers now name the path the run was given, so the diff applies from the
repository root: against a copy of the fixture at the same path, `git apply -v` printed
`Applied patch fixtures/dockerfiles/debian-apt-naive/Dockerfile cleanly.` After the
diff, the result lints clean: pinned Hadolint v2.15.1 with `--info DL3057` reported
nothing, and `docker buildx build --call check` gave "Check complete, no warnings found."

**What it missed or got wrong.**
- The `HEALTHCHECK` runs `curl --version`, which tests nothing. DW-HEALTH-02 asks for a
  check that exercises the application. The run says the health rules matter little
  here but does not say that this check proves nothing.
- The `description` label is its own wording, not taken from anywhere, and it is not
  called a placeholder. The source URL and the MIT licence come from this repository,
  where the fixture lives (it read `LICENSE`).
- It wrote the hunk by hand instead of trying `diff -u` again as a plain command. The
  hunk was right this time, but SKILL.md asks for `diff` to write it.

**Earlier runs.** The previous recording (2026-11-03) pinned the base through an `ARG`,
set `USER 10001:10001` without creating that user, offered DW-USER-02 as a must-fix, and
named `a/Dockerfile` in its diff headers, so `git apply` failed from the repository
root. This run creates the user and group, rates DW-USER-02 should fix, and its diff
applies from the root.
