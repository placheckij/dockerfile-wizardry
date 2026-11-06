# Changelog

Changes to the Claude Code plugin: the [`dockerfile-wizardry` skill](skills/dockerfile-wizardry/SKILL.md) and the rulebook it reads. Changes to the example image, CI and the rest of the repository are not listed.

Claude Code gives existing users a new copy of the plugin only when the version in [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) changes, so each version below is a release. Versions follow [Semantic Versioning](https://semver.org/), read in terms of the rules:

- **Major**: a rule id is removed or renumbered, a rule's strength goes up (`SHOULD` to `MUST`), or a rule now fails Dockerfiles it used to pass. Re-run your audits.
- **Minor**: a new rule, source or trade-off section, or a new skill behaviour.
- **Patch**: rewording, link fixes and re-verified dates that leave every rule's meaning as it was.

Before 1.0.0, a major change bumps the minor version instead and anything else bumps the patch version. 1.0.0 will mean the rule ids are stable.

Each pull request that changes `skills/` or `.claude-plugin/` adds a line under Unreleased, naming the rule ids it affects; see [CONTRIBUTING.md](CONTRIBUTING.md#releases) for how a release is made.

## [Unreleased]

## [0.2.0] - 2026-11-06

### Added

- DW-BASE-03 (SHOULD): build on a base tag its publisher still rebuilds. A tag for a release that is no longer supported, such as an old patch version, stays pullable but is never rebuilt, so `--pull`, a digest pin and digest-versus-tag checks such as Docker Scout's `No outdated base images` policy all miss that it is stale. Before resolving a digest (DW-BASE-01), also for a `FROM` already pinned by digest, both modes compare a tag below its release line, the version series the publisher keeps patching (the minor version for Python and Alpine, the major version for Node), with the same tag cut down to that line, any variant kept (`3.12-slim-bookworm` for `3.12.4-slim-bookworm`, `24-slim` for `node:24.11-slim`), and propose the release-line tag when they differ, naming the OS release the image was built on when the tag left it implicit (`3.12-slim-bookworm` for `3.12.4-slim`), or putting the move to the user when that cannot be told or only a newer OS release is supported; a broader tag moving to a newer release line is not a finding. They compare the two tags' current digests, not the digest pinned in the file: a pin that has only fallen behind its own tag is a digest left un-updated (DW-SUPPLY-04), not DW-BASE-03. They also read the base image's build date with `docker buildx imagetools inspect`: a date months old leads to checking in the publisher's supported tags whether the release line or the variant's OS release (`-slim-bullseye`) was dropped, a fixed date from a reproducible build (1970-01-01) is ignored, and moving to a supported variant or a newer release line is put to the user as a decision. If the lookups cannot run, the report says DW-BASE-03 was not checked. DW-BASE-01 now says that digest updates and a CI job comparing the pin with its tag miss a tag that is no longer rebuilt, while an update that also moves the tag to a newer version catches it, and points to the new rule.

### Changed

- Audit mode reports a finding that only a trade-off can fix, such as DW-BUILD-10 on the package manager a distribution base ships, at its severity without a diff, naming the options, and asks which fixes to apply by rule id, also where one diff covers several rules.
- Audit mode offers, when Docker is available and without requiring it, to build the image before and after the chosen fixes and compare the user it runs as and its PID 1 (DW-USER-01, DW-HEALTH-04, DW-HEALTH-05), who owns the application code, its dependencies and their directories (DW-USER-02), counted by owner and mode, and the image size, so a cost a diff does not show, such as install-time bytecode (DW-DEPS-02), reaches the report. It builds with the flags of the build that makes the image, for one platform, under two new tags, redacts secret values in what it shows, and removes only the images and containers it created.
- Audit mode gives findings judged against a CI workflow or build script their diffs against that file, and for DW-SUPPLY-03 resolves the commit an action's tag or branch points to with `git ls-remote`, taking the peeled commit of an annotated tag, keeping a `# <version>` comment for Dependabot and Renovate, pinning `docker://` steps by digest, leaving a `TODO` instead of a guessed SHA, and saying that the pinned commits were not reviewed.
- Audit mode checks the Compose healthchecks, Kubernetes exec probes and scripts it read before a diff removes a package or binary they call.
- Audit mode does not count a scan of the copied files, by a secret scanner or a search it wrote itself, as reading them: it reports what the scan found, keeps the files it did not open under Limits and lists neither DW-SECRET-01 nor DW-BUILD-03 as passing.
- DW-DEPS-02 asks for install-time bytecode also when the installed dependencies are root-owned (DW-USER-02), not only on a read-only root filesystem, and says the size cost grows with the dependencies and should be measured instead of quoting 8 MB as typical. DW-USER-02 points back to it.
- DW-BUILD-07 notes that a persistent self-hosted runner keeps its local cache without an export, and that a no-cache rebuild then has to get past that cache (DW-SUPPLY-04).
- `# hadolint ignore=...` lines are written only when Hadolint runs on that Dockerfile: a Hadolint config, a CI workflow, build script, Makefile, git hook or linter suite with Hadolint on that runs it, an ignore or global ignore line the Dockerfile already has, or the user's word; the skill's own linter run does not count. They are written only for codes that run would report, so DL3057, off by default, gets one only when the repository turns it on (in its config, with a flag such as `--info DL3057`, or with an existing ignore line). Elsewhere the code and its reason go in the summary or report, and existing ignore lines are left as they are. This covers DL3008 and DL3018 for unpinned packages (DW-DEPS-01) in both modes, DL3057 and DL3002 on build stages (DW-HEALTH-02, DW-USER-01) in create mode, and audit mode's suggestion of those two in a note. They used to be added or suggested whether or not Hadolint ran.

### Fixed

- The audit-mode `awk` example that counts file owners and modes when comparing the before and after images (DW-USER-02) writes its fields as `$(1)`, not `$1`: Claude Code replaced `$1` in SKILL.md with the skill's arguments when the skill was invoked with arguments, so the loaded example printed the Dockerfile path instead of the mode column.

## [0.1.2] - 2026-11-04

### Changed

- Audit mode lists a rule as passing only when every part of it was checked, and puts the unchecked part under Limits instead: what a pinned action fetches in turn for DW-SUPPLY-03, and whether removed files are gone from every layer for DW-SUPPLY-05. A `manual` rule checked in full by reading still passes.
- Audit mode checks every `.dockerignore` pattern for a missing `**/` (DW-BUILD-03), including docs, test caches and build output, not only patterns for secrets, and keeps any file the build needs at that depth with a `!` line, or leaves the pattern as it is and says why.
- Audit mode does not report or rewrite a `LABEL`, `EXPOSE`, `HEALTHCHECK`, `STOPSIGNAL`, `ENTRYPOINT` or `CMD` that never reaches the image, because it sits in a stage the final stage is not built from or a later instruction overrides it (DW-BASE-02, DW-HEALTH-01 to DW-HEALTH-05). It no longer rewrites labels in a stage a `FROM scratch` final stage never inherits, or reports DL3025 or JSONArgsRecommended on such a `CMD` or `ENTRYPOINT`.
- Audit mode takes the final stage to be the one the image is built from: the last stage, unless the workflow, build script or Compose file that builds the image names a `--target` (DW-BASE-02, DW-HEALTH-01 to DW-HEALTH-05, DW-USER-01).

## [0.1.1] - 2026-11-04

### Changed

- Audit mode reads the contents of every copied file, not only the names, and reports a secret it finds by file, line and kind, never by value, redacting it in any diff or change summary that shows the line. It reads the CI workflows that build, scan, publish or deploy the image instead of leaving DW-BUILD-07 and DW-SUPPLY-03 to DW-SUPPLY-06 under Limits when the user did not hand them over, and reads Compose and Kubernetes files for the rules they can meet: `init: true` meets DW-HEALTH-04, and probes are noted against DW-HEALTH-02.
- Audit mode reports a gap that affects no file yet (DW-BUILD-03) at the rule's strength, checks DW-BUILD-09 only when reproducible output matters, against the Dockerfile together with the workflow that builds the image, asks rather than assumes whether the image is published and checks DW-SUPPLY-01 and DW-SUPPLY-02 against the publishing workflow and deployment files instead of the Dockerfile, and reports a trade-off the file has already settled (DW-BUILD-04, DW-DEPS-01) as a **decide** row without a diff.
- Audit mode merges fixes whose lines fall within three of each other into one diff, and applies chosen fixes by editing the file instead of applying the diffs in sequence.
- DW-BUILD-05 says which pip cache-mount targets keep Hadolint's DL3042 quiet: a cache or tmpfs mount whose target contains `.cache/pip`, not the parent `.cache`.

## [0.1.0] - 2026-11-04

### Added

- The `dockerfile-wizardry` skill, with an audit mode and a create mode, reading a `references/` copy of the rulebook generated from `docs/rules/`. (#15)
- Plugin and marketplace manifests, so the skill installs with `/plugin marketplace add placheckij/dockerfile-wizardry`. (#15)
- An argument hint, so `/dockerfile-wizardry:dockerfile-wizardry` offers `[audit|create] [path]` as you type. (#21)

### Changed

- DW-USER-01 now requires the runtime user as numbers, `USER <uid>:<gid>`: a name is resolved only inside the container, and Kubernetes' `runAsNonRoot` refuses to start an image that names its user. Dockerfiles that switch to a non-root user by name, or give no numeric group, now fail it. (#17)
