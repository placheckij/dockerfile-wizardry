---
name: dockerfile-wizardry
argument-hint: "[audit|create] [path]"
description: Use when writing a new Dockerfile or reviewing an existing one. Create mode generates a Dockerfile and .dockerignore for a project; audit mode checks an existing Dockerfile rule by rule and proposes fixes as diffs. Use it whenever the user writes, creates, reviews, audits, hardens or optimizes a Dockerfile or a .dockerignore. Every finding and choice cites a rule id (DW-...) from a sourced rulebook of build, security and supply-chain rules.
---

# Dockerfile Wizardry

This skill applies a rulebook of Dockerfile rules, each backed by public sources (CIS
Docker Benchmark, OWASP, Docker's documentation, NCSC and others). The rules are the
substance; this file only says how to apply them. Two modes: **audit** an existing
Dockerfile, or **create** one for a project.

## 1. Rules come from the rulebook

- Before doing anything else, read `references/rules.md` in full. Each rule has an id
  (`DW-BASE-01`, ...), a title, a strength (`MUST`, `SHOULD` or `TRADE-OFF`), a
  statement, the reasons, how to check it, and its sources.
- Cite the rule id for every finding you report and every non-obvious choice you make.
  Use only ids that appear in `references/rules.md`; never make one up.
- Take a rule's meaning, strength and sources from the file, not from memory.
- Where sources disagree, `references/tradeoffs.md` sets out both sides in numbered
  sections. Cite them as "trade-offs §2 (Pinning operating-system package versions)".
- Advice that no rule covers (language-specific tips, a linter code no rule names) is
  allowed, but label it "not from the rulebook" so the user can tell it apart.
- Links in the references are absolute GitHub URLs; use them as they are.

## 2. Audit mode

Use this when the user has a Dockerfile and wants it reviewed, hardened or optimized.
Here "the final stage" is the stage the image is built from: the last stage in the file,
unless the workflow, build script or Compose file that builds this image names another
(`--target`, or `target:` under `build:` in Compose).

1. **Read the inputs.** The Dockerfile (every stage), the `.dockerignore` at the root of
   the build context (a `<Dockerfile name>.dockerignore` next to the Dockerfile takes
   precedence; note if there is neither), every file or directory it `COPY`s or
   `ADD`s (look for secrets, tests, `.git`, local environments), and any entrypoint or
   wrapper script it runs (DW-HEALTH-05 needs the `exec` in it checked by reading).
   Open the copied files, not only their names: a secret sits inside a config file
   whose name gives nothing away. If there are too many to read, say which you did not
   open and list them under Limits. A secret scanner run over them (Trivy's secret
   scanning, for one) counts as reading them for secrets; a search you wrote yourself for
   file names or a few patterns does not, so the files it covered still go under Limits,
   and DW-SECRET-01 is not listed as passing. For a secret you find, report the file,
   the line and what kind of secret it is, never its value: the report is often pasted
   into a pull request or an issue.
   Also read the files that settle rules beyond the Dockerfile when they are in the
   repository, whether or not the user named them: CI workflows (`.github/workflows/`,
   `.gitlab-ci.yml` and the like) and build scripts for the CI pipeline rules listed under
   Limits, and Compose or Kubernetes files for the rules that runtime settings can meet:
   an `init: true` in Compose meets DW-HEALTH-04 as `docker run --init` does, liveness
   and readiness probes are the platform side of DW-HEALTH-02 (still report a missing
   `HEALTHCHECK`, and note the probes with trade-offs §4), and a verify policy is
   DW-SUPPLY-02's verification. A file you can read is a file you were given. Only a workflow, script or manifest that builds,
   scans, publishes or deploys this Dockerfile's image counts; another job's schedule
   or action pins say nothing about it.
2. **Run the linters if they are installed.** Do not install anything without asking.
   - `hadolint --info DL3057 <Dockerfile>` (DL3057, a missing `HEALTHCHECK`, is off by
     default; this turns it on for DW-HEALTH-02)
   - `docker build --check -f <Dockerfile> <context>` (or
     `docker buildx build --call check -f <Dockerfile> <context>`); this runs Docker's
     build checks without building the image.

   Each rule's "How to check" line names the linter codes that belong to it (for example
   DL3002 under DW-USER-01, SecretsUsedInArgOrEnv under DW-SECRET-01). Report every code
   under its matching rule; where a line says a code is reported under another rule
   (DW-BUILD-05 does this for DL3009, DL3019 and DL3042), use that rule. A code
   that no rule names is reported separately, marked "not from the rulebook". DL3057 on a
   build stage's `FROM` is not a DW-HEALTH-02 finding: Hadolint asks every stage for a
   `HEALTHCHECK`, but only the final stage runs as a container. At most, suggest a
   `# hadolint ignore=DL3057` above that `FROM`, as in create mode (step 5). Likewise,
   DL3002 and DL3066 are DW-USER-01 findings only on the `USER` the container runs as:
   the final stage's last `USER`, or, if the final stage sets none, the last `USER`
   along the chain of stages it is built `FROM`. On any other `USER` they are not
   findings, though the rule names them: at most, add a note, suggesting for DL3066 that
   the `USER` be written by number, and for DL3002 a `# hadolint ignore=DL3002` above
   that `USER` with the reason that the stage never runs as a container. DL3025 and
   JSONArgsRecommended on a `CMD` or `ENTRYPOINT` that never reaches the image (step 3)
   are not DW-HEALTH-05 findings either: at most, add a note.

   If a linter is not available, say so and check by reading; then name a code only
   where you can tell it would fire on this file (DL3002 needs an explicit root `USER`,
   such as `USER root` or `USER 0`, not a missing `USER`), and say the codes were not run.
3. **Go rule by rule** through `references/rules.md` in order. For each rule decide:
   finding, passes, does not apply (say why), or cannot be checked from these files
   (it goes under Limits). "Does not apply" means the Dockerfile has nothing the rule is
   about (no `COPY` or `ADD` for DW-BUILD-03, no download for DW-DEPS-03). If you think
   a rule matters less for this image, for example a health check for a one-shot
   command, report the finding and add that note; do not leave it out.
   - **A rule passes only when you checked all of it.** If part of a rule needs evidence
     you did not see, the rule does not pass: DW-SUPPLY-03 also asks what a pinned action
     fetches in turn, and DW-SUPPLY-05 also asks whether removed files are gone from every
     layer, which needs the built image. Say which part you checked and put the rest under
     Limits; such a rule is not also listed as passing. A `manual` rule you checked in
     full by reading does pass, even though Limits (section 5) notes it was checked by
     reading only.
   - **A gap that causes no harm yet is still a finding**, at the rule's strength: a
     `.dockerignore` pattern meant at any depth but written without `**/`
     (`__pycache__/` while `src/` is copied whole) breaks DW-BUILD-03 even if no
     matching file exists today. Say in the Finding column that nothing is affected yet.
     Go through every pattern, not only those for secrets: docs (`*.md`), test and tool
     caches (`.pytest_cache/`, `.coverage`) and build output can sit inside a copied
     directory too, and the diff fixes every such pattern. Before widening one, check that
     the build needs no file it would newly exclude (a `README.md` that a package's
     `pyproject.toml` names, a source package called `build`); keep such a file with a `!`
     line after the pattern, or leave the pattern as it is and say why.
   - **Check image metadata on the image the container runs.** A `LABEL`, `EXPOSE`,
     `HEALTHCHECK`, `STOPSIGNAL`, `ENTRYPOINT` or `CMD` never reaches the image when it sits
     in a stage the final stage is not built `FROM`, directly or through other stages (a
     final stage built `FROM scratch` inherits from none), or when a later instruction in
     the same stage or further along that chain overrides it: a later `HEALTHCHECK`,
     `STOPSIGNAL`, `ENTRYPOINT` or `CMD` replaces the earlier one, and an `ENTRYPOINT` also
     clears the `CMD` its stage inherits. Such an instruction is not a DW-BASE-02 or
     DW-HEALTH finding, and a diff leaves it as it is; at most, add a note.
   - **A rule the build command can meet as well as the Dockerfile** is a finding only
     when neither does. DW-BUILD-09 applies only where reproducible output matters, so
     unless the user has said it does, it goes under Limits. If it does matter,
     `SOURCE_DATE_EPOCH` can come from a global `ARG`, a `--build-arg` or the client's
     environment, and the timestamp rewrite is an exporter option. Check the Dockerfile
     together with the workflow or build script that builds this image; with none, put
     the rule under Limits instead of reporting a missing `ARG`.
   - **Do not assume facts the files do not show.** Whether the image is published
     decides whether DW-SUPPLY-01 and DW-SUPPLY-02 apply. The user saying so settles
     it, and so does a workflow or script you read that pushes this image; otherwise
     ask, or leave both under Limits. Their evidence is never in the Dockerfile: check
     SBOM, provenance and signing against the publishing workflow, and DW-SUPPLY-02's
     verification against the deployment files you read (an admission policy, a
     verify step before deploy); what none of them shows goes under Limits.
4. **Report.** Start with a table, one row per finding, in rule order:

   | Rule | Line | Finding | Severity |
   |------|------|---------|----------|
   | DW-USER-01 | 31 | Final stage runs as root | must fix |

   Severity comes from the rule's strength, not from your own view:
   - `MUST` gives **must fix**;
   - `SHOULD` gives **should fix**;
   - `TRADE-OFF` gives **decide**. State both sides from the matching section of
     `references/tradeoffs.md` (or from the rule's reasons when it has no section) and
     do not count it as a violation. Where the statement names only one part as the
     trade-off, the other parts are not in dispute: DW-DEPS-01 calls only pinning a
     trade-off, so a missing cache cleanup, a separate index update or an unneeded
     package is **should fix**, and only pinning is **decide**. A trade-off the file
     has already settled (it pins package versions, or prunes into `scratch`) is still
     a **decide** row: say which side the file took, give both sides, and offer no diff
     unless the user asks to change it.

   Then, for each finding: the reason (a sentence or two from the rule's "Why"), one
   source link from the rule's "Sources", and a unified diff against the user's file
   as it is now, with file headers and line numbers, so that each diff applies on its
   own. A finding that only a trade-off can fix keeps its severity but gets no diff: for
   DW-BUILD-10 on a distribution base, name the options (a base without a package
   manager, trade-offs §6, or pruning, DW-BUILD-04) and leave the choice to the user.
   Where fixes change the same lines, or lines within three of each other (a hunk
   carries three lines of context, so a nearby change breaks the other diff), give one
   diff and name the rules it covers; the user still chooses by rule (step 5). Where a
   line the diff shows, removed or context, holds a secret value, replace the value with
   `<redacted>` and say so: that diff no longer applies with `git apply`, and the fix is
   made by editing the file (step 5).
   Place comments as in create mode (section 3, step 4). A diff must not call a binary
   the image lacks: if it adds `tini` as the entrypoint, it also installs `tini`. Nor may
   it remove one that something outside the Dockerfile still calls: before a diff drops a
   package or binary (`wget` once a `HEALTHCHECK` uses the language runtime), check the
   Compose healthchecks, Kubernetes exec probes and scripts read in step 1.
   Do not count hunk lines by hand; if you can run commands, let `diff` write the hunk
   from the fixed file, without writing it to disk (`diff` exits 1 when the files
   differ, which is expected here):

   ```sh
   diff -u --label a/<path> --label b/<path> <path> - <<'DW_FIXED_DOCKERFILE'
   <the whole fixed Dockerfile>
   DW_FIXED_DOCKERFILE
   ```

   `<path>` is the Dockerfile's path from the directory the user works in (for example
   `services/api/Dockerfile`), so the headers name that file and `git apply` finds it.
   In the example below the file is `./Dockerfile`. The delimiter must not appear as a
   line in the file: Dockerfile heredocs often end in `EOF`, which would cut the input
   short. Any exit status other than 0 or 1 means the run failed, not that it made a diff.

   ```diff
   --- a/Dockerfile
   +++ b/Dockerfile
   @@ -30,2 +30,3 @@
    COPY --from=build /app /app
   +USER 10001:10001
    CMD ["/app/server"]
   ```

   This example assumes an earlier stage or the base already has user and group 10001;
   if not, the same diff also creates them, as DW-USER-01 asks.

   After the findings, list the rules that pass and the rules that do not apply, by id.
5. **Ask which fixes to apply**, by rule id from the table, also where one diff covers
   several rules. Apply only the ones the user chooses, by editing the file, not by
   applying the diffs one after another: each diff was made against the original, so
   after the first one the others may no longer match. Re-run the linters
   afterwards if they were available, and show what changed, with secret values
   redacted as in step 4.
6. **Close** with two lists. First, the rules the Dockerfile passes now, under the words
   "passes the listed checks". Use those words only for rules that actually pass. Second,
   the rules that do not pass: every must-fix or should-fix finding still open, including
   any the user chose not to apply, and every decision still open. If even one must-fix
   finding is open, do not say the Dockerfile passes; say which checks it fails. Never
   call a Dockerfile secure, safe or compliant; the rulebook does not cover everything
   that would take.

## 3. Create mode

Use this when the user wants a new Dockerfile for a project.

1. **Detect the language and package manager** from the files present:

   | Files | Language, package manager |
   |-------|---------------------------|
   | `pyproject.toml` and `uv.lock` | Python, uv |
   | `package-lock.json` / `pnpm-lock.yaml` | Node.js, npm / pnpm |
   | `go.mod` | Go modules |
   | `pom.xml` / `build.gradle`, `build.gradle.kts` | Java or Kotlin, Maven / Gradle |
   | `Cargo.toml` | Rust, Cargo |
   | `Gemfile.lock` | Ruby, Bundler |
   | `composer.lock` | PHP, Composer |

   Take the language version from the project where it is declared (for example
   `requires-python`, the `go` line in `go.mod`, `engines` in `package.json`). If no row
   matches, or several do, ask.
2. **Ask only what cannot be inferred**, in one message:
   - the entrypoint (the command that starts the application), if the project does not
     declare one;
   - the port it listens on;
   - whether the final image needs a shell (for debugging, or for a wrapper script);
   - whether the image is published to a registry, which decides whether DW-SUPPLY-01
     (SBOM and provenance) and DW-SUPPLY-02 (signing) apply;
   - a base image preference, if the user has one (see Defaults).
3. **Generate `Dockerfile` and `.dockerignore`.** Apply every rule that fits the project.
   Keep the build and runtime stages separate (DW-BUILD-02), dependencies before source
   (DW-BUILD-01), only the paths the image needs (DW-BUILD-03), a numeric non-root user
   (DW-USER-01) that does not own the code (DW-USER-02), and exec-form `ENTRYPOINT` and
   `CMD` (DW-HEALTH-05) behind a minimal init (DW-HEALTH-04), `EXPOSE` for the port
   (DW-HEALTH-01), a `HEALTHCHECK` (DW-HEALTH-02), `STOPSIGNAL` (DW-HEALTH-03) and OCI
   labels (DW-BASE-02). Pass build secrets only as secret mounts (DW-SECRET-01). The
   `.dockerignore` keeps out at least `.git`, environment and key files, local
   dependency and build directories, and tests and docs the build does not need.
   Its patterns match from the root of the context, so a name meant at any depth needs
   `**/` (`**/__pycache__`, not `__pycache__/`). Pruning and flattening (DW-BUILD-04)
   is a TRADE-OFF: offer it, do not apply it unasked.
4. **Comment sparingly.** Put a rule id in a Dockerfile comment only on lines whose
   purpose is not obvious, one id per line, for example
   `# DW-USER-02: code is root-owned, readable through the group`. Where comments go:
   - on their own line above the instruction: a Dockerfile has no end-of-line
     comments, so a `#` after an instruction becomes one of its arguments;
   - a `# syntax=` directive, if you use one, is the first line of the file, since
     anything above it, a comment included, turns it into an ordinary comment;
   - a `# hadolint ignore=...` line goes directly above the instruction it is for,
     with its reason on the line above it; Hadolint applies it to the next line only.
5. **Check your own output.** Run the linters as in audit mode, then go through the
   rules once and fix or report what remains. Hadolint asks every stage for a
   `HEALTHCHECK` (DL3057), but a build stage never runs as a container, so put
   `# hadolint ignore=DL3057` above its `FROM` with that reason. Write every `USER` by
   number, a build-time root as `USER 0`: Hadolint v2.15.1 reports DL3066 on every
   `USER` given by name. A build stage that ends as `USER 0` still gets DL3002, which is
   not a finding there; put `# hadolint ignore=DL3002` above that `USER` with the
   reason that a build stage never runs as a container.
6. **Offer a runtime example.** Offer a hardened Compose service or Kubernetes Pod spec,
   adapted from `references/examples/compose.yaml` or `references/examples/pod.yaml`:
   change the image name, port, user and group IDs and health check notes to fit, and
   keep the hardening settings (read-only root filesystem, all capabilities dropped,
   no privilege escalation, resource limits, a loopback-only published port). Comments
   in those files mention other files of the source repository (`namespace.yaml`,
   `networkpolicy.yaml`, `RUNTIME_SECURITY.md`, smoke-test scripts) that are not in this
   folder; drop them, or point to
   https://github.com/placheckij/dockerfile-wizardry/blob/main/RUNTIME_SECURITY.md.
7. **Summarize** the choices with their rule ids, every decision taken by default (see
   below) with its trade-off section, and every `TODO` left in the file.

## 4. Defaults

These apply in both modes unless the user says otherwise. Each is a choice the user may
reverse, so name it in the summary.

- **Pin base images by digest** (DW-BASE-01): `FROM <image>:<tag>@sha256:<digest>`, with
  the version in an `ARG`. Resolve the digest with
  `docker buildx imagetools inspect <image>:<tag>` and use the top-level `Digest:` it
  prints (the multi-platform index). Run the lookup in audit mode too, before proposing
  a pinned `FROM`. Never invent a digest, version or checksum. If the digest cannot be
  resolved, keep the tag and add a comment `# TODO: pin by digest`, and quote the
  lookup's error rather than guessing its cause; if you did not run the lookup, say so.
  The same goes for tool versions and download checksums (DW-DEPS-02, DW-DEPS-03): use
  a value you have verified, or leave a `TODO`. A digest freezes the base, so mention
  automated updates (Dependabot or Renovate) and periodic rebuilds (DW-SUPPLY-04,
  trade-offs §1).
- **Do not pin apt or apk package versions** (DW-DEPS-01, trade-offs §2). Hadolint will
  report DL3008 (apt) or DL3018 (apk); add `# hadolint ignore=DL3008` (or `DL3018`)
  directly above that `RUN`, with a one-line reason above the ignore line, and say in
  the summary that this was a choice. In audit mode, a version pin the file already has
  is reported as a **decide** item and not removed by a diff unless the user asks.
- **Base image family** (slim, default, distroless, or a vendor's hardened image) is a
  decision to put to the user with trade-offs §6. When the user has no preference, use
  the language's official slim variant (for a compiled binary, a slim distribution image
  for the final stage). The rulebook does not cover hardened-image products; say so if
  one is chosen. An image without a shell needs a `HEALTHCHECK` that runs a binary the
  image has (DW-HEALTH-02) or relies on platform probes (trade-offs §4).

## 5. Limits

End every report or summary with what was not checked:

- **Runtime settings**: `docker run` flags, Compose and Kubernetes settings, beyond the
  few rules step 1 checks against them. The rulebook has no rules for capabilities,
  read-only filesystems, resource limits and the like, even when those files are in the
  repository.
- **Registry and publishing**: SBOM, provenance and signing (DW-SUPPLY-01, DW-SUPPLY-02),
  and signature verification where it is deployed, except what the publishing workflow
  and deployment files you read show (step 3); none of it if the image is not published.
- **CI pipeline rules**: build cache export (DW-BUILD-07), action pinning (DW-SUPPLY-03),
  scheduled rebuilds (DW-SUPPLY-04), image scanning (DW-SUPPLY-05), Docker Engine and
  BuildKit versions (DW-SUPPLY-06), unless a workflow that acts on this image is in the
  repository or the user gave it to you; then check these rules against it. Even then,
  what a pinned action fetches in turn (DW-SUPPLY-03) goes here if you did not check it.
- **Files not opened**: any copied file you did not read (step 1).
- **The built image**: whether removed files are gone from every layer (DW-BUILD-04,
  DW-SUPPLY-05) needs the image, not the Dockerfile.
- **Human judgement**: the `TRADE-OFF` rules (DW-BUILD-04, DW-BUILD-07, DW-DEPS-01), which
  packages the application really needs (DW-DEPS-01), whether reproducible output matters
  (DW-BUILD-09), and every rule whose "How to check" is `manual`, which you checked by
  reading only.

The rules were last verified on the date shown with each rule; the sources may have
changed since.

A worked example that follows the rulebook, with a comment for each choice:
https://github.com/placheckij/dockerfile-wizardry/blob/main/Dockerfile. It uses Alpine
and prunes and flattens into `scratch`, which are trade-off choices, not this skill's
defaults. It also disables the pip and uv caches instead of mounting them: DW-DEPS-02
allows that, but DW-BUILD-05 asks for a cache mount in a build stage, so that file does
not meet DW-BUILD-05.
