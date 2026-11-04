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

- Audit mode reads the contents of every copied file, not only the names, and reads CI workflows and Compose or Kubernetes files found in the repository instead of leaving DW-BUILD-07 and DW-SUPPLY-03 to DW-SUPPLY-06 under Limits when the user did not hand them over.
- Audit mode reports a gap that affects no file yet (DW-BUILD-03) at the rule's strength, reports DW-BUILD-09 only when reproducible output matters and neither the Dockerfile nor a build workflow it read sets `SOURCE_DATE_EPOCH`, asks rather than assumes whether the image is published and checks DW-SUPPLY-01 and DW-SUPPLY-02 only against a publishing workflow, and reports a trade-off the file has already settled (DW-BUILD-04, DW-DEPS-01) as a **decide** row without a diff.
- Audit mode merges fixes whose lines fall within three of each other into one diff, and applies chosen fixes by editing the file instead of applying the diffs in sequence.
- DW-BUILD-05 says which pip cache-mount targets keep Hadolint's DL3042 quiet: any target ending in `.cache/pip`, not the parent `.cache`.

## [0.1.0] - 2026-11-04

### Added

- The `dockerfile-wizardry` skill, with an audit mode and a create mode, reading a `references/` copy of the rulebook generated from `docs/rules/`. (#15)
- Plugin and marketplace manifests, so the skill installs with `/plugin marketplace add placheckij/dockerfile-wizardry`. (#15)
- An argument hint, so `/dockerfile-wizardry:dockerfile-wizardry` offers `[audit|create] [path]` as you type. (#21)

### Changed

- DW-USER-01 now requires the runtime user as numbers, `USER <uid>:<gid>`: a name is resolved only inside the container, and Kubernetes' `runAsNonRoot` refuses to start an image that names its user. Dockerfiles that switch to a non-root user by name, or give no numeric group, now fail it. (#17)
