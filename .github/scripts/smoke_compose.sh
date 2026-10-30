#!/usr/bin/env bash
# Smoke test for examples/compose.yaml.
#
# Starts the example exactly as written, waits for the image's own HEALTHCHECK to
# report "healthy", calls the endpoints, and checks with `docker inspect` that the
# hardening settings were really applied (not just written in the file).
#
# Needs the image to exist locally:  docker build -t wizardry:1.0.0 .
# Usage: .github/scripts/smoke_compose.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

IMAGE=wizardry:1.0.0
PROJECT=wizardry-smoke
COMPOSE=(docker compose -p "$PROJECT" -f examples/compose.yaml)
URL=http://127.0.0.1:8000

fail() { echo "❌ $*" >&2; exit 1; }

docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || fail "image $IMAGE not found - build it first: docker build -t $IMAGE ."

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

echo "== settings Docker actually applied"
expect "health status"              "$(inspect '{{.State.Health.Status}}')"                     healthy
expect "read-only root filesystem"  "$(inspect '{{.HostConfig.ReadonlyRootfs}}')"              true
expect "capabilities dropped"       "$(inspect '{{.HostConfig.CapDrop}}')"                      "[ALL]"
expect "capabilities added"         "$(inspect '{{len .HostConfig.CapAdd}}')"                   0
expect "no-new-privileges"          "$(inspect '{{.HostConfig.SecurityOpt}}')"                  "[no-new-privileges:true]"
expect "memory limit (bytes)"       "$(inspect '{{.HostConfig.Memory}}')"                       536870912
expect "cpu limit (nano cpus)"      "$(inspect '{{.HostConfig.NanoCpus}}')"                     1000000000
expect "restart policy"             "$(inspect '{{.HostConfig.RestartPolicy.Name}}:{{.HostConfig.RestartPolicy.MaximumRetryCount}}')" on-failure:5
expect "published on loopback only" "$(inspect '{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostIp}}')" 127.0.0.1
expect "runs as the unprivileged user" "$(inspect '{{.Config.User}}')"                          wizard

echo "== endpoints"
for pair in "health:healthy" "spell/fireball:Blazing" "potion/healing:phoenix_tear" ""; do
  [ -n "$pair" ] || continue
  path=${pair%%:*}; needle=${pair#*:}
  body=$(curl -fsS --retry 10 --retry-delay 1 --retry-all-errors "$URL/$path") \
    || fail "GET /$path failed"
  case "$body" in *"$needle"*) echo "✅ GET /$path contains '$needle'" ;; *) fail "GET /$path: '$needle' not in: $body" ;; esac
done

echo "== inside the container"
docker exec "$CID" sh -c '
  fail=0
  ( echo x > /spellbook/injected ) 2>/dev/null && { echo "writable: /spellbook"; fail=1; }
  ( echo x > /usr/local/bin/injected ) 2>/dev/null && { echo "writable: /usr/local/bin"; fail=1; }
  ( echo x > /tmp/ok ) 2>/dev/null || { echo "/tmp is not writable"; fail=1; }
  chmod u+w /spellbook/main.py 2>/dev/null && { echo "chmod u+w main.py succeeded"; fail=1; }
  exit $fail' || fail "filesystem checks inside the container failed"
echo "✅ root filesystem and application files are read-only; /tmp (tmpfs) is writable"

echo "All Compose smoke checks passed."
