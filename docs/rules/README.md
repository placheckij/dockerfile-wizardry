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
  Rules are paraphrased, with any short quotation marked as one, so the source is always the place to confirm the wording.
- **Last verified**: the date someone last read the sources and confirmed the rule still holds.

## Scope

Most rules are about the Dockerfile and the way it is built. A few cover the build pipeline around it (for example pinning GitHub Actions, or keeping BuildKit patched) because the build runs on them.

## Trade-offs

Where sources disagree, or the best choice depends on your situation, a rule is marked `TRADE-OFF` and explains the choice itself. The larger recurring choices have a section on the [trade-offs page](tradeoffs.md); rules of any strength link there when they take one side of such a choice.

## Index

Generated from the theme files by `.github/scripts/check_rules.py --write`; CI fails if it is
out of date. The same command generates the skill's references
([`skills/dockerfile-wizardry/references/`](../../skills/dockerfile-wizardry/references/rules.md)) from these files.

<!-- rules-index:start -->
| Rule | Title | Strength | Spells | Theme |
| --- | --- | --- | --- | --- |
| DW-BASE-01 | Pin the base image by digest | SHOULD | #1 | [base-image](base-image.md) |
| DW-BASE-02 | Label the image with metadata | SHOULD | #2 | [base-image](base-image.md) |
| DW-BUILD-01 | Order layers by how often they change | SHOULD | #6 | [build-and-cache](build-and-cache.md) |
| DW-BUILD-02 | Use multi-stage builds | SHOULD | #7 | [build-and-cache](build-and-cache.md) |
| DW-BUILD-03 | Copy only what the image needs | MUST | #8 | [build-and-cache](build-and-cache.md) |
| DW-BUILD-04 | Prune what the app never runs, then flatten | TRADE-OFF | #10 | [build-and-cache](build-and-cache.md) |
| DW-BUILD-05 | Keep package-manager downloads in a cache mount | SHOULD | - | [build-and-cache](build-and-cache.md) |
| DW-BUILD-06 | Mount a large source tree instead of copying it when it only produces an artifact | SHOULD | - | [build-and-cache](build-and-cache.md) |
| DW-BUILD-07 | Export the build cache in CI, and choose its mode on purpose | TRADE-OFF | - | [build-and-cache](build-and-cache.md) |
| DW-BUILD-08 | Cross-compile for other platforms instead of emulating them | SHOULD | - | [build-and-cache](build-and-cache.md) |
| DW-BUILD-09 | Use SOURCE_DATE_EPOCH when you need reproducible output | SHOULD | - | [build-and-cache](build-and-cache.md) |
| DW-BUILD-10 | Leave out remote-management and package-management tools | SHOULD | - | [build-and-cache](build-and-cache.md) |
| DW-DEPS-01 | Install only the packages you need, in one layer | TRADE-OFF | #3 | [dependencies](dependencies.md) |
| DW-DEPS-02 | Install language tooling pinned, with its cache out of the layer | SHOULD | #5 | [dependencies](dependencies.md) |
| DW-DEPS-03 | Verify what you download during the build | SHOULD | - | [dependencies](dependencies.md) |
| DW-HEALTH-01 | Declare the port the application listens on | SHOULD | #11 | [health-and-signals](health-and-signals.md) |
| DW-HEALTH-02 | Add a health check | SHOULD | #12 | [health-and-signals](health-and-signals.md) |
| DW-HEALTH-03 | Set the stop signal | SHOULD | #13 | [health-and-signals](health-and-signals.md) |
| DW-HEALTH-04 | Run a minimal init as PID 1 | SHOULD | #14 | [health-and-signals](health-and-signals.md) |
| DW-HEALTH-05 | Use exec form, and exec in wrapper scripts, so signals reach the application | SHOULD | - | [health-and-signals](health-and-signals.md) |
| DW-SECRET-01 | Never pass secrets through ARG, ENV or COPY; mount them | MUST | - | [secrets](secrets.md) |
| DW-SUPPLY-01 | Attach an SBOM and provenance to the images you publish | SHOULD | - | [supply-chain](supply-chain.md) |
| DW-SUPPLY-02 | Sign published images and verify them before deploying | SHOULD | - | [supply-chain](supply-chain.md) |
| DW-SUPPLY-03 | Pin GitHub Actions to full commit SHAs | SHOULD | - | [supply-chain](supply-chain.md) |
| DW-SUPPLY-04 | Rebuild and replace instead of patching in place, and do not let cache hide updates | SHOULD | - | [supply-chain](supply-chain.md) |
| DW-SUPPLY-05 | Scan the static image, and check removed files are really gone | SHOULD | - | [supply-chain](supply-chain.md) |
| DW-SUPPLY-06 | Keep Docker Engine and BuildKit patched, and use only trusted frontends | SHOULD | - | [supply-chain](supply-chain.md) |
| DW-USER-01 | Run as a non-root user | MUST | #4 | [users-and-permissions](users-and-permissions.md) |
| DW-USER-02 | The runtime user must not own or be able to change what it runs | SHOULD | #9 | [users-and-permissions](users-and-permissions.md) |
<!-- rules-index:end -->
