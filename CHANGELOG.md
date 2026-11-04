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

- DW-USER-01 now requires the runtime user as numbers, `USER <uid>:<gid>`: a name is resolved only inside the container, and Kubernetes' `runAsNonRoot` refuses to start an image that names its user. Dockerfiles that switch to a non-root user by name, or give no numeric group, now fail it. (#17)

## [0.1.0] - 2026-11-04

### Added

- The `dockerfile-wizardry` skill, with an audit mode and a create mode, reading a `references/` copy of the rulebook generated from `docs/rules/`. (#15)
- Plugin and marketplace manifests, so the skill installs with `/plugin marketplace add placheckij/dockerfile-wizardry`. (#15)

This version was not tagged.
