#!/usr/bin/env bash
# Smoke test for examples/namespace.yaml + pod.yaml + networkpolicy.yaml on a throwaway kind cluster.
#
# Creates a cluster, loads the image, applies the examples (the namespace enforces the
# Pod Security "restricted" standard), then checks what Kubernetes ACTUALLY enforced
# inside the container - not just what the manifests say - that the NetworkPolicy really
# blocks the traffic it should, and the documented outcomes for random user IDs
# (see "Which user and group the container needs" in RUNTIME_SECURITY.md).
#
# SAFETY
#  - Everything runs against its own temporary kubeconfig file, never ~/.kube/config, and
#    the script refuses to continue unless the current context is the throwaway cluster it
#    just created. Your own kubectl contexts are never read or changed.
#  - The kind cluster gets a unique name and is the only cluster this script ever deletes.
#    kind identifies clusters by Docker container, not by kubeconfig, so the script also
#    refuses to run if a cluster with the chosen name already exists.
#
# Needs: docker, kind, kubectl, python3, curl, and the image:  docker build -t wizardry:1.0.0 .
# Optional: KIND_NODE_IMAGE (e.g. kindest/node:v1.37.0@sha256:...) to pin the node image,
#           KIND_CLUSTER_NAME to choose the cluster name.
# Usage: .github/scripts/smoke_kubernetes.sh
set -euo pipefail

cd "$(dirname "$0")/../.."

IMAGE=wizardry:1.0.0
CLUSTER=${KIND_CLUSTER_NAME:-wizardry-smoke-$$}
NS=wizardry

KUBECONFIG_FILE=$(mktemp "${TMPDIR:-/tmp}/wizardry-kubeconfig.XXXXXX")
PF_LOG=$(mktemp "${TMPDIR:-/tmp}/wizardry-portforward.XXXXXX")
export KUBECONFIG="$KUBECONFIG_FILE"   # kind and kubectl below use ONLY this file

fail() { echo "❌ $*" >&2; exit 1; }

for tool in docker kind kubectl python3 curl; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is required but not installed"
done
docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || fail "image $IMAGE not found - build it first: docker build -t $IMAGE ."
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  fail "a kind cluster named '$CLUSTER' already exists; refusing to touch it (choose another KIND_CLUSTER_NAME)"
fi

CREATED=0
PF_PID=""
cleanup() {
  local rc=$?
  if [ -n "$PF_PID" ]; then kill "$PF_PID" 2>/dev/null || true; fi
  if [ "$rc" -ne 0 ] && [ "$CREATED" = 1 ]; then
    echo "--- diagnostics ---" >&2
    kubectl get pods -A -o wide >&2 2>/dev/null || true
    kubectl describe pods -n "$NS" 2>/dev/null | tail -n 40 >&2 || true
    kubectl logs -n "$NS" wizardry --tail 20 >&2 2>/dev/null || true
  fi
  if [ "$CREATED" = 1 ]; then
    kind delete cluster --name "$CLUSTER" --kubeconfig "$KUBECONFIG_FILE" >/dev/null 2>&1 || true
  fi
  rm -f "$KUBECONFIG_FILE" "$PF_LOG"
}
trap cleanup EXIT

step() { echo; echo "== $*"; }
ok() { echo "✅ $*"; }

# A pod's field via jsonpath
pod_field() { kubectl get pod "$1" -n "${3:-$NS}" -o jsonpath="$2"; }

# Wait up to $2 seconds for pod $1 to be Ready
wait_ready() { kubectl wait pod/"$1" -n "$NS" --for=condition=Ready --timeout="${2}s" >/dev/null; }

# Wait (up to 120 s) for a run-to-completion pod and print its final phase
wait_phase() { # wait_phase <namespace> <pod>
  local deadline=$((SECONDS + 120)) phase
  while [ "$SECONDS" -lt "$deadline" ]; do
    phase=$(kubectl get pod "$2" -n "$1" -o jsonpath='{.status.phase}' 2>/dev/null || true)
    case "$phase" in Succeeded|Failed) echo "$phase"; return 0 ;; esac
    sleep 2
  done
  echo Timeout
}

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

# What every connectivity probe runs. It prints ONE explicit result and uses distinct exit codes, so a
# test can tell "the network dropped the packets" from anything else that makes a probe fail:
#   REACHED          the HTTP request succeeded                          (exit 0)
#   BLOCKED timeout  the connection timed out - what a NetworkPolicy drop looks like   (exit 1)
#   ERROR ...        anything else: refused, HTTP 500, DNS, a bug         (exit 2)
PROBE_PY='
import socket, sys, urllib.error, urllib.request
try:
    urllib.request.urlopen("http://%s:8000/health" % sys.argv[1], timeout=4)
    print("REACHED")
except Exception as e:
    reason = e.reason if isinstance(e, urllib.error.URLError) else e
    if isinstance(reason, (TimeoutError, socket.timeout)):
        print("BLOCKED timeout")
        sys.exit(1)
    print("ERROR", type(e).__name__, e)
    sys.exit(2)
'

# A run-to-completion client pod (Pod Security "restricted"-compliant) that runs PROBE_PY against an IP
make_client() { # make_client <name> <namespace> <role label or ''> <target ip>
  PROBE_PY="$PROBE_PY" python3 -c '
import json, os, sys
name, ns, role, ip = sys.argv[1:5]
labels = "  labels:\n    role: %s\n" % role if role else ""
print("""apiVersion: v1
kind: Pod
metadata:
  name: %s
  namespace: %s
%sspec:
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 1337
    runAsGroup: 1337
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: client
    image: wizardry:1.0.0
    command: ["/usr/local/bin/python", "-c", %s, %s]
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop: [ALL]""" % (name, ns, labels, json.dumps(os.environ["PROBE_PY"]), json.dumps(ip)))' "$1" "$2" "$3" "$4"
}

# The final line a finished client pod logged (its explicit result), and its phase
client_result() { # client_result <namespace> <pod> -> "<phase>|<last log line>"
  local phase
  phase=$(wait_phase "$1" "$2")
  echo "$phase|$(kubectl logs "$2" -n "$1" 2>/dev/null | tail -n 1)"
}

# examples/pod.yaml as a second app instance that the NetworkPolicy does NOT select (a controlled
# endpoint for the egress test): same spec, different name and `app` label
make_target() { # make_target <name>
  python3 -c '
import sys
s = open("examples/pod.yaml").read()
head = "metadata:\n  name: wizardry\n"
assert s.count(head) == 1 and s.count("app: wizardry") == 1
s = s.replace(head, "metadata:\n  name: " + sys.argv[1] + "\n", 1).replace("app: wizardry", "app: " + sys.argv[1])
print(s)' "$1"
}

step "Creating a throwaway kind cluster ($CLUSTER) with its own kubeconfig"
kind create cluster --name "$CLUSTER" --kubeconfig "$KUBECONFIG_FILE" --wait 180s \
  ${KIND_NODE_IMAGE:+--image "$KIND_NODE_IMAGE"}
CREATED=1
[ "$(kubectl config current-context)" = "kind-$CLUSTER" ] \
  || fail "current kubectl context is not kind-$CLUSTER - refusing to continue"
ok "kubectl is pointed at kind-$CLUSTER (temporary kubeconfig, not ~/.kube/config)"

step "Loading the image and applying the examples"
kind load docker-image "$IMAGE" --name "$CLUSTER" >/dev/null
kubectl apply -f examples/namespace.yaml
enforce=$(kubectl get ns "$NS" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}')
[ "$enforce" = restricted ] || fail "namespace does not enforce Pod Security 'restricted' (label is '${enforce:-<missing>}')"
ok "namespace enforces the Pod Security 'restricted' standard"
# Policy first, so it already selects the Pod when it starts (no window where it is reachable by everyone)
kubectl apply -f examples/networkpolicy.yaml
ok "NetworkPolicy applied BEFORE the pod exists"
kubectl apply -f examples/pod.yaml
ok "examples/pod.yaml was ADMITTED by that namespace"
wait_ready wizardry 120
ok "pod Ready (readiness probe on /health passes)"

step "Requests through a port-forward"
free_port() { python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'; }
LOCAL_PORT=$(free_port)
kubectl port-forward --address 127.0.0.1 -n "$NS" pod/wizardry "$LOCAL_PORT:8000" >"$PF_LOG" 2>&1 &
PF_PID=$!
for _ in $(seq 1 30); do
  grep -q "Forwarding from 127.0.0.1:$LOCAL_PORT" "$PF_LOG" && break
  kill -0 "$PF_PID" 2>/dev/null || fail "port-forward exited: $(cat "$PF_LOG")"
  sleep 1
done
grep -q "Forwarding from 127.0.0.1:$LOCAL_PORT" "$PF_LOG" || fail "port-forward did not start: $(cat "$PF_LOG")"
for pair in "health:healthy" "spell/fireball:Blazing" "potion/healing:phoenix_tear"; do
  path=${pair%%:*}; needle=${pair#*:}
  body=$(curl -fs --retry 5 --retry-delay 1 --retry-all-errors "http://127.0.0.1:$LOCAL_PORT/$path") \
    || fail "GET /$path failed"
  case "$body" in *"$needle"*) ok "GET /$path contains '$needle'" ;; *) fail "GET /$path: '$needle' not in: $body" ;; esac
done

step "What Kubernetes enforced inside the container"
# The script below runs INSIDE the pod, so its $(...) must not expand here (hence single quotes).
# shellcheck disable=SC2016
out=$(kubectl exec -n "$NS" wizardry -- sh -c '
  echo "uid=$(id -u) gid=$(id -g)"
  grep -E "^(CapEff|NoNewPrivs|Seccomp):" /proc/1/status | tr -d "\t" | tr "\n" " "; echo
  grep -Eq "^[^ ]+ / [^ ]+ ro[, ]" /proc/mounts || echo "VIOLATION: root filesystem is not mounted read-only"
  ( echo x > /spellbook/injected ) 2>/dev/null && echo "VIOLATION: /spellbook is writable"
  ( echo x > /tmp/ok ) 2>/dev/null || echo "VIOLATION: /tmp is not writable"
  chmod u+w /spellbook/main.py 2>/dev/null && echo "VIOLATION: chmod u+w main.py succeeded"
  true')
printf '   %s\n' "${out//$'\n'/$'\n'   }"
case "$out" in *"uid=1337 gid=1337"*) ok "runs as uid/gid 1337" ;; *) fail "unexpected user: $out" ;; esac
case "$out" in *"CapEff:0000000000000000"*) ok "effective capabilities: none" ;; *) fail "capabilities not empty: $out" ;; esac
case "$out" in *"NoNewPrivs:1"*) ok "no-new-privileges is active" ;; *) fail "NoNewPrivs not set: $out" ;; esac
case "$out" in *"Seccomp:2"*) ok "seccomp filter is active" ;; *) fail "seccomp not in filter mode: $out" ;; esac
case "$out" in *VIOLATION:*) fail "filesystem/permission problem: $out" ;; *) ok "root filesystem mounted read-only; application files read-only; /tmp writable" ;; esac

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

step "Network policy (examples/networkpolicy.yaml): ingress and egress"
POD_IP=$(pod_field wizardry '{.status.podIP}')
[ -n "$POD_IP" ] || fail "could not read the app pod IP"
# A second app instance the policy does not select: the endpoint for the egress test
make_target egress-target | kubectl apply -f - >/dev/null
wait_ready egress-target 120
TARGET_IP=$(pod_field egress-target '{.status.podIP}')
[ -n "$TARGET_IP" ] || fail "could not read the egress target pod IP"

# Ingress: four clients run the same code; only namespace and labels differ. Each must finish with
# the explicit result - a pod that merely failed (OOM kill, HTTP 500, ...) proves nothing.
make_client np-allowed          "$NS"   frontend "$POD_IP"    | kubectl apply -f - >/dev/null
make_client np-unlabelled       "$NS"   ""       "$POD_IP"    | kubectl apply -f - >/dev/null
make_client np-other-namespace  default frontend "$POD_IP"    | kubectl apply -f - >/dev/null
make_client np-egress-control   "$NS"   ""       "$TARGET_IP" | kubectl apply -f - >/dev/null

expect_result() { # expect_result <namespace> <pod> <phase> <log line> <what>
  local got
  got=$(client_result "$1" "$2")
  [ "$got" = "$3|$4" ] || fail "$5: expected '$3|$4', got '$got'"
  ok "$5"
}
expect_result "$NS" np-allowed         Succeeded "REACHED"          "ingress: pod labelled role=frontend (same namespace) REACHED the app"
expect_result "$NS" np-unlabelled      Failed    "BLOCKED timeout"  "ingress: pod without the label (same namespace) was BLOCKED (timeout)"
expect_result default np-other-namespace Failed  "BLOCKED timeout"  "ingress: pod in another namespace (even with the label) was BLOCKED (timeout)"

# Egress: the app pod itself must not be able to open outbound connections. The positive control
# proves the target is reachable from a pod the policy does not select, so a timeout here is the policy.
expect_result "$NS" np-egress-control  Succeeded "REACHED"          "egress control: an unselected pod REACHED the target (so the target is reachable)"
# stdout only: kubectl prints "command terminated with exit code N" on stderr when the probe exits non-zero
egress_out=$(kubectl exec -n "$NS" wizardry -- /spellbook/.venv/bin/python -c "$PROBE_PY" "$TARGET_IP" 2>/dev/null | tail -n 1 || true)
[ "$egress_out" = "BLOCKED timeout" ] \
  || fail "egress: the app pod's outbound connection was not blocked by timeout (got: '$egress_out')"
ok "egress: the app pod's own outbound connection to the same target was BLOCKED (timeout)"

[ "$(pod_field wizardry '{.status.containerStatuses[0].ready}')" = true ] \
  || fail "app pod is no longer Ready (kubelet probes should be unaffected by the policy)"
curl -fs --retry 3 --retry-delay 1 --retry-all-errors "http://127.0.0.1:$LOCAL_PORT/health" >/dev/null \
  || fail "port-forward no longer works with the policy in place"
ok "app still Ready and reachable through the port-forward"

echo
echo "All Kubernetes smoke checks passed."
