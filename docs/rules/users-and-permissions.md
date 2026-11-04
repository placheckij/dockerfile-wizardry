# Users and permissions

Who the container runs as, and what that user may change. Written from
Spell #4 and Spell #9.

## DW-USER-01: Run as a non-root user

strength: MUST

spells:
- 4

last_verified: 2026-11-04

statement:
  Create a dedicated user and group with explicit numeric IDs and switch to it by number,
  `USER <uid>:<gid>`, before the final `CMD`/`ENTRYPOINT`. Never leave the container running
  as root.

why:
  Code execution inside the container then starts with the privileges of an unprivileged user,
  not root, which limits what a compromise can reach (CIS 4.1, OWASP Rule 2). The uid must be
  numeric because a name is mapped to an id only inside the container, from the image's
  `/etc/passwd`; a check that reads only the image config sees the name and cannot tell which
  id it is. With `runAsNonRoot: true` and no `runAsUser`, the Kubernetes kubelet therefore
  refuses to start a container whose image names its user ("image has non-numeric user (…),
  cannot verify user is non-root"). Give the gid as well: a user without a primary group runs
  with the root group. Naming a group also drops the user's other group memberships, so the
  runtime user gets what it needs through that one group.

how_to_check:
  Hadolint DL3002 (last user should not be root), DL3066 (non-numeric user id, which the host
  may not resolve); Dockle CIS-DI-0001 (a user has been created). The Hadolint codes are
  findings only on the user the container runs as, the last `USER` of the final stage.
  Hadolint also reports DL3002 on a build stage that ends as root and DL3066 on any `USER`
  given by name; there they are not findings under this rule. A `USER` that only applies
  during the build can be written `USER 0`, which DL3066 accepts.

sources:
- https://www.cisecurity.org/benchmark/docker
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user
- https://github.com/hadolint/hadolint
- https://docs.docker.com/reference/dockerfile/#user
- https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/
- https://github.com/kubernetes/kubernetes/blob/v1.37.2/pkg/kubelet/kuberuntime/security_context_others.go#L50

## DW-USER-02: The runtime user must not own or be able to change what it runs

strength: SHOULD

spells:
- 9

last_verified: 2026-11-02

statement:
  Make application code and dependencies owned by `root`, readable (and executable where needed)
  by the runtime user through a group, and not writable by anyone at runtime. Do the same for
  the application directory itself.

why:
  An owner can always `chmod` its own files back to writable, and a writable directory lets
  entries be renamed or replaced, so a compromised process could tamper with its own code. OWASP
  Rule 8 asks for a read-only filesystem at runtime; making the files root-owned is this
  repository's build-time complement, which keeps the protection even when the runtime flag is
  missing. The runtime flag remains the primary control.

how_to_check:
  manual. This repository's CI runs a check that the application user cannot write, `chmod` or
  replace anything under the application directory.

sources:
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only
