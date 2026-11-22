# Worked example: auditing `python-naive` with the skill

Command, run from the repository root on 2026-11-22 with Claude Code 2.1.323 (`claude --version`); the model was `claude-opus-5-5`. The output below is the run's `result` field, unedited.

```sh
claude -p --setting-sources project --plugin-dir . --no-session-persistence \
  --permission-mode dontAsk \
  --tools Read Grep Glob Bash Skill \
  --allowedTools "Bash(docker *)" "Bash(hadolint *)" "Bash(command -v *)" "Bash(which *)" "Bash(grep *)" "Bash(head *)" "Bash(tail *)" "Bash(echo *)" "Bash(cd *)" "Bash(awk *)" "Bash(cat *)" "Bash(uv --version)" "Bash(ls *)" "Bash(diff *)" \
  --disallowedTools "Read(./fixtures/**/expected-findings.txt)" "Bash(*expected-findings*)" "Bash(docker push *)" "Bash(docker rm *)" "Bash(docker rmi *)" "Bash(docker image rm *)" "Bash(docker system *)" "Bash(docker volume *)" \
  --output-format stream-json --verbose \
  -- "Audit fixtures/dockerfiles/python-naive/Dockerfile with the dockerfile-wizardry skill. Report only; do not edit files."
```

The tool list and permissions keep the run from changing files: there is no Edit or Write tool, Bash is limited to Docker (destructive subcommands denied), the linters, `diff` and a few read-only commands, and the fixture's `expected-findings.txt` is hidden so the audit cannot copy it. Anything else the run tries is denied, not asked. `stream-json` records each tool call, so the review below can say which commands ran.

This file was moved out of the fixture directory for the run. `ADD . /app` copies the whole directory, and the skill reads every copied file, so a first attempt read the previous recording and its review before writing its own; that attempt is not shown.

The run's init event lists this plugin, at version 0.2.0 plus the unreleased changes on `main`, and Claude Code's built-in plugins.

## Output

# Audit: `fixtures/dockerfiles/python-naive/Dockerfile`

**This file is a deliberately bad fixture.** `check_fixtures.py` in CI expects Hadolint and Docker's build checks to report exactly the codes listed in `expected-findings.txt`. If you apply any fix below, update that file too or CI will fail. I didn't edit anything.

**What I checked:**
- **Build context:** the fixture directory, the same one `check_fixtures.py` passes to `docker buildx build --call check`.
- **No `.dockerignore`:** there is none in the context.
- **`ADD . /app`** copies `Dockerfile` and `expected-findings.txt`. I didn't open `expected-findings.txt` because reading it was denied (see Limits).
- **Missing files:** `requirements.txt` and `app.py` aren't in the context. The image can't build as it is, before or after the fixes. The header says it was never built.
- **Docker build check** (ran): `SecretsUsedInArgOrEnv` on line 7 and `JSONArgsRecommended` on line 14.
- **Hadolint** isn't installed here and I didn't pull its image. By reading, these codes would fire: DL3007 (line 3), DL3020 (line 10), DL3042 (line 11), DL3025 (line 14) and DL3057 (with `--info DL3057`). DL3064 may fire on line 7. None of these were run. DL3002 doesn't fire because there is no explicit `USER root`.
- **Base lookups** (ran):
  - `python:latest` is `sha256:46837ed3…6182`: Python 3.15.2, built 2026-11-05.
  - `python:3.15-slim` and `python:3.15-slim-trixie` are both `sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928`: 3.15.2 on Debian trixie, built 2026-11-05.

| Rule | Line | Finding | Severity |
|------|------|---------|----------|
| DW-BASE-01 | 3 | `python:latest` is a floating tag with no digest (DL3007) | should fix |
| DW-BASE-02 | – | No `LABEL`s | should fix |
| DW-BUILD-01 | 10–11 | The whole context is copied before `pip install`, so any code change reruns the install. Whether the install is locked can't be seen (no `requirements.txt`) | should fix |
| DW-BUILD-02 | 3–11 | One stage: pip runs in the runtime image | should fix |
| DW-BUILD-03 | 10 | `ADD` used for local files (DL3020). The whole context is copied with no `.dockerignore`, which puts `Dockerfile` and `expected-findings.txt` in the image | must fix |
| DW-BUILD-04 | – | Not pruned or flattened | decide |
| DW-BUILD-05 | 11 | pip's downloads go into a layer instead of a cache mount in a build stage | should fix |
| DW-BUILD-10 | 3 | The full `python` image ships apt/dpkg and the buildpack-deps toolchain and SCM clients. Slim still ships apt | should fix |
| DW-DEPS-02 | 11 | `pip install` without `--no-cache-dir` or a cache mount leaves the cache in the layer (DL3042) | should fix |
| DW-HEALTH-02 | – | No `HEALTHCHECK` (DL3057) | should fix |
| DW-HEALTH-03 | – | No `STOPSIGNAL` | should fix |
| DW-HEALTH-04 | 14 | No init as PID 1, and no Compose `init: true` found | should fix |
| DW-HEALTH-05 | 14 | Shell-form `CMD` (JSONArgsRecommended, DL3025) | should fix |
| DW-SECRET-01 | 7 | `ARG API_TOKEN` passes a secret through a build argument (SecretsUsedInArgOrEnv) | must fix |
| DW-USER-01 | – | No `USER`, so the container runs as root | must fix |
| DW-USER-02 | 10, 14 | The runtime user (root) owns `/app` and the installed packages | should fix |

## Why each one matters

- **DW-BASE-01:** a tag can be republished, so the same file can build on different bytes. Moving to the release-line slim tag also settles the base family; see trade-offs §6. https://docs.docker.com/build/building/best-practices/#pin-base-image-versions
- **DW-BASE-02:** labels tie the image to its source and owner. https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys
- **DW-BUILD-01:** installing dependencies before copying code keeps that layer cached. https://docs.docker.com/build/building/best-practices/#leverage-build-cache
- **DW-BUILD-02:** build tools and caches never reach the final image. https://docs.docker.com/build/building/best-practices/#use-multi-stage-builds
- **DW-BUILD-03:** anything copied stays in the image for good. `ADD` can also unpack archives and fetch URLs. https://docs.docker.com/build/building/best-practices/#exclude-with-dockerignore
- **DW-BUILD-04 (decide):**
  - For: pruning and flattening into `scratch` removes package managers and tools from every layer.
  - Against: it costs `docker exec … sh` debugging, and it's defense in depth, not a barrier.
  - The file currently takes the "don't prune" side. No diff unless you want it.
- **DW-BUILD-05:** a cache mount survives between builds without ending up in the image. https://docs.docker.com/build/cache/optimize/
- **DW-BUILD-10:** NCSC says containers shouldn't need package managers or remote-management tools. The diff below moves to slim, which drops the toolchain and SCM clients, but apt stays. The options for removing it are a base without a package manager (trade-offs §6) or pruning (DW-BUILD-04). That's your call, so there's no diff for it. https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
- **DW-DEPS-02:** a cache left in a layer adds size that can never be removed. pip compiles bytecode at install time by default, which covers the root-owned packages after the fix. https://docs.astral.sh/uv/guides/integration/docker/
- **DW-HEALTH-02:** without a check, Docker only knows whether the process is alive, not whether the app works. The diff uses Python's `urllib`, so no `curl` is needed. The `/` endpoint is an assumption, marked TODO. https://docs.docker.com/reference/dockerfile/#healthcheck
- **DW-HEALTH-03:** this makes the shutdown signal explicit. https://docs.docker.com/reference/dockerfile/#stopsignal
- **DW-HEALTH-04:** without an init, zombies pile up and signals may not reach the app. https://github.com/krallin/tini
- **DW-HEALTH-05:** in shell form, `sh` gets SIGTERM and doesn't pass it on. https://docs.docker.com/reference/build-checks/json-args-recommended/
- **DW-SECRET-01:** build args persist in the image and in `max` provenance. Nothing uses `API_TOKEN`, so the diff removes it. If the build does need it, use `RUN --mount=type=secret,id=api_token,required=true …`. https://docs.docker.com/build/building/secrets/
- **DW-USER-01:** if the process is compromised, it gets root. https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user
- **DW-USER-02:** an owner can always `chmod` its own code back to writable and tamper with it. https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only

## Diff

The fixes overlap, so this is one diff covering DW-BASE-01, DW-BASE-02, DW-BUILD-01, DW-BUILD-02, DW-BUILD-03, DW-BUILD-05, DW-DEPS-02, DW-HEALTH-02, DW-HEALTH-03, DW-HEALTH-04, DW-HEALTH-05, DW-SECRET-01, DW-USER-01 and DW-USER-02. `diff -u` generated it; it was not written to disk.

```diff
--- a/fixtures/dockerfiles/python-naive/Dockerfile
+++ b/fixtures/dockerfiles/python-naive/Dockerfile
@@ -1,14 +1,39 @@
 # Bad on purpose: a first-draft Python image. The rules it breaks are listed in
 # expected-findings.txt next to this file. Linted only, never built.
-FROM python:latest
+FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS build
 
-# a token as a build argument ends up in the image metadata (no value here, so the
-# repository's secret scan has nothing to find)
-ARG API_TOKEN
+WORKDIR /app
+COPY requirements.txt ./
+# DW-BUILD-05: pip's download cache stays in the builder, out of the layer
+RUN --mount=type=cache,target=/root/.cache/pip \
+    python -m venv /opt/venv \
+ && /opt/venv/bin/pip install -r requirements.txt
 
+FROM python:3.15-slim-trixie@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
+
+LABEL org.opencontainers.image.title="python-naive" \
+      org.opencontainers.image.description="TODO: what the image is for" \
+      org.opencontainers.image.source="https://github.com/placheckij/dockerfile-wizardry"
+
+# OS packages are not pinned; updates come from rebuilding on a new base digest (trade-offs §2)
+# hadolint ignore=DL3008
+RUN apt-get update \
+ && apt-get install -y --no-install-recommends tini \
+ && rm -rf /var/lib/apt/lists/* \
+ && groupadd --system --gid 10001 app \
+ && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app
+
+# DW-USER-02: dependencies and code stay root-owned, readable by the runtime user
+COPY --from=build /opt/venv /opt/venv
+ENV PATH="/opt/venv/bin:$PATH"
 WORKDIR /app
-ADD . /app
-RUN pip install -r requirements.txt
+COPY app.py ./
 
 EXPOSE 8000
-CMD python app.py
+USER 10001:10001
+# TODO: point the check at the application's health endpoint
+HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
+  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)"]
+STOPSIGNAL SIGTERM
+ENTRYPOINT ["/usr/bin/tini", "--"]
+CMD ["python", "app.py"]
```

**Notes on the diff:**
- **`# hadolint ignore=DL3008`:** I added it because CI runs Hadolint on this path through `check_fixtures.py`. It follows the default of not pinning apt packages (trade-offs §2).
- **Bundled frontend:** no `# syntax=` line, so the build uses the bundled frontend.
- **App modules:** add any modules `app.py` imports to the `COPY`.
- **Locked install (DW-BUILD-01):** use `--require-hashes` if `requirements.txt` has hashes. I couldn't check this.
- **Digest updates:** Dependabot or Renovate plus periodic rebuilds should keep the digest current (DW-SUPPLY-04, trade-offs §1).
- **Not linted:** running the build check on the fixed file was denied, so it hasn't been linted.

## Pass / not applicable

- **Passes:** DW-BASE-03. `latest` is above the release line, so no tag comparison applies, and the base was built on 2026-11-05. The proposed `3.15-slim-trixie` was built the same day.
- **Does not apply:**
  - DW-BUILD-06: no large tree is used only to produce an artifact.
  - DW-BUILD-08: no file I read sets up a multi-platform build.
  - DW-DEPS-01: the file installs no OS packages.
  - DW-DEPS-03: nothing is downloaded during the build.

## Which fixes to apply?

Tell me which rule ids you want. Because this is a fixture, the usual answer may be "none", or applying them to a copy. Building before and after isn't possible, since `requirements.txt` and `app.py` are missing from the context.

## Result

**Passes the listed checks:** DW-BASE-03.

**Doesn't pass:**
- **Must fix:** DW-BUILD-03, DW-SECRET-01, DW-USER-01.
- **Should fix:** DW-BASE-01, DW-BASE-02, DW-BUILD-01, DW-BUILD-02, DW-BUILD-05, DW-BUILD-10, DW-DEPS-02, DW-HEALTH-02, DW-HEALTH-03, DW-HEALTH-04, DW-HEALTH-05, DW-USER-02.
- **Decide:** DW-BUILD-04.

## Limits

- **Files not opened:** `expected-findings.txt` (reading it was denied). I ran no secret scan over it, so even after the fix, DW-SECRET-01 and DW-BUILD-03 can't be listed as passing until it has been read.
- **Partly checked:**
  - DW-HEALTH-01: `EXPOSE 8000` is present, but I can't confirm the app listens on 8000 because `app.py` isn't in the context.
  - DW-SUPPLY-06: there's no `# syntax=` frontend, but Engine and BuildKit versions weren't checked.
- **Registry and publishing:** DW-SUPPLY-01 and DW-SUPPLY-02. No workflow pushes this image and the header says it's never built, but you haven't confirmed it isn't published.
- **CI pipeline:** DW-BUILD-07, DW-SUPPLY-03, DW-SUPPLY-04 and DW-SUPPLY-05. CI only lints this file and doesn't build, scan or publish it. Trivy's config scan skips it.
- **Reproducible output:** DW-BUILD-09, since it isn't stated whether that matters.
- **Built image:** checking what's left in the layers (DW-BUILD-04, DW-SUPPLY-05) needs a build, which isn't possible here.
- **Runtime settings** beyond `init`: none were found or checked.
- **Checked by reading only:** the manual rules, and which packages the app actually needs.
- **Linters:** Hadolint wasn't run.
- **Rule dates:** the rules were last verified on the dates shown with each one.

## Review

Reviewed by hand against `expected-findings.txt` (14 rules) and the rulebook.

**Expected findings.** All 14 are reported, each with the severity its strength gives:
DW-BUILD-03, DW-SECRET-01 and DW-USER-01 must fix, the rest should fix. DW-BUILD-04 is
shown as a decision. DW-BUILD-10 is reported at its severity without a diff, naming
pruning or another base as the options, and it now says correctly that slim still
ships apt. It also reports DW-BUILD-05, which is not expected (see below).

**DW-BASE-01.** The fix writes the base reference out in both `FROM` lines
(`python:3.15-slim-trixie@sha256:...`), as the rule now asks. The previous recording kept
the version and digest in `ARG`s, which the rule now fails.

**Rule ids.** Every id it cites exists in `references/rules.md` (checked by script).

**Linters.** `docker buildx build --call check` ran and reported `SecretsUsedInArgOrEnv`
and `JSONArgsRecommended`, each under its rule. Hadolint is not installed on this
machine, so the run says so and names the codes by reading. Pinned Hadolint v2.15.1 with
`--info DL3057`, run afterwards on the fixture, reports exactly the codes it named:
DL3007, DL3057, DL3064, DL3020, DL3042 and DL3025. It hedged on DL3064 ("may fire"); it
does fire. It says DL3002 does not fire, which is right.

**Digests and versions.** The digests for `python:latest`
(`sha256:46837ed3105db0029b6d656816185c6258e3b39690532fb782428e0a5fd76182`) and
`python:3.15-slim-trixie`
(`sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928`) match
`docker buildx imagetools inspect` run afterwards, and so does the build date it gives
(2026-11-05). It took Python 3.15 from the version `python:latest` points to, and says
so.

**Copied files.** `ADD . /app` copies the hidden `expected-findings.txt`, so the run
tried to read it, as SKILL.md asks. The read was denied, and the run puts that file under
Limits and keeps DW-SECRET-01 and DW-BUILD-03 off the passing list.

**Trade-offs.** The unpinned `tini` gets its reason on the line above
`# hadolint ignore=DL3008`, which sits directly above the `RUN`. The ignore line is
allowed because CI runs Hadolint on this file (`check_fixtures.py`), and the run cites
that. DW-BUILD-04 is not applied.

**Wording.** No "secure" claim. DW-BASE-03 is the only rule it lists as passing, and it
does pass. The close names the three open must-fix findings and says the file does not
pass. It also warns that applying the fixes would break `check_fixtures.py`.

**The proposed diff.** `diff -u` wrote it, with headers that name the path the run was
given, so it applies from the repository root: against a copy of the fixture at the same
path, `git apply -v` printed `Applied patch fixtures/dockerfiles/python-naive/Dockerfile
cleanly.` The run's build check on the fixed file was denied (a heredoc piped into
`grep`), and it says the fix was not linted. After the diff, `docker buildx build --call
check` gave "Check complete, no warnings found." Pinned Hadolint v2.15.1 with
`--info DL3057` reported one code: DL3057 on the build stage's `FROM`.

**What it missed or got wrong.**
- It reports DW-BUILD-05 on the original single stage. That stage is the final stage,
  where the rule asks only for cleanup in the same layer; the pip cache left there is
  DW-DEPS-02, which it also reports. The fix's build stage does use a cache mount, as
  the rule asks.
- The fix leaves DL3057 on the build stage's `FROM`. That is not a DW-HEALTH-02 finding,
  but SKILL.md puts `# hadolint ignore=DL3057` there, with its reason, where Hadolint
  runs, as it does here. The run did not see it because Hadolint was not installed and
  its own check of the fix was denied.
- The fix copies the virtual environment and `app.py` owned by `root:root` and readable
  by everyone. They are not writable by the runtime user, which is the point of
  DW-USER-02, but the rule asks for them to be readable through a group, and the comment
  above the `COPY` does not mention that.

**Earlier runs.** The previous recording (2026-11-03) could not run `diff` and gave a
whole replacement file, disabled pip's cache instead of mounting it in the build stage,
said DW-BUILD-10 was met by slim, and chose Python 3.13 without saying so. This run's
diff applies, the build stage uses a cache mount, DW-BUILD-10 stays open, and the
version comes from the tag it replaces.
