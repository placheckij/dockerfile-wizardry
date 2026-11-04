# Changelog

Changes to the Claude Code plugin: the [`dockerfile-wizardry` skill](skills/dockerfile-wizardry/SKILL.md) and the rulebook it reads. Changes to the example image, CI and the rest of the repository are not listed.

Claude Code gives existing users a new copy of the plugin only when the version in [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) changes, so each version below is a release. Versions follow [Semantic Versioning](https://semver.org/), read in terms of the rules:

- **Major**: a rule id is removed or renumbered, a rule's strength goes up (`SHOULD` to `MUST`), or a rule now fails Dockerfiles it used to pass. Re-run your audits.
- **Minor**: a new rule, source or trade-off section, or a new skill behaviour.
- **Patch**: rewording, link fixes and re-verified dates that leave every rule's meaning as it was.

Before 1.0.0, a major change bumps the minor version instead and anything else bumps the patch version. 1.0.0 will mean the rule ids are stable.

Each pull request that changes `skills/` or `.claude-plugin/` adds a line under Unreleased, naming the rule ids it affects; see [CONTRIBUTING.md](CONTRIBUTING.md#releases) for how a release is made.

## [Unreleased]

### Changed

- Audit mode lists a rule as passing only when every part of it was checked, and puts the unchecked part under Limits instead: what a pinned action fetches in turn for DW-SUPPLY-03, and whether removed files are gone from every layer for DW-SUPPLY-05.
- Audit mode checks every `.dockerignore` pattern for a missing `**/` (DW-BUILD-03), including docs, test caches and build output, not only patterns for secrets, and keeps any file the build needs at that depth with a `!` line.
- Audit mode checks `LABEL`, `EXPOSE`, `HEALTHCHECK`, `STOPSIGNAL`, `ENTRYPOINT` and `CMD` only in the final stage and the stages it is built from (DW-BASE-02, DW-HEALTH-01 to DW-HEALTH-05), so it no longer rewrites labels in a stage a `FROM scratch` final stage never inherits, and does not report DL3025 or JSONArgsRecommended on another stage's `CMD` or `ENTRYPOINT`.

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
