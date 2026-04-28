# Design: nodejs-security-patch

## Current state
The mctl-portal Dockerfile specifies a Node.js 22 LTS base image. The exact
minor/patch version is pinned (e.g., `FROM node:22.x.y-bookworm-slim`) to
ensure reproducible builds. The image is built by CI, tagged with a git SHA,
pushed to the container registry, and referenced from `mctl-gitops`. ArgoCD
deploys the image to the `admins` namespace.

The currently pinned Node.js 22 version predates the March 2026 security
release and therefore contains CVE-2026-21710, CVE-2026-21711, and
CVE-2026-21637.

## Proposed solution
Update the `FROM` line in the mctl-portal Dockerfile to the latest Node.js
22 LTS patch that incorporates all three March 2026 CVE fixes. The exact
version number must be confirmed from https://nodejs.org/en/blog/vulnerability/march-2026-security-releases
at the time of implementation.

Steps:
1. Identify the exact Node.js 22 LTS patch version from the March 2026
   security release blog post.
2. Update the `FROM node:22.x.y-bookworm-slim` line in the Dockerfile.
3. Build the new image locally; run `trivy image` to confirm no remaining
   HIGH/CRITICAL Node.js runtime CVEs.
4. Run the standard smoke-test suite against the local image.
5. Push the image, update the tag in `mctl-gitops`, open a PR, and promote
   via ArgoCD as usual.

This is an intentionally narrow change — only the base image `FROM` line
changes. No application code, Backstage packages, or configuration files
are modified by this proposal (those are covered by the separate
`techdocs-path-traversal-fix` and `integration-credential-leak-fix`
proposals).

### Coordination with Backstage patch proposals
If the Backstage v1.50.3 image rebuild (from the other two proposals) is
happening in the same sprint, the Node.js base-image pin update SHOULD be
included in that same Dockerfile change, producing a single image that
addresses all three sets of CVEs. This avoids two separate deploy events.
If timelines diverge, each proposal can be shipped independently.

## Alternatives

### Option A: Use an untagged `node:22-lts` floating reference
Use `FROM node:22-lts` without a specific patch version so the base image
automatically picks up future security releases on each build. Dropped
because floating references reduce build reproducibility and make it
impossible to certify exactly which runtime version is in production, which
is required for compliance and rollback purposes.

### Option B: Upgrade to Node.js 24 LTS
Move to the next LTS line. Dropped for this proposal because a major Node.js
version bump requires validating compatibility with all Backstage packages and
native addons — that is a larger effort that should be planned separately.
Node.js 22 LTS receives security support until April 2027, so there is no
urgency for a major-version upgrade at this time.

### Option C: Rely on the Kubernetes node's OS-level gVisor/seccomp profile
Accept the CVEs and mitigate at the kernel layer via seccomp or gVisor
sandboxing. Dropped because the `admins` namespace does not use gVisor, and
adding it is a platform-level change. CVE-2026-21710 (DoS via memory
exhaustion) is not mitigated by seccomp. The correct fix is to patch the
runtime.

## Platform impact

### Migrations
None. A base-image change has no effect on application data or Postgres
schema.

### Backward compatibility
Node.js patch releases within the 22 LTS line maintain full API compatibility.
No application code changes are required.

### Resource impact
The updated Node.js base image has an identical footprint to the current one.
No change in CPU or memory consumption. No impact on the `labs` tenant (the
service runs in `admins`). No flag required.

### Risks and mitigations
- **Risk:** The Node.js patch release inadvertently changes a runtime behavior
  relied on by a Backstage plugin (e.g., HTTP header handling).
  **Mitigation:** Run the full Playwright e2e suite in staging before
  promoting to production.
- **Risk:** The new base image introduces a new OS-level package with its own
  CVEs.
  **Mitigation:** Run `trivy image` on the built image and review any new
  findings before promoting.
- **Risk:** Simultaneous application of this patch and the Backstage v1.50.3
  bump makes it harder to attribute a regression.
  **Mitigation:** If combining into one image build, ensure each change set is
  individually reviewable in the PR diff. If a regression is detected, the
  rollback is still a single image-tag revert.
