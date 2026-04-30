# Tasks: baileys-registry-lockdown

- [ ] 1. Audit current `package-lock.json` for `@whiskeysockets/baileys` — DoD: The `resolved` URL is confirmed to be `https://registry.npmjs.org/...`; the `integrity` sha512 hash is present; no alternate registry or GitHub tarball URL is used. Findings documented in PR description. If a non-standard URL is found, treat as a security finding and escalate before continuing.

- [ ] 2. Add `@whiskeysockets` scope registry pin to `.npmrc` (depends on 1) — DoD: `.npmrc` at the workspace root contains `@whiskeysockets:registry=https://registry.npmjs.org/`; `npm install --dry-run` resolves `@whiskeysockets/baileys` from `registry.npmjs.org` in a clean local environment; no other `@whiskeysockets` packages are broken.

- [ ] 3. Add CI lint step asserting lockfile registry for `@whiskeysockets/baileys` (depends on 1) — DoD: CI pipeline includes a step (shell script or npm script) that greps `package-lock.json` for the `@whiskeysockets/baileys` resolved URL and fails if it does not start with `https://registry.npmjs.org/`; the step runs on every PR that modifies `package-lock.json` or `package.json`.

- [ ] 4. Verify `npm ci` enforces integrity hash in CI environment (depends on 2, 3) — DoD: A test run of `npm ci` completes successfully; a deliberately tampered sha512 hash in a local copy of `package-lock.json` causes `npm ci` to fail with an integrity error (validated locally, not merged).

- [ ] 5. Update developer documentation / CONTRIBUTING notes (depends on 2) — DoD: A brief note is added to the appropriate internal doc or PR template explaining the `.npmrc` scope pin and the requirement to use `npm ci` (not `npm install`) in CI; the note references this proposal's slug.

## Tests

- [ ] T1. Run `npm ci` from a clean `node_modules` state in CI and confirm it succeeds with the current `package-lock.json` and `.npmrc` in place.
- [ ] T2. Manually modify the `resolved` URL for `@whiskeysockets/baileys` in a local copy of `package-lock.json` to point to a non-npmjs URL; confirm `npm ci` fails.
- [ ] T3. Manually modify the `integrity` hash for `@whiskeysockets/baileys` in a local copy of `package-lock.json`; confirm `npm ci` fails with an integrity error.
- [ ] T4. Run the CI lint step on a `package-lock.json` that has a `github.com` tarball URL for `@whiskeysockets/baileys`; confirm the lint step fails.
- [ ] T5. Run the CI lint step on the correct `package-lock.json`; confirm it passes.
- [ ] T6. Confirm that no new `@whiskeysockets/*` package is resolvable from any registry other than `registry.npmjs.org` with the `.npmrc` scope pin active (run `npm install @whiskeysockets/some-fake-package --registry https://some-other-registry.example.com` and confirm it is blocked or resolved from the correct registry).

## Rollback
This proposal makes only configuration changes (`package-lock.json` verification, `.npmrc`, CI script). Rollback is straightforward:

1. Revert the `.npmrc` change in git (remove the `@whiskeysockets:registry` line).
2. Revert the CI lint step in the pipeline config.
3. No deployed code changes, no Kubernetes changes, no S3 changes — the rollback has zero operational impact.
4. Document the reason for rollback in the revert PR so it can be re-addressed.

Because this proposal does not change any running deployment, there is no runtime rollback procedure required.
