# Sources

Every rule cites the primary document it is written from. This page lists those documents by
site, with the rules that cite each one, so you can see what the rulebook rests on and where to
read further. It is generated from the rules by `.github/scripts/check_rules.py --write`; CI
fails if it is out of date.

<!-- sources-index:start -->
### cheatsheetseries.owasp.org

- [cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-12-utilize-docker-secrets-for-sensitive-data-management](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-12-utilize-docker-secrets-for-sensitive-data-management) - DW-BUILD-03
- [cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-2-set-a-user) - DW-USER-01
- [cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-5a-be-careful-when-mapping-container-ports-to-the-host-with-firewalls-like-ufw](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-5a-be-careful-when-mapping-container-ports-to-the-host-with-firewalls-like-ufw) - DW-HEALTH-01
- [cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-8-set-filesystem-and-volumes-to-read-only) - DW-USER-02
- [cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-9-integrate-container-scanning-tools-into-your-cicd-pipeline](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html#rule-9-integrate-container-scanning-tools-into-your-cicd-pipeline) - DW-DEPS-01

### docs.astral.sh

- [docs.astral.sh/uv/guides/integration/docker/](https://docs.astral.sh/uv/guides/integration/docker/) - DW-BUILD-01, DW-DEPS-02

### docs.docker.com

- [docs.docker.com/build/building/base-images/#create-a-minimal-base-image-using-scratch](https://docs.docker.com/build/building/base-images/#create-a-minimal-base-image-using-scratch) - DW-BUILD-04
- [docs.docker.com/build/building/best-practices/#add-or-copy](https://docs.docker.com/build/building/best-practices/#add-or-copy) - DW-BUILD-06
- [docs.docker.com/build/building/best-practices/#leverage-build-cache](https://docs.docker.com/build/building/best-practices/#leverage-build-cache) - DW-BUILD-01
- [docs.docker.com/build/building/best-practices/#pin-base-image-versions](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions) - DW-BASE-01, DW-SUPPLY-04
- [docs.docker.com/build/building/best-practices/#run](https://docs.docker.com/build/building/best-practices/#run) - DW-DEPS-01, DW-DEPS-02
- [docs.docker.com/build/building/best-practices/#use-multi-stage-builds](https://docs.docker.com/build/building/best-practices/#use-multi-stage-builds) - DW-BUILD-02
- [docs.docker.com/build/building/multi-platform/](https://docs.docker.com/build/building/multi-platform/) - DW-BUILD-08
- [docs.docker.com/build/building/multi-stage/](https://docs.docker.com/build/building/multi-stage/) - DW-BUILD-04
- [docs.docker.com/build/building/secrets/](https://docs.docker.com/build/building/secrets/) - DW-SECRET-01
- [docs.docker.com/build/cache/backends/](https://docs.docker.com/build/cache/backends/) - DW-BUILD-07
- [docs.docker.com/build/cache/backends/registry/](https://docs.docker.com/build/cache/backends/registry/) - DW-BUILD-07
- [docs.docker.com/build/cache/optimize/](https://docs.docker.com/build/cache/optimize/) - DW-BUILD-05, DW-BUILD-06
- [docs.docker.com/build/metadata/attestations/sbom/](https://docs.docker.com/build/metadata/attestations/sbom/) - DW-SUPPLY-01
- [docs.docker.com/build/metadata/attestations/slsa-provenance/](https://docs.docker.com/build/metadata/attestations/slsa-provenance/) - DW-BUILD-09, DW-SECRET-01, DW-SUPPLY-01
- [docs.docker.com/engine/release-notes/29/](https://docs.docker.com/engine/release-notes/29/) - DW-SUPPLY-06
- [docs.docker.com/reference/build-checks/json-args-recommended/](https://docs.docker.com/reference/build-checks/json-args-recommended/) - DW-HEALTH-05
- [docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/](https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/) - DW-SECRET-01
- [docs.docker.com/reference/cli/docker/container/run/#init](https://docs.docker.com/reference/cli/docker/container/run/#init) - DW-HEALTH-04
- [docs.docker.com/reference/dockerfile/](https://docs.docker.com/reference/dockerfile/) - DW-BUILD-05
- [docs.docker.com/reference/dockerfile/#add](https://docs.docker.com/reference/dockerfile/#add) - DW-BUILD-03, DW-DEPS-03
- [docs.docker.com/reference/dockerfile/#expose](https://docs.docker.com/reference/dockerfile/#expose) - DW-HEALTH-01
- [docs.docker.com/reference/dockerfile/#healthcheck](https://docs.docker.com/reference/dockerfile/#healthcheck) - DW-HEALTH-02
- [docs.docker.com/reference/dockerfile/#label](https://docs.docker.com/reference/dockerfile/#label) - DW-BASE-02
- [docs.docker.com/reference/dockerfile/#stopsignal](https://docs.docker.com/reference/dockerfile/#stopsignal) - DW-HEALTH-03
- [docs.docker.com/reference/dockerfile/#syntax](https://docs.docker.com/reference/dockerfile/#syntax) - DW-SUPPLY-06
- [docs.docker.com/reference/dockerfile/#understand-how-arg-and-from-interact](https://docs.docker.com/reference/dockerfile/#understand-how-arg-and-from-interact) - DW-BASE-01

### docs.python.org

- [docs.python.org/3/library/py_compile.html](https://docs.python.org/3/library/py_compile.html) - DW-DEPS-02

### docs.renovatebot.com

- [docs.renovatebot.com/docker/](https://docs.renovatebot.com/docker/) - DW-SUPPLY-04

### docs.sigstore.dev

- [docs.sigstore.dev/cosign/signing/signing_with_containers/](https://docs.sigstore.dev/cosign/signing/signing_with_containers/) - DW-SUPPLY-02
- [docs.sigstore.dev/cosign/verifying/verify/](https://docs.sigstore.dev/cosign/verifying/verify/) - DW-SUPPLY-02

### github.com

- [github.com/advisories/GHSA-7236-3392-c5c6](https://github.com/advisories/GHSA-7236-3392-c5c6) - DW-SUPPLY-06
- [github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23) - DW-SUPPLY-03
- [github.com/docker-library/official-images/blob/master/README.md](https://github.com/docker-library/official-images/blob/master/README.md) - DW-DEPS-03
- [github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md](https://github.com/goodwithtech/dockle/blob/master/CHECKPOINT.md) - DW-SECRET-01
- [github.com/krallin/tini](https://github.com/krallin/tini) - DW-HEALTH-04
- [github.com/moby/buildkit/blob/master/docs/build-repro.md](https://github.com/moby/buildkit/blob/master/docs/build-repro.md) - DW-BUILD-09
- [github.com/moby/buildkit/releases/tag/dockerfile%2F1.16.0](https://github.com/moby/buildkit/releases/tag/dockerfile%2F1.16.0) - DW-DEPS-03
- [github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys](https://github.com/opencontainers/image-spec/blob/main/annotations.md#pre-defined-annotation-keys) - DW-BASE-02
- [github.com/sigstore/cosign/releases/tag/v3.1.3](https://github.com/sigstore/cosign/releases/tag/v3.1.3) - DW-SUPPLY-02

### hynek.me

- [hynek.me/articles/docker-signals/](https://hynek.me/articles/docker-signals/) - DW-HEALTH-05

### trivy.dev

- [trivy.dev/latest/docs/](https://trivy.dev/latest/docs/) - DW-SUPPLY-05

### wiki.alpinelinux.org

- [wiki.alpinelinux.org/wiki/Local_APK_cache](https://wiki.alpinelinux.org/wiki/Local_APK_cache) - DW-BUILD-05

### www.cisecurity.org

- [www.cisecurity.org/benchmark/docker](https://www.cisecurity.org/benchmark/docker) - DW-BASE-01, DW-BUILD-03, DW-BUILD-04, DW-DEPS-01, DW-HEALTH-02, DW-SECRET-01, DW-USER-01

### www.ncsc.gov.uk

- [www.ncsc.gov.uk/collection/using-containerisation/building-container-images](https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images) - DW-BUILD-10, DW-SECRET-01, DW-SUPPLY-04, DW-SUPPLY-05
<!-- sources-index:end -->
