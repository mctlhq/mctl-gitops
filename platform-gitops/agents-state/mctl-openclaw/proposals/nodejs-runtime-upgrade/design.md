# Design: nodejs-runtime-upgrade

## Current state

According to `context/architecture.md`, openclaw uses Node.js + TypeScript, Docker images are
built and deployed via mctl-gitops → ArgoCD into three namespaces: `ovk`, `labs`, `admins`.
The current openclaw version is 2026.3.14 (see `context/current-version.md`).

The exact Node.js version in the base Docker image is not captured in context (no explicit
mention in `architecture.md`); however, the Node.js January 2026 Security Release was
published on 13 January 2026: if the base image has not been updated since the 2026.3.14
build, it most likely uses a version below the safe thresholds (v20.20.0 / v22.22.0 /
v24.13.0). This makes three High CVEs (CVE-2025-55131, CVE-2025-55130, CVE-2025-59465)
potentially active.

The current CI pipeline status of `npm audit` and the malicious-packages check is not
captured in context — assumed to be absent or non-blocking.

## Proposed solution

### 1. Base image bump in Dockerfile

Change the line `FROM node:XX` in the openclaw Dockerfile (or the fork-specific Dockerfile
in mctl-gitops) to Node.js v22.22.0-alpine (or an equivalent slim image).

The choice of v22 (LTS "Jod") is motivated by:
- It is the current Active LTS line at the time of the security release (April 2026).
- v24.13.0 ("Krypton") was released on 15 April 2026 — has not finished its stabilization
  period yet, although marked LTS; the proven line is preferable for production.
- v20.20.2 ("Iron") is in Security Maintenance (security fixes only, feature-frozen).

If the current Dockerfile already uses v22.x < 22.22.0 — a patch tag bump suffices.
If on v20.x — bump to v22.22.0 with compatibility validation in labs (see tasks).

The Alpine/slim variant does not affect RAM relative to the current base image — the
replacement happens within the same size category.

### 2. CI step: npm audit

Add a step to the CI pipeline (GitHub Actions / Argo Workflows / equivalent) after `npm ci`:

```
npm audit --audit-level=high --production
```

- `--audit-level=high`: blocks only High and Critical vulnerabilities (medium/low — warning).
- `--production`: ignores devDependencies in the runtime audit (devDeps don't make it into the Docker image).
- The step runs before `docker build` — fast-fail before the expensive image build.

### 3. CI step: grep for malicious packages

Add a shell-script step in CI:

```bash
#!/bin/sh
set -e
BLOCKED="lotusbail discord.js-user"
for pkg in $BLOCKED; do
  if grep -q "\"$pkg\"" package-lock.json; then
    echo "SECURITY: malicious package '$pkg' found in lockfile" >&2
    exit 1
  fi
done
echo "Malicious package check passed."
```

The step runs before `npm ci` — before any dependencies are installed.

The `BLOCKED` list grows as new disclosures appear (maintained as a config file
`.malicious-packages` at the repository root — one package name per line).

### Rollout

The Dockerfile and CI changes do not require a tenant-by-tenant rollout — they are applied
at image-build time. However, the new image is deployed per ADR 0001: labs → admins → ovk.

For `labs`: before deploying the new image record the baseline RAM (kubectl top pod), and
after deploy compare. A minor Node.js bump should not bring noticeable RAM growth;
if the delta exceeds 20MB — investigate before promoting to admins.

The restore-state probe (ADR 0002) and the s3-sync canary apply normally on the new image deploy.

## Alternatives

### 1. Upgrade to Node.js v24 LTS ("Krypton")

v24.15.0 was released on 15 April 2026 and is already LTS. Closes the same CVEs and provides
new APIs (SQLite RC, improved crypto).
- Risk: a major bump (v22 → v24) can surface breaking changes in openclaw dependencies
  (especially native addons, if any).
- Requires deeper validation in labs.
- Dropped for the first iteration: v22.22.0 suffices to close the CVEs; v24 is a separate
  proposal if needed.

### 2. Dependabot / Renovate for automatic base-image updates

An automatic PR when a new Node.js image is released — removes the manual toil.
- Requires configuring Renovate/Dependabot in the gitops repository.
- Out of scope of this proposal (separate operational task).
- Does not close active CVEs here and now.
Dropped as out-of-scope; can be added as a follow-up.

### 3. Use only `npm audit` without grepping for specific packages

`npm audit` covers known vulnerabilities in the npm advisories registry. The problem:
`lotusbail` and `discord.js-user` are malicious packages, and their advisory may not be
in the npm registry (Koi Security disclosed them in December 2025; their npm advisory
database status is unknown). An explicit grep on the package name is reliable and does not
depend on the advisory database being up to date. Dropped: we use both approaches together.

## Platform impact

### Migration

No data or state migration. The change is limited to:
- Dockerfile (a single `FROM` line)
- CI pipeline configuration (two extra steps)

### Backward compatibility

Node.js v22.22.0 is compatible with most npm packages supporting Node.js >= 18.
If the current base image is on v20.x — minor breaking changes are unlikely but require
validation in labs (TypeScript compilation, native addons, test suite).

`npm audit --production` does not affect runtime behaviour — it only blocks CI on detection.

### Resource impact

- **RAM**: minimal change (patch/minor Node.js bump, not major). Delta < 5MB expected.
  For `labs` — **not risky**.
- **CPU**: unchanged.
- **CI build time**: +30–60 seconds for the `npm audit` step (network call to the registry).

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Node.js bump breaks a native addon | Low | Validation in labs: full test run before admins/ovk |
| `npm audit` produces false positives (in devDeps) | Medium | The `--production` flag excludes devDeps; debatable findings — parse `npm audit --json` |
| grep does not cover scoped versions of malicious packages | Low | Extend the regex: `lotusbail` + `@*/lotusbail` if needed |
| New image fails to restore S3 state (breaking change in Node.js crypto) | Very low | The restore-state probe (ADR 0002) catches it before prod traffic; rollback to the previous image |
