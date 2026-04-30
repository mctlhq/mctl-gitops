# Design: axios-supply-chain-pinning

## Current state

The mctl-openclaw workspace is an npm workspace (TypeScript + Node.js) with multiple packages: core openclaw, extensions per channel, and plugin-sdk consumers. `axios` appears as a transitive dependency via several packages:

- `@slack/web-api` and `@slack/webhook` explicitly pin `axios >= 1.15.0` (safe; done in their April 2025 releases).
- openclaw core and channel extensions may pull in older axios versions through other transitive paths (e.g. CLI tooling, test harnesses, or bundled provider packages).

The WAVESHAPER.V2 backdoor is present in `axios@1.14.1` and `axios@0.30.4`. It activates silently on `require('axios')` and exfiltrates credentials. The threat is real: the mctl-openclaw workspace holds S3 credentials (per-tenant), channel OAuth refresh tokens, GitHub deploy keys, and npm publish tokens — exactly the secrets WAVESHAPER.V2 targets.

No workspace-wide `overrides` or `resolutions` block is currently in place to enforce a minimum safe axios version.

See `context/architecture.md` §"Dependencies for researcher" for the full tracked dependency list.

## Proposed solution

**Three-phase approach: audit → pin → automate.**

### Phase 1: Audit (immediate — Day 1)

Run `npm ls axios --all` across the workspace and compare the installed versions of `axios` in each of the three tenant Docker images (via `docker run --rm <image> npm ls axios --all`). Document every version found.

If `1.14.1` or `0.30.4` is present in any tenant image:
1. Treat as a critical incident.
2. Rotate all secrets accessible from that tenant (S3 creds, OAuth tokens, GitHub keys, npm tokens).
3. Rebuild the image with the pin in place (Phase 2) before re-deploying.

### Phase 2: Pin (immediate — Day 1–2)

Add a workspace-wide `overrides` block to the **root** `package.json`:

```json
{
  "overrides": {
    "axios": ">=1.15.0"
  }
}
```

Regenerate `package-lock.json` (`npm install --package-lock-only`), verify with `npm ls axios`, and confirm no entry for `1.14.1` or `0.30.4` appears in the lock file. Rebuild all Docker images from the updated lockfile.

For yarn workspaces: use the `resolutions` field instead.

### Phase 3: Automate (Day 2–5)

Add `npm audit --audit-level=high` to the CI pipeline (GitHub Actions / the existing mctl-gitops pipeline). Any PR that introduces a high-severity advisory fails the build. This prevents future supply-chain compromises from reaching a tenant without an explicit bypass.

Optionally, add `socket.dev` or `Snyk` scanning as a secondary check for known-malicious packages (as distinct from CVE advisories, which `npm audit` may lag).

## Alternatives

**A. Manual image inspection only (no pin)** — Rejected. Without an enforced pin, the next `npm install` could silently re-introduce the backdoored version if a transitive dependency relaxes its own constraints.

**B. Remove axios from the dependency tree entirely** — Rejected. Axios is a transitive dep of node-slack-sdk and potentially other packages. Replacing it would require forking or patching those packages, which is disproportionate effort for a version-pinning fix.

**C. Audit only the running images, skip lock file enforcement** — Rejected. Auditing running images is necessary but not sufficient; the lock file must be fixed to protect future builds.

## Platform impact

### Migrations
Root `package.json` gains an `overrides` block; `package-lock.json` is regenerated. All tenant images must be rebuilt from the updated lockfile. No runtime behavior changes.

### Backward compatibility
`axios >= 1.15.0` is fully API-compatible with 1.14.x (the backdoor was injected without API changes). No application code changes required.

### Resource impact (especially for `labs`)
Zero memory or CPU impact. This is a lockfile-level constraint with no runtime footprint.

### Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Backdoored version was present in a deployed image | Immediate credential rotation per the Phase 1 incident procedure |
| CI `npm audit` produces false positives from other low-severity advisories | Set `--audit-level=high` to gate only on HIGH and CRITICAL; review and suppress known-safe findings with `.nsprc` or `npm audit --omit` |
| Lock file regeneration pulls in unintended dependency upgrades | Review `npm install --dry-run` diff before committing; scope the change to axios resolution only |
| Some package requires axios < 1.15.0 and cannot be upgraded | Evaluate whether that package is still maintained; if not, consider replacing it |
