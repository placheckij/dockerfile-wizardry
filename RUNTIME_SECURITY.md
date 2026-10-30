# 🛡️ Runtime Security Best Practices

While the Dockerfile implements build-time security, these are **runtime security flags** you should use when deploying containers in production.

## 🔐 Essential Runtime Security Flags

### 1. Read-Only Root Filesystem (CIS 5.13)
Prevent any modifications to the container filesystem:
```bash
docker run --read-only --tmpfs /tmp:rw,noexec,nosuid,size=100m wizardry:latest
```
**Why**: Prevents attackers from modifying files or installing malware.

If the container mounts a volume it only needs to *read*, mount that read-only too (OWASP Rule 8):
```bash
docker run --read-only -v app-data:/data:ro wizardry:latest
```

### 2. Drop All Capabilities (CIS 5.4)
Remove all Linux capabilities, add back only what's needed:
```bash
docker run --cap-drop=ALL wizardry:latest
```
**Why**: Limits what the container can do at the kernel level.

This app listens on port 8000 as a non-root user, so it needs **no** capabilities back. Only add one (e.g. `--cap-add=NET_BIND_SERVICE`) if you change it to bind a port below 1024 - and CIS 5.8 advises against mapping privileged ports in the first place.

### 3. No New Privileges (CIS 5.26)
Prevent privilege escalation:
```bash
docker run --security-opt=no-new-privileges:true wizardry:latest
```
**Why**: Blocks setuid/setgid bits from working inside the container.

### 4. Resource Limits (CIS 5.11, 5.29)
Prevent resource exhaustion attacks:
```bash
docker run \
  --memory=512m \
  --memory-swap=512m \
  --cpus=1.0 \
  --pids-limit=100 \
  --ulimit nofile=1024:1024 \
  wizardry:latest
```
**Why**: Prevents DoS attacks and resource starvation. `--memory` is CIS 5.11 and `--pids-limit` is CIS 5.29; to give containers a relative CPU *priority* (CIS 5.12) use `--cpu-shares` instead of, or alongside, the hard `--cpus` cap.

`--ulimit nofile` caps open file descriptors, and with them concurrent connections - size it for your real load (1024 is a deliberately small demo value). OWASP Rule 7 also lists `--ulimit nproc`, but Linux counts that limit per *real user ID*, not per container ([`getrlimit(2)`](https://man7.org/linux/man-pages/man2/getrlimit.2.html)), so several containers sharing one UID are limited together and UID 0 is exempt. `--pids-limit` is the per-container control.

### 5. Bind Published Ports to a Specific Interface (CIS 5.14)
Don't expose the service on every host interface unless you mean to:
```bash
docker run -p 127.0.0.1:8000:8000 wizardry:latest
```
**Why**: `-p 8000:8000` listens on all interfaces (`0.0.0.0`). Bind to loopback, or to the one interface that should receive traffic, and put a reverse proxy in front.

### 6. Limit Restart Attempts (CIS 5.15)
```bash
docker run --restart=on-failure:5 wizardry:latest
```
**Why**: A crash-looping container is restarted at most 5 times instead of forever, so a persistent failure surfaces instead of being hidden.

### 7. Rootless Docker or User Namespace Remapping (OWASP Rule 11)
Keep a container escape from turning into host root.

**Rootless mode** runs the Docker daemon *and* the containers without host-root privileges, which reduces the impact of a daemon or runtime compromise. Install it as described in the [Docker documentation](https://docs.docker.com/engine/security/rootless/) and check its prerequisites, [tips](https://docs.docker.com/engine/security/rootless/tips/) and [troubleshooting](https://docs.docker.com/engine/security/rootless/troubleshoot/) pages to see whether it fits your workloads before relying on it.

**User namespace remapping** is the lighter alternative: container root is mapped to an unprivileged range of host users.
```bash
# In /etc/docker/daemon.json
{
  "userns-remap": "default"
}
```
**Why**: a process that escapes the container lands in an unprivileged host account instead of root. Know the limits: `userns-remap` still leaves the Docker *daemon* running as root (rootless mode does not), and neither protects against kernel vulnerabilities - containers share the host kernel, so keep it patched (OWASP Rule 0). [Podman](https://podman.io/) is daemonless and rootless by design if you prefer an alternative.

### 8. Network Isolation (OWASP Rule 5, CIS 5.30)
By default every container on Docker's `docker0` bridge can talk to every other one (inter-container connectivity is on). Rather than switching it off daemon-wide with `--icc=false`, OWASP recommends **user-defined networks**, so you decide which containers share a network:
```bash
docker network create backend
docker run --network backend wizardry:latest
```
Docker Compose does this for you: each project gets its own network, and [`examples/compose.yaml`](examples/compose.yaml) is checked to be on it and not on the default bridge. See [Docker networking](https://docs.docker.com/engine/network/).

In Kubernetes use a [NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/): [`examples/networkpolicy.yaml`](examples/networkpolicy.yaml) lets only pods labelled `role: frontend` in the same namespace reach the app (port 8000) and denies all egress. It needs a network plugin that *enforces* policies - otherwise the object is silently ignored - and CI proves it on kind, in the order the docs use (policy first, then the Pod). Ingress: the labelled pod gets through; an unlabelled pod and a pod in another namespace are blocked by a *timeout* (not merely a failed pod). Egress: the app pod cannot reach a target that an unselected pod can reach. The app's probes keep working.

### 9. Mandatory Access Control and Runtime Monitoring (OWASP Rule 6)
Never disable the default profiles; they are the baseline:
- **seccomp** - leave Docker's default profile on (CIS 5.22). `--security-opt seccomp=unconfined` removes it. [Docker seccomp](https://docs.docker.com/engine/security/seccomp/)
- **AppArmor** - on AppArmor hosts Docker generates and applies the `docker-default` profile to every container unless you override it, so do not pass `apparmor=unconfined`; add a stricter per-container profile if you can. [Docker AppArmor](https://docs.docker.com/engine/security/apparmor/)
- **SELinux** - on SELinux hosts keep it enforcing and let the runtime label containers; do not turn labelling off.

In Kubernetes the container-level `securityContext.appArmorProfile.type: RuntimeDefault` asks for the same thing ([tutorial](https://kubernetes.io/docs/tutorials/security/apparmor/)). It is deliberately **not** in `examples/pod.yaml`: it only works on nodes with AppArmor enabled, and a Pod that requests it elsewhere is rejected - on the kind node used here the result was `Cannot enforce AppArmor: AppArmor is not enabled on the host`. Add it where your nodes support it.

**Runtime monitoring** (behavioural detection of unexpected `exec` calls, privilege-escalation attempts or unusual connections) is a separate layer that needs host or cluster-level installation, so it is not part of this repo. OWASP names [Falco](https://falco.org/), [Tetragon](https://tetragon.io/) and Cilium's eBPF tooling.

### 10. The Host and the Docker Daemon (OWASP Rules 0, 1, 10)
Container hardening is only as strong as the host underneath, because containers share the host kernel:
- **Keep the host kernel and Docker Engine patched** (Rule 0). Container-escape bugs such as Leaky Vessels ([CVE-2024-21626](https://nvd.nist.gov/vuln/detail/CVE-2024-21626)) and kernel exploits such as Dirty COW work from inside a well-configured container.
- **Never expose the daemon over unauthenticated TCP** (`-H tcp://0.0.0.0:...`), and **do not mount `/var/run/docker.sock` into containers** (Rule 1; CIS 5.32). Mounting it read-only does not help: a process that can reach the socket can still send API requests that modify containers or the host.
- **Leave the daemon log level at `info`** (Rule 10); do not run `debug` unless you need it.

## 🐳 Docker Compose Example

[`examples/compose.yaml`](examples/compose.yaml) applies the flags above declaratively: a read-only root filesystem with a `/tmp` tmpfs, all capabilities dropped, `no-new-privileges`, memory and CPU limits, the port published on `127.0.0.1` only, an open-files `ulimit`, its own user-defined network, a process limit (`pids: 100`), and a bounded restart policy. It deliberately has no `healthcheck:` block: the image ships its own `HEALTHCHECK` (it uses Python, because the image has no `curl`), and an override would need a command that exists inside the container.

```bash
docker build -t wizardry:1.0.0 .
docker compose -f examples/compose.yaml up -d --wait
```

CI runs this exact file (`.github/scripts/smoke_compose.sh`): it waits for the container to become `healthy`, calls the endpoints, and checks that every setting above was actually applied: with `docker inspect` (what Docker was asked to do) and from inside the container (the root filesystem and `/tmp` mount options, the `ulimit`, and that the application files cannot be changed). It uses a unique Compose project name, so it can never touch a project of yours.

## ☸️ Kubernetes Security Context

[`examples/namespace.yaml`](examples/namespace.yaml) and [`examples/pod.yaml`](examples/pod.yaml) show the same hardening in Kubernetes. The namespace **enforces the Pod Security `restricted` standard**. The Pod runs as a non-root user (`runAsNonRoot`, uid/gid 1337) with all capabilities dropped, `allowPrivilegeEscalation: false`, a read-only root filesystem with an `emptyDir` for `/tmp`, the `RuntimeDefault` seccomp profile, resource requests and limits, and liveness and readiness probes on `/health`. [`examples/networkpolicy.yaml`](examples/networkpolicy.yaml) adds network isolation (see section 8).

```bash
docker build -t wizardry:1.0.0 .
kubectl apply -f examples/namespace.yaml -f examples/networkpolicy.yaml -f examples/pod.yaml
```

The order matters: the NetworkPolicy goes in **before** the Pod, so it already selects the Pod when it starts and the Pod is never reachable by everyone in the meantime.

CI applies these files to a throwaway `kind` cluster (`.github/scripts/smoke_kubernetes.sh`) and checks what Kubernetes actually enforced inside the container, not only what the manifests say, and that the NetworkPolicy blocks what it should: unlisted ingress *and* all egress, each proved against a positive control so that a timeout can only be the policy (see section 8).

### Which user and group the container needs

The application files are owned by `root:wizards` (gid 1337) and are not readable by anyone else (see Spell #9), so the process must run **as gid 1337 or with 1337 as a supplementary group**. [`examples/pod.yaml`](examples/pod.yaml) does both (`runAsGroup: 1337` and `fsGroup: 1337`).

Platforms that assign a random UID (for example OpenShift's restricted SCC) work only if gid 1337 is still granted:

| Pod `securityContext` | Result |
|---|---|
| `runAsUser: 1337`, `runAsGroup: 1337` | runs |
| `runAsUser: 10001`, `runAsGroup: 10001`, **`fsGroup: 1337`** | runs (`fsGroup` becomes a supplementary group) |
| `runAsUser: 10001`, `runAsGroup: 10001`, no `fsGroup` | crash-loops: `exec /spellbook/.venv/bin/uvicorn failed: Permission denied` |

With plain Docker the equivalent is `--user 10001:10001 --group-add 1337`. A random UID with only gid 0 does not work either, because gid 0 has no access.

CI checks these rows on a throwaway `kind` cluster, in a namespace enforcing the Pod Security `restricted` standard, which admits the manifest unchanged.

### Trying the manifests on a local cluster

The image is not published to any registry, so load it into the cluster first (for example `kind load docker-image wizardry:1.0.0`). The examples use the `1.0.0` tag on purpose: Kubernetes defaults `imagePullPolicy` to `Always` for the `:latest` tag, which would try to pull `wizardry` from a registry and end in `ErrImagePull`, whereas any other tag defaults to `IfNotPresent` and uses the loaded image. `.github/scripts/smoke_kubernetes.sh` does all of this; it creates its own cluster with its own kubeconfig and refuses to run against any other context, so your current `kubectl` context is never touched.

## 🔑 Secrets Management

### Never Use Environment Variables for Secrets
❌ **Bad**:
```bash
docker run -e DATABASE_PASSWORD=secret123 wizardry:latest
```

✅ **Good - Docker Secrets (Swarm)** - distributed over mutual TLS and stored in an encrypted Raft log:
```bash
echo "secret123" | docker secret create db_password -
docker service create --secret db_password wizardry:latest
```

✅ **Good - BuildKit Secrets**:
```dockerfile
# In Dockerfile
RUN --mount=type=secret,id=npmrc,dst=/root/.npmrc npm install
```
```bash
# Build command
docker build --secret id=npmrc,src=$HOME/.npmrc .
```

✅ **Good - Docker Compose secrets (local development)**:
```yaml
secrets:
  db_password:
    file: ./db_password.txt
services:
  wizardry:
    image: wizardry:1.0.0
    secrets:
      - db_password   # appears inside the container as /run/secrets/db_password
```
File-backed Compose secrets are **bind mounts**, not encrypted storage, unlike Swarm secrets. Protect the source file with host file permissions and disk encryption, and keep it out of version control. See [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/).

⚠️ **Kubernetes Secrets - use with care.** A Kubernetes Secret is only base64-*encoded*, and by default it is stored unencrypted in etcd. The Docker Secrets mechanism above does not apply to Kubernetes. Enable [encryption at rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/), restrict access with RBAC, or use an external secret store, and mount the secret as a file instead of an environment variable:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-secret
  namespace: wizardry   # must be the Pod's namespace: a secret volume cannot cross namespaces
type: Opaque
stringData:
  password: change-me   # placeholder; never commit real values
---
# Only the relevant fields of the Pod from examples/pod.yaml:
spec:
  containers:
  - name: wizardry
    volumeMounts:
    - name: db-secret
      mountPath: /run/secrets/db
      readOnly: true
  volumes:
  - name: db-secret
    secret:
      secretName: db-secret
      defaultMode: 0440
```
More in OWASP's [Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) and [Kubernetes Security](https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html) cheat sheets.

## 🔍 Image Scanning

### Scan Before Deploying
```bash
# Docker Scout
docker scout cves wizardry:latest

# Trivy
trivy image wizardry:latest

# Snyk
snyk container test wizardry:latest

# Grype
grype wizardry:latest
```

### Enable Content Trust (CIS 4.2)
```bash
export DOCKER_CONTENT_TRUST=1
docker pull wizardry:latest  # Will verify signature
```

## 📋 Security Checklist

Before deploying to production, verify:

- [ ] Container runs as non-root user (uid > 0)
- [ ] Read-only root filesystem enabled
- [ ] All capabilities dropped (--cap-drop=ALL)
- [ ] No new privileges flag set
- [ ] Resource limits configured, including `--ulimit nofile` (OWASP Rule 7)
- [ ] Health checks defined
- [ ] Secrets mounted securely (not in ENV)
- [ ] Image scanned for vulnerabilities
- [ ] Base image regularly updated
- [ ] Host kernel and Docker Engine patched (OWASP Rule 0)
- [ ] Docker daemon not exposed over TCP (OWASP Rule 1)
- [ ] Volumes mounted read-only where possible (OWASP Rule 8)
- [ ] Default seccomp / AppArmor / SELinux profiles left enabled (OWASP Rule 6)
- [ ] No privileged mode (--privileged) (CIS 5.5)
- [ ] Published ports bound to a specific interface (CIS 5.14)
- [ ] Restart policy limited (`--restart=on-failure:5`) (CIS 5.15)
- [ ] Default seccomp profile left enabled (CIS 5.22)
- [ ] Docker socket not mounted into the container (CIS 5.32)
- [ ] User-defined network or NetworkPolicy so only the containers that must talk to it can (OWASP Rule 5)
- [ ] Pod security standards enforced (K8s)
- [ ] Logging configured
- [ ] Security contexts applied

## 🎯 Quick Production Command

Combine all security flags:
```bash
docker run -d \
  --name wizardry \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=100m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges:true \
  --memory=512m \
  --cpus=1.0 \
  --pids-limit=100 \
  --ulimit nofile=1024:1024 \
  -p 127.0.0.1:8000:8000 \
  --restart=on-failure:5 \
  wizardry:latest
```

## 📚 References

- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker) (control numbers in this repo follow v1.9.0)
- [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
