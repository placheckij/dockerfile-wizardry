#!/usr/bin/env bash
# Smoke test for examples/compose.yaml.
#
# Starts the example exactly as written, waits for the image's own HEALTHCHECK to
# report "healthy", calls the endpoints, and checks that the hardening settings were
# really applied: with `docker inspect` (what Docker was asked to do) and from inside
# the container (what the kernel actually enforces).
#
# SAFETY: the Compose project gets a unique name, so this script can never recreate or
# tear down a project of yours that it did not start. The example publishes the fixed host
# port 8000, so the script refuses to run if something already listens there.
#
# Needs the image to exist locally:  docker build -t wizardry:1.0.0 .
# Usage: .github/scripts/smoke_compose.sh

# The single-quoted `docker inspect --format` strings are Go templates ($p, $bs, $n are template
# variables, not shell variables), and the in-container script must not expand locally either.
# shellcheck disable=SC2016
set -euo pipefail

cd "$(dirname "$0")/../.."

IMAGE=wizardry:1.0.0
PROJECT="wizardry-smoke-$$"
COMPOSE=(docker compose -p "$PROJECT" -f examples/compose.yaml)
URL=http://127.0.0.1:8000

fail() { echo "❌ $*" >&2; exit 1; }

docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || fail "image $IMAGE not found - build it first: docker build -t $IMAGE ."

if (exec 3<>/dev/tcp/127.0.0.1/8000) 2>/dev/null; then
  fail "something is already listening on 127.0.0.1:8000 (the example's fixed host port); stop it and retry"
fi

cleanup() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "--- container logs (last 30 lines) ---" >&2
    "${COMPOSE[@]}" logs --no-color --tail 30 >&2 2>/dev/null || true
  fi
  "${COMPOSE[@]}" down --volumes >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${COMPOSE[@]}" up -d --wait --wait-timeout 90
CID=$("${COMPOSE[@]}" ps -q wizardry)
[ -n "$CID" ] || fail "no container for service 'wizardry'"

inspect() { docker inspect --format "$1" "$CID"; }
expect() { # expect <what> <actual> <wanted>
  [ "$2" = "$3" ] || fail "$1: expected '$3', got '$2'"
  echo "✅ $1 = $3"
}

echo "== settings Docker was asked to apply (docker inspect)"
expect "health status"                  "$(inspect '{{.State.Health.Status}}')"                    healthy
expect "read-only root filesystem"      "$(inspect '{{.HostConfig.ReadonlyRootfs}}')"             true
expect "capabilities dropped"           "$(inspect '{{.HostConfig.CapDrop}}')"                     "[ALL]"
expect "capabilities added"             "$(inspect '{{len .HostConfig.CapAdd}}')"                  0
expect "no-new-privileges"              "$(inspect '{{.HostConfig.SecurityOpt}}')"                 "[no-new-privileges:true]"
expect "memory limit (bytes)"           "$(inspect '{{.HostConfig.Memory}}')"                      536870912
expect "cpu limit (nano cpus)"          "$(inspect '{{.HostConfig.NanoCpus}}')"                    1000000000
expect "restart policy"                 "$(inspect '{{.HostConfig.RestartPolicy.Name}}:{{.HostConfig.RestartPolicy.MaximumRetryCount}}')" on-failure:5
expect "open-files ulimit"              "$(inspect '{{range .HostConfig.Ulimits}}{{.Name}}={{.Soft}}:{{.Hard}};{{end}}')" "nofile=1024:1024;"
expect "tmpfs"                          "$(inspect '{{.HostConfig.Tmpfs}}')"                       "map[/tmp:rw,noexec,nosuid,size=100m]"
expect "runs as the unprivileged user"  "$(inspect '{{.Config.User}}')"                            wizard
# Every published binding must be loopback-only - checking just the first would miss an extra 0.0.0.0 one
expect "published ports (all bindings)" "$(inspect '{{range $p, $bs := .NetworkSettings.Ports}}{{range $bs}}{{$p}}={{.HostIp}}:{{.HostPort}};{{end}}{{end}}')" "8000/tcp=127.0.0.1:8000;"
# On the project's own user-defined network, not the default bridge
expect "networks"                       "$(inspect '{{range $n, $_ := .NetworkSettings.Networks}}{{$n}};{{end}}')" "${PROJECT}_default;"

echo "== endpoints"
for pair in "health:healthy" "spell/fireball:Blazing" "potion/healing:phoenix_tear"; do
  path=${pair%%:*}; needle=${pair#*:}
  body=$(curl -fsS --retry 10 --retry-delay 1 --retry-all-errors "$URL/$path") \
    || fail "GET /$path failed"
  case "$body" in *"$needle"*) echo "✅ GET /$path contains '$needle'" ;; *) fail "GET /$path: '$needle' not in: $body" ;; esac
done

echo "== what the kernel enforces inside the container"
# This script runs INSIDE the container, so its $(...) must not expand here (hence single quotes).
docker exec "$CID" sh -c '
  fail=0
  grep -Eq "^[^ ]+ / [^ ]+ ro[, ]" /proc/mounts || { echo "root filesystem is not mounted read-only"; fail=1; }
  line=$(grep -E "^[^ ]+ /tmp " /proc/mounts || true)
  case "$line" in "tmpfs /tmp tmpfs "*) ;; *) echo "/tmp is not a tmpfs: $line"; fail=1 ;; esac
  for opt in nosuid noexec size=102400k; do
    case "$line" in *"$opt"*) ;; *) echo "/tmp mount lacks $opt: $line"; fail=1 ;; esac
  done
  ( echo x > /tmp/ok ) 2>/dev/null || { echo "/tmp is not writable"; fail=1; }
  ( echo x > /spellbook/injected ) 2>/dev/null && { echo "/spellbook is writable"; fail=1; }
  chmod u+w /spellbook/main.py 2>/dev/null && { echo "chmod u+w main.py succeeded"; fail=1; }
  [ "$(ulimit -n)" = 1024 ] || { echo "ulimit -n is $(ulimit -n), expected 1024"; fail=1; }
  exit $fail' || fail "checks inside the container failed"
echo "✅ root filesystem read-only; /tmp is a tmpfs with nosuid, noexec and the size limit; application files read-only; ulimit -n = 1024"

echo "All Compose smoke checks passed."
