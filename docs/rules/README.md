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
| Rule | Title | Strength | Spells | Theme |
| --- | --- | --- | --- | --- |
| DW-BASE-01 | Pin the base image by digest | SHOULD | #1 | [base-image](base-image.md) |
| DW-BASE-02 | Label the image with metadata | SHOULD | #2 | [base-image](base-image.md) |
| DW-BUILD-01 | Order layers by how often they change | SHOULD | #6 | [build-and-cache](build-and-cache.md) |
| DW-BUILD-02 | Use multi-stage builds | SHOULD | #7 | [build-and-cache](build-and-cache.md) |
| DW-BUILD-03 | Copy only what the image needs | MUST | #8 | [build-and-cache](build-and-cache.md) |
| DW-BUILD-04 | Prune what the app never runs, then flatten | TRADE-OFF | #10 | [build-and-cache](build-and-cache.md) |
| DW-DEPS-01 | Install only the packages you need, in one layer | TRADE-OFF | #3 | [dependencies](dependencies.md) |
| DW-DEPS-02 | Install language tooling pinned, without caches | SHOULD | #5 | [dependencies](dependencies.md) |
| DW-HEALTH-01 | Declare the port the application listens on | SHOULD | #11 | [health-and-signals](health-and-signals.md) |
| DW-HEALTH-02 | Add a health check | MUST | #12 | [health-and-signals](health-and-signals.md) |
| DW-HEALTH-03 | Set the stop signal | SHOULD | #13 | [health-and-signals](health-and-signals.md) |
| DW-HEALTH-04 | Run a minimal init as PID 1 | SHOULD | #14 | [health-and-signals](health-and-signals.md) |
| DW-USER-01 | Run as a non-root user | MUST | #4 | [users-and-permissions](users-and-permissions.md) |
| DW-USER-02 | The runtime user must not own or be able to change what it runs | MUST | #9 | [users-and-permissions](users-and-permissions.md) |
<!-- rules-index:end -->
