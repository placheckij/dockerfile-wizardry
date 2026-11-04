## 🤝 Contributing

Join the wizarding community! We welcome contributions:

- 🐍 **More language examples** (Node.js, Go, Rust, Java, etc.)
- 🔐 **Security improvements** and new spells
- ⚡ **Optimization techniques** and potions
- 📚 **Documentation** enhancements and tutorials
- 🐛 **Bug fixes** and improvements

Please ensure your contributions maintain the "wizardry" theme and include educational comments!

## Checks to run

- After editing anything in `docs/rules/`, run `python3 .github/scripts/check_rules.py --write`.
  It regenerates the rule index, the sources page and the skill's `references/` folder; CI runs
  it with `--check` and fails if they are out of date.
- A new Dockerfile under `fixtures/dockerfiles/<name>/` needs an `expected-findings.txt` next to
  it, listing each rule the Dockerfile breaks and the linter codes that catch it (the format is
  described at the top of `.github/scripts/check_fixtures.py`). Run
  `python3 .github/scripts/check_fixtures.py` (it needs Docker) to confirm the linters report
  exactly those codes.

## Releases

Claude Code gives existing users a new copy of the plugin only when the version in
`.claude-plugin/plugin.json` changes, so changes to `skills/` and `.claude-plugin/` wait on
`main` until a release.

- A pull request that changes `skills/` or `.claude-plugin/` (including the generated
  `references/` folder, so any rulebook change) adds a line under `## [Unreleased]` in
  `CHANGELOG.md`, naming the rule ids it affects. Static Checks fails if the pull request leaves
  that section unchanged.
- To release, test the skill from `main` (for example with `claude --plugin-dir .` in a
  checkout), then run `python3 .github/scripts/release.py prepare patch|minor|major`. It bumps
  `plugin.json` and moves the Unreleased entries into a dated section. `CHANGELOG.md` says which
  part to bump. Commit both files and open a pull request.
- Merging that pull request tags the commit `vX.Y.Z` and publishes a GitHub Release with the
  section as its notes (`.github/workflows/release.yml`).
- Every Monday the same workflow fails, and GitHub emails the failure, while a plugin change has
  waited more than 14 days for a release.
