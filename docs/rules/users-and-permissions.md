# Users and permissions

Who the container runs as, and what that user may change. Written from
[Spell #4](../../README.md) and [Spell #9](../../README.md).

## DW-USER-01: Run as a non-root user
strength: MUST
spells:
- 4
last_verified: 2026-11-02
statement: |
  Create a dedicated user and group with explicit numeric IDs and switch to it with `USER`
  before the final `CMD`/`ENTRYPOINT`. Never leave the container running as root.
why: |
  Code execution inside the container then starts with the privileges of an unprivileged user,
  not root, which limits what a compromise can reach (CIS 4.1, OWASP Rule 2).
how_to_check: |
  Hadolint DL3002 (last user should not be root) and DL3066 (non-numeric user ID); Dockle
  CIS-DI-0001 (a user has been created).
sources:
- https://www.cisecurity.org/benchmark/docker
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user

## DW-USER-02: The runtime user must not own or be able to change what it runs
strength: MUST
spells:
- 9
last_verified: 2026-11-02
statement: |
  Make application code and dependencies owned by `root`, readable (and executable where needed)
  by the runtime user through a group, and not writable by anyone at runtime. Do the same for
  the application directory itself.
why: |
  An owner can always `chmod` its own files back to writable, and a writable directory lets
  entries be renamed or replaced, so a compromised process could tamper with its own code. This
  is the build-time side of OWASP Rule 8; the `--read-only` runtime flag is the other side and
  remains the primary control. This setting holds even when the runtime flag is missing.
how_to_check: |
  manual. This repository's CI runs a check that the application user cannot write, `chmod` or
  replace anything under the application directory.
sources:
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only
