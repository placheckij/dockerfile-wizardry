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
