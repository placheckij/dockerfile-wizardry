# Health and signals

How the image tells the platform it is working, and how it shuts down. The first four rules are
written from Spell #11, #12, #13 and #14; DW-HEALTH-05 comes from its sources alone.

## DW-HEALTH-01: Declare the port the application listens on

strength: SHOULD

spells:
- 11

last_verified: 2026-11-02

statement:
  Add `EXPOSE <port>` for the port the application uses. When running the container, publish the
  port on loopback (`-p 127.0.0.1:8000:8000`) unless it is meant to be reachable from other
  hosts.

why:
  `EXPOSE` does not publish anything; the Dockerfile reference calls it documentation between
  whoever builds the image and whoever runs it about which ports are meant to be published. A bare
  `-p 8000:8000` opens the port on all interfaces, and Docker's own firewall rules bypass host
  firewalls such as UFW (OWASP Rule 5a).

how_to_check:
  manual

sources:
- https://docs.docker.com/reference/dockerfile/#expose
- https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-5a-be-careful-when-mapping-container-ports-to-the-host-with-firewalls-like-ufw

## DW-HEALTH-02: Add a health check

strength: SHOULD

spells:
- 12

last_verified: 2026-11-02

statement:
  Add a `HEALTHCHECK` that exercises the application, using a tool that exists in the image. A
  failed check must exit non-zero.

why:
  CIS 4.5 asks for it: Docker then reports whether the application inside is working (`healthy` or
  `unhealthy`), not only whether the process is still running. Using the language runtime already
  in the image avoids shipping `curl` and its libraries just for the check. Whether to rely on it
  is partly your platform's call, since an orchestrator can use its own probes instead; Hadolint
  ships its missing-`HEALTHCHECK` rule disabled by default. See the
  [trade-offs](tradeoffs.md#4-a-healthcheck-in-the-image-or-probes-in-the-platform).

how_to_check:
  Hadolint DL3057 (missing `HEALTHCHECK`; ignored by default, so enable it); Dockle CIS-DI-0006.

sources:
- https://www.cisecurity.org/benchmark/docker
- https://docs.docker.com/reference/dockerfile/#healthcheck

## DW-HEALTH-03: Set the stop signal

strength: SHOULD

spells:
- 13

last_verified: 2026-11-02

statement:
  Set `STOPSIGNAL` to the signal your application handles for a clean shutdown (`SIGTERM` for
  most servers), and make sure the process actually handles it.

why:
  `docker stop` sends this signal first and kills the process after a timeout. A process that
  ignores it loses in-flight work. The default is `SIGTERM` when the instruction is not set, so
  for most servers `STOPSIGNAL SIGTERM` makes that choice explicit rather than changing it.

how_to_check:
  manual

sources:
- https://docs.docker.com/reference/dockerfile/#stopsignal

## DW-HEALTH-04: Run a minimal init as PID 1

strength: SHOULD

spells:
- 14

last_verified: 2026-11-02

statement:
  Use an init such as `tini` (or `docker run --init`) as the entrypoint, with the application
  started in exec form.

why:
  PID 1 has special signal and child-reaping behaviour. Without an init, orphaned child
  processes can accumulate as zombies and signals may not reach the application, which delays
  or breaks graceful shutdown.

how_to_check:
  manual

sources:
- https://docs.docker.com/reference/cli/docker/container/run/#init
- https://github.com/krallin/tini

## DW-HEALTH-05: Use exec form, and exec in wrapper scripts, so signals reach the application

strength: SHOULD

last_verified: 2026-11-03

statement:
  Write `ENTRYPOINT` and `CMD` in exec (JSON array) form. If the entrypoint is a shell script,
  finish it with `exec <your-app>` so the application replaces the shell as the process that
  receives signals.

why:
  In shell form the executable runs as a child of a shell, which does not pass signals on, so the
  application may never see `SIGTERM` and is killed after the stop timeout instead of shutting
  down cleanly. The same happens when a wrapper script starts the application without `exec`.
  Docker's build check `JSONArgsRecommended` flags the shell form for this reason.

how_to_check:
  Docker build check JSONArgsRecommended (`docker build --check`) and Hadolint DL3025 (JSON
  notation for `CMD` and `ENTRYPOINT`). Neither looks inside a wrapper script, and a `SHELL`
  instruction suppresses the build check's warning, so the `exec` in a script has to be checked by
  reading it.

sources:
- https://hynek.me/articles/docker-signals/
- https://docs.docker.com/reference/build-checks/json-args-recommended/
- https://github.com/hadolint/hadolint
