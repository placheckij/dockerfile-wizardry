# 🛡️ Runtime Security Best Practices

While the Dockerfile implements build-time security, these are **runtime security flags** you should use when deploying containers in production.

## 🔐 Essential Runtime Security Flags

### 1. Read-Only Root Filesystem (CIS 5.13)
Prevent any modifications to the container filesystem:
```bash
docker run --read-only --tmpfs /tmp:rw,noexec,nosuid,size=100m wizardry:latest
```
**Why**: Prevents attackers from modifying files or installing malware.

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
  wizardry:latest
```
**Why**: Prevents DoS attacks and resource starvation. `--memory` is CIS 5.11 and `--pids-limit` is CIS 5.29; to give containers a relative CPU *priority* (CIS 5.12) use `--cpu-shares` instead of, or alongside, the hard `--cpus` cap.

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

### 7. User Namespace Remapping
Map container users to different host users:
```bash
# In /etc/docker/daemon.json
{
  "userns-remap": "default"
}
```
**Why**: Even if someone breaks out, they're not root on the host.

## 🐳 Docker Compose Example

```yaml
services:
  wizardry:
    image: wizardry:latest
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=100m
    ports:
      - "127.0.0.1:8000:8000"
    # No healthcheck block: the image ships its own HEALTHCHECK (it uses Python,
    # the image has no curl). Overriding it here would need a command that exists
    # inside the container.
    restart: on-failure:5
```

## ☸️ Kubernetes Security Context

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: wizardry
  labels:
    app: wizardry
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1337
    runAsGroup: 1337
    fsGroup: 1337
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: wizardry
    image: wizardry:latest
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      runAsNonRoot: true
      runAsUser: 1337
      capabilities:
        drop:
          - ALL
    ports:
    - containerPort: 8000
      name: http
      protocol: TCP
    resources:
      limits:
        memory: "512Mi"
        cpu: "1000m"
      requests:
        memory: "256Mi"
        cpu: "500m"
    livenessProbe:
      httpGet:
        path: /health
        port: 8000
        scheme: HTTP
      initialDelaySeconds: 10
      periodSeconds: 30
      timeoutSeconds: 3
      successThreshold: 1
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /health
        port: 8000
        scheme: HTTP
      initialDelaySeconds: 5
      periodSeconds: 10
      timeoutSeconds: 3
      successThreshold: 1
      failureThreshold: 3
    volumeMounts:
    - name: tmp
      mountPath: /tmp
  volumes:
  - name: tmp
    emptyDir:
      sizeLimit: 100Mi
  restartPolicy: Always
```

## 🔑 Secrets Management

### Never Use Environment Variables for Secrets
❌ **Bad**:
```bash
docker run -e DATABASE_PASSWORD=secret123 wizardry:latest
```

✅ **Good - Docker Secrets**:
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

✅ **Good - Kubernetes Secrets**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-secret
type: Opaque
data:
  password: c2VjcmV0MTIz  # base64 encoded
---
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: wizardry
    env:
    - name: DB_PASSWORD
      valueFrom:
        secretKeyRef:
          name: db-secret
          key: password
```

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
- [ ] Resource limits configured
- [ ] Health checks defined
- [ ] Secrets mounted securely (not in ENV)
- [ ] Image scanned for vulnerabilities
- [ ] Base image regularly updated
- [ ] No privileged mode (--privileged) (CIS 5.5)
- [ ] Published ports bound to a specific interface (CIS 5.14)
- [ ] Restart policy limited (`--restart=on-failure:5`) (CIS 5.15)
- [ ] Default seccomp profile left enabled (CIS 5.22)
- [ ] Docker socket not mounted into the container (CIS 5.32)
- [ ] Network policies defined (K8s)
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
  -p 127.0.0.1:8000:8000 \
  --restart=on-failure:5 \
  wizardry:latest
```

## 📚 References

- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker) (control numbers in this repo follow v1.9.0)
- [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
