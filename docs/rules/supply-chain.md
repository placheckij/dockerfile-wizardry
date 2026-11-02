# Supply chain

What you build on, what you publish, and how others can check it.


## DW-SUPPLY-01: Attach an SBOM and provenance to the images you publish

strength: SHOULD

last_verified: 2026-11-02

statement:
  Build published images with attestations: `--sbom=true` for a software bill of materials and
  `--provenance=mode=max` for build provenance, or `mode=min` if build arguments might hold
  anything sensitive.

why:
  Attestations let consumers see what is inside an image and how it was built. Docker says that
  when possible you should prefer `mode=max` because it holds much more detail, and warns that it
  exposes the values of build arguments, so pair it with DW-SECRET-01 and use `min` (which Docker
  calls safe for all builds) when you cannot be sure.

how_to_check:
  manual

sources:
- https://docs.docker.com/build/metadata/attestations/sbom/
- https://docs.docker.com/build/metadata/attestations/slsa-provenance/

## DW-SUPPLY-02: Sign published images and verify them before deploying

strength: SHOULD

last_verified: 2026-11-02

statement:
  Sign images you publish (for example with cosign) and verify the signature, against the identity
  you expect, in the deployment path rather than trusting a tag. Keep the signing tool current.

why:
  Verification checks a signature against an expected identity, so a consumer can reject an image
  that was not signed by it. The tooling itself has had bugs: cosign v3.1.3 resolved
  GHSA-fx35-mq7g-6g98, a verification bypass using an unexpected public key in a legacy bundle.
  This repository does not publish images; the README explains what it would take.

how_to_check:
  manual

sources:
- https://docs.sigstore.dev/cosign/signing/signing_with_containers/
- https://docs.sigstore.dev/cosign/verifying/verify/
- https://github.com/sigstore/cosign/releases/tag/v3.1.3

## DW-SUPPLY-03: Pin GitHub Actions to full commit SHAs

strength: SHOULD

last_verified: 2026-11-02

statement:
  Reference third-party GitHub Actions by their full commit SHA, not by a mutable tag.

why:
  The Trivy supply chain advisory (GHSA-69fq-xp46-6x23, CVE-2026-33634, March 2026) recommends
  pinning GitHub Actions to full, immutable commit SHA hashes and not using mutable version tags,
  after malicious releases and action tags were published. The advisory covers Actions; it does
  not make a general claim about other tools.

how_to_check:
  manual

sources:
- https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23

## DW-SUPPLY-04: Rebuild and replace instead of patching in place, and do not let cache hide updates

strength: SHOULD

last_verified: 2026-11-02

statement:
  Apply security updates by building a new image and replacing the running container, and make
  sure your build cache does not stop updates from being picked up (for example with `docker build
  --pull`, a periodic build without cache, or automated base-image digest updates).

why:
  The NCSC guidance says security updates are typically applied by building a new image rather
  than updating containers in place, and that build caching should not prevent security updates.
  Docker notes that pinning a base image to a digest means opting out of automated security fixes,
  and Renovate recommends pinning Docker images to an exact digest while it proposes updates; see
  [tag or digest](tradeoffs.md#1-tag-or-digest-for-the-base-image) and
  [updating](tradeoffs.md#3-update-inside-the-image-or-rebuild-from-a-fresh-base).

how_to_check:
  manual. Docker Scout's `No outdated base images` policy checks base image freshness.

sources:
- https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
- https://docs.docker.com/build/building/best-practices/#pin-base-image-versions
- https://docs.renovatebot.com/docker/

## DW-SUPPLY-05: Scan the static image, and check removed files are really gone

strength: SHOULD

last_verified: 2026-11-02

statement:
  Scan the built image's contents for known vulnerabilities, misconfiguration and malware without
  running it, and confirm that files you removed during the build are not still present in a
  layer.

why:
  The NCSC guidance asks for automated scanning to detect malware, known vulnerabilities and
  misconfiguration, says scans should analyse a static image so you should never need to run the
  container to scan it, and says you should be sure that files removed during the build are
  entirely removed from the final image, which matters most for temporary secrets. See
  DW-BUILD-04.

how_to_check:
  A scanner such as Trivy, plus `docker history` or a layer inspector; this repository runs Trivy
  in CI.

sources:
- https://www.ncsc.gov.uk/collection/using-containerisation/building-container-images
