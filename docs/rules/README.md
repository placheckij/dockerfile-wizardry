# Dockerfile rules

Each rule here states one practice for building a Docker image, why it matters, how to check it,
and where it comes from. The main [README](../../README.md) walks through the same practices as
numbered "spells" in a worked example; the `Spells` column below maps one to the other.

## What a rule contains

- **Strength**
  - `MUST`: the source states it as a requirement, or skipping it leaves a clear security gap.
  - `SHOULD`: recommended, with reasons you may weigh against your situation.
  - `TRADE-OFF`: sources disagree, or the right choice depends on your case. Both sides are
    given, and the rule does not pick one for you.
- **Statement** and **why**: what to do, and the reason.
- **How to check**: a linter rule id, a command, or `manual` when no tool covers it.
- **Sources**: links to the primary documents (a benchmark, a vendor's own docs, a standard).
  Rules are paraphrased, never copied, so the source is always the place to confirm the wording.
- **Last verified**: the date someone last read the sources and confirmed the rule still holds.

## Index

Generated from the theme files by `.github/scripts/check_rules.py --write`; CI fails if it is
out of date.

<!-- rules-index:start -->
<!-- rules-index:end -->
