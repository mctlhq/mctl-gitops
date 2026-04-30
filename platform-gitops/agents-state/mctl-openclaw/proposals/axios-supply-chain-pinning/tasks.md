# Tasks: axios-supply-chain-pinning

- [ ] 1. **Audit axios versions in the workspace and all three tenant images** — Run `npm ls axios --all` in the repo root. Also run `docker run --rm <admins-image> npm ls axios --all`, `<labs-image>`, and `<ovk-image>`. Record all installed versions in a gist/PR comment. — DoD: Full version list documented; presence or absence of `1.14.1` / `0.30.4` confirmed for each tenant.

- [ ] 2. **CONDITIONAL: Incident response if backdoored version found** (depends on 1; execute only if 1.14.1 or 0.30.4 is present) — Open a P1 incident. Rotate S3 credentials, channel OAuth refresh tokens, GitHub deploy keys, and npm publish tokens for every affected tenant. Suspend affected tenant deployments until clean images are in place. — DoD: Incident opened; all at-risk secrets rotated and re-configured in the affected tenants.

- [ ] 3. **Add `overrides` block to root `package.json`** — Add `"overrides": { "axios": ">=1.15.0" }`. Regenerate `package-lock.json` with `npm install --package-lock-only`. — DoD: `npm ls axios --all` shows no version below 1.15.0; `package-lock.json` contains no entry for `1.14.1` or `0.30.4`; diff reviewed and approved.

- [ ] 4. **Rebuild Docker images from updated lockfile** (depends on 3) — Rebuild all three tenant Docker images using the updated `package-lock.json`. Push to the internal container registry. — DoD: New image tags built; `npm ls axios` inside each new image confirms only `>=1.15.0`.

- [ ] 5. **Deploy updated images to each tenant via gitops** (depends on 4) — Open gitops PRs for `admins`, `labs`, and `ovk` (following labs→admins→ovk order per ADR-0001). No openclaw version change; only the image rebuild. — DoD: All three tenants running the clean images; s3-sync canary and restore-state probe green.

- [ ] 6. **Add `npm audit --audit-level=high` step to CI pipeline** (depends on 3) — Insert a `npm audit --audit-level=high` step in the GitHub Actions workflow (or equivalent pipeline) that runs on every PR. Fail the build on HIGH or CRITICAL advisories. — DoD: CI pipeline fails a test PR that introduces a known-malicious package; passing PRs are not blocked by low-severity advisories.

- [ ] 7. **Document the incident and remediation in `context/decisions/`** (depends on 5) — Create `context/decisions/0004-axios-supply-chain-pinning.md` summarising the WAVESHAPER.V2 threat, the pin decision, and the CI enforcement. — DoD: ADR merged; cross-referenced from the CI pipeline comment.

## Tests

- [ ] T1. After task 3: `npm ls axios --all | grep axios` — no line contains `1.14.1` or `0.30.4`.
- [ ] T2. After task 4: for each tenant image, `docker run --rm <image> sh -c "npm ls axios --all 2>/dev/null | grep axios"` — same check.
- [ ] T3. After task 6: create a test branch that introduces `axios@1.14.1` as a direct dep in a workspace package. Confirm CI fails with a HIGH advisory finding.
- [ ] T4. After task 5: confirm s3-sync canary, restore-state probe, and channel connectivity are green for all three tenants.

## Rollback

The `overrides` pin is a one-way security fix; rolling it back would re-expose the workspace to the backdoor. If the pin causes a build failure (e.g., a package hard-requires `axios < 1.15.0`):

1. Identify the failing package and determine whether a patched version is available.
2. If not, replace the package or pin it to the last safe pre-conflict version.
3. Do NOT remove the `overrides` block without an explicit security review confirming safety.
