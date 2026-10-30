#!/usr/bin/env bash
# Smoke test for examples/namespace.yaml + examples/pod.yaml on a throwaway kind cluster.
#
# Creates a cluster, loads the image, applies the examples (the namespace enforces the
# Pod Security "restricted" standard), then checks what Kubernetes ACTUALLY enforced
# inside the container - not just what the manifest says - and the documented outcomes
# for random user IDs (see "Which user and group the container needs" in RUNTIME_SECURITY.md).
#
# SAFETY: everything runs against its own temporary kubeconfig file, never ~/.kube/config,
# and the script refuses to continue unless the current context is the throwaway kind
# cluster it just created. Your own kubectl contexts are never read or changed.
#
# Needs: docker, kind, kubectl, python3, curl, and the image:  docker build -t wizardry:1.0.0 .
# Optional: KIND_NODE_IMAGE (e.g. kindest/node:v1.37.0@sha256:...) to pin the node image.
# Usage: .github/scripts/smoke_kubernetes.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

IMAGE=wizardry:1.0.0
CLUSTER=${KIND_CLUSTER_NAME:-wizardry-smoke}
NS=wizardry
LOCAL_PORT=18000

KUBECONFIG_FILE=$(mktemp "${TMPDIR:-/tmp}/wizardry-kubeconfig.XXXXXX")
export KUBECONFIG="$KUBECONFIG_FILE"   # kind and kubectl below use ONLY this file

fail() { echo "❌ $*" >&2; exit 1; }

for tool in docker kind kubectl python3 curl; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is required but not installed"
done
docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || fail "image $IMAGE not found - build it first: docker build -t $IMAGE ."

PF_PID=""
cleanup() {
  local rc=$?
  if [ -n "$PF_PID" ]; then kill "$PF_PID" 2>/dev/null || true; fi
  if [ "$rc" -ne 0 ]; then
    echo "--- diagnostics ---" >&2
    kubectl get pods -n "$NS" -o wide >&2 2>/dev/null || true
    kubectl describe pods -n "$NS" 2>/dev/null | tail -n 40 >&2 || true
    kubectl logs -n "$NS" wizardry --tail 20 >&2 2>/dev/null || true
  fi
  kind delete cluster --name "$CLUSTER" --kubeconfig "$KUBECONFIG_FILE" >/dev/null 2>&1 || true
  rm -f "$KUBECONFIG_FILE"
}
trap cleanup EXIT

step() { echo; echo "== $*"; }
ok() { echo "✅ $*"; }

# A pod's field via jsonpath
pod_field() { kubectl get pod "$1" -n "$NS" -o jsonpath="$2"; }

# Wait up to $2 seconds for pod $1 to be Ready
wait_ready() { kubectl wait pod/"$1" -n "$NS" --for=condition=Ready --timeout="${2}s" >/dev/null; }

# examples/pod.yaml with a different name / random uid-gid, optionally without fsGroup
make_variant() { # make_variant <name> <drop_fsgroup 0|1>
  python3 -c '
import sys
name, drop = sys.argv[1], sys.argv[2] == "1"
s = open("examples/pod.yaml").read()
head = "metadata:\n  name: wizardry\n"
assert s.count(head) == 1 and s.count("runAsUser: 1337") >= 1 and s.count("runAsGroup: 1337") >= 1
s = s.replace(head, "metadata:\n  name: " + name + "\n", 1)
s = s.replace("runAsUser: 1337", "runAsUser: 10001").replace("runAsGroup: 1337", "runAsGroup: 10001")
if drop:
    assert "    fsGroup: 1337\n" in s
    s = s.replace("    fsGroup: 1337\n", "")
print(s)' "$1" "$2"
}

step "Creating a throwaway kind cluster ($CLUSTER) with its own kubeconfig"
kind delete cluster --name "$CLUSTER" --kubeconfig "$KUBECONFIG_FILE" >/dev/null 2>&1 || true
kind create cluster --name "$CLUSTER" --kubeconfig "$KUBECONFIG_FILE" --wait 180s \
  ${KIND_NODE_IMAGE:+--image "$KIND_NODE_IMAGE"}
[ "$(kubectl config current-context)" = "kind-$CLUSTER" ] \
  || fail "current kubectl context is not kind-$CLUSTER - refusing to continue"
ok "kubectl is pointed at kind-$CLUSTER (temporary kubeconfig, not ~/.kube/config)"

step "Loading the image and applying the examples"
kind load docker-image "$IMAGE" --name "$CLUSTER" >/dev/null
kubectl apply -f examples/namespace.yaml
ok "namespace created; Pod Security enforce level: $(kubectl get ns "$NS" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}')"
kubectl apply -f examples/pod.yaml
ok "examples/pod.yaml was ADMITTED by a namespace enforcing the 'restricted' standard"
wait_ready wizardry 120
ok "pod Ready (readiness probe on /health passes)"

step "Requests through a port-forward"
kubectl port-forward -n "$NS" pod/wizardry "$LOCAL_PORT:8000" >/dev/null 2>&1 &
PF_PID=$!
for pair in "health:healthy" "spell/fireball:Blazing" "potion/healing:phoenix_tear"; do
  path=${pair%%:*}; needle=${pair#*:}
  body=$(curl -fs --retry 15 --retry-delay 1 --retry-all-errors "http://127.0.0.1:$LOCAL_PORT/$path") \
    || fail "GET /$path failed"
  case "$body" in *"$needle"*) ok "GET /$path contains '$needle'" ;; *) fail "GET /$path: '$needle' not in: $body" ;; esac
done

step "What Kubernetes enforced inside the container"
# The script below runs INSIDE the pod, so its $(...) must not expand here (hence single quotes).
# shellcheck disable=SC2016
out=$(kubectl exec -n "$NS" wizardry -- sh -c '
  echo "uid=$(id -u) gid=$(id -g)"
  grep -E "^(CapEff|NoNewPrivs|Seccomp):" /proc/1/status | tr -d "\t" | tr "\n" " "; echo
  ( echo x > /spellbook/injected ) 2>/dev/null && echo "VIOLATION: /spellbook is writable"
  ( echo x > /usr/local/bin/injected ) 2>/dev/null && echo "VIOLATION: /usr/local/bin is writable"
  ( echo x > /tmp/ok ) 2>/dev/null || echo "VIOLATION: /tmp is not writable"
  chmod u+w /spellbook/main.py 2>/dev/null && echo "VIOLATION: chmod u+w main.py succeeded"
  true')
printf '   %s\n' "${out//$'\n'/$'\n'   }"
case "$out" in *"uid=1337 gid=1337"*) ok "runs as uid/gid 1337" ;; *) fail "unexpected user: $out" ;; esac
case "$out" in *"CapEff:0000000000000000"*) ok "effective capabilities: none" ;; *) fail "capabilities not empty: $out" ;; esac
case "$out" in *"NoNewPrivs:1"*) ok "no-new-privileges is active" ;; *) fail "NoNewPrivs not set: $out" ;; esac
case "$out" in *"Seccomp:2"*) ok "seccomp filter is active" ;; *) fail "seccomp not in filter mode: $out" ;; esac
case "$out" in *VIOLATION:*) fail "filesystem/permission problem: $out" ;; *) ok "root filesystem and application files read-only; /tmp writable" ;; esac

[ "$(pod_field wizardry '{.spec.containers[0].securityContext.readOnlyRootFilesystem}')" = true ] \
  || fail "readOnlyRootFilesystem is not true in the API object"
ok "API object: readOnlyRootFilesystem=true"

step "Stability (liveness probe has had time to run)"
sleep 20
[ "$(pod_field wizardry '{.status.containerStatuses[0].restartCount}')" = 0 ] || fail "container restarted"
[ "$(pod_field wizardry '{.status.containerStatuses[0].ready}')" = true ] || fail "container no longer ready"
ok "0 restarts, still Ready"

step "Random user IDs (documented in RUNTIME_SECURITY.md)"
make_variant arb-fsgroup 0 | kubectl apply -f - >/dev/null
make_variant arb-nogroup 1 | kubectl apply -f - >/dev/null
wait_ready arb-fsgroup 120
ok "uid/gid 10001 WITH fsGroup 1337: runs and is Ready"
deadline=$((SECONDS + 90))
until [ "$(pod_field arb-nogroup '{.status.containerStatuses[0].restartCount}' 2>/dev/null || echo 0)" -ge 1 ]; do
  [ "$SECONDS" -lt "$deadline" ] || fail "arb-nogroup was expected to crash-loop but did not"
  sleep 3
done
[ "$(pod_field arb-nogroup '{.status.containerStatuses[0].ready}')" != true ] || fail "arb-nogroup unexpectedly Ready"
kubectl logs -n "$NS" arb-nogroup --previous 2>/dev/null | grep -q "Permission denied" \
  || kubectl logs -n "$NS" arb-nogroup 2>/dev/null | grep -q "Permission denied" \
  || fail "arb-nogroup did not fail with 'Permission denied'"
ok "uid/gid 10001 WITHOUT fsGroup: crash-loops with 'Permission denied', as documented"

echo
echo "All Kubernetes smoke checks passed."
