# Tasks: issue-210-feat-web-asset-integrity-contract-immuta

- [ ] 1. Create `docs/contracts/web-asset-integrity.md` with the scope/status banner (docs-only,
  no enforcement, links to epic #330, evidence #207/#208, issue #210) and terms. Reuse the
  provenance vocabulary of `docs/evidence/web-contract-evidence.md`.
  - DoD: The file exists. The banner says the owner GO covers contract preparation only, and
    that SRI rollout, CI, GitOps, CSP and deployment are out of scope.
- [ ] 2. Write the release manifest specification (depends on 1).
  - DoD: The field table covers `designVersion`, 40-hex `sourceCommit`, `provenance`
    (run/digest/attestation SHOULD) and `assets[]` (`path`, `url`, `npmExport`, `bytes`,
    `mediaType`, `sha256`, optional `sri`).
  - DoD: It includes one fenced YAML example for `0.20.2`, labelled illustrative and
    non-executable. It uses the SHA-256 values from evidence §3 (tagged observed), the byte
    sizes and sha384 values (tagged `[CODE]`-only), `sourceCommit: unknown (not observed)`, and
    digest/attestation `not-run`.
  - DoD: It describes how to check a version against its bytes: committed file, npm tarball and
    CDN body must hash equal.
- [ ] 3. Write the delivery modes A (exact-version CDN, `integrity`/`crossorigin` only after G3)
  and B (locally vendored, manifest `--check`) (depends on 2).
  - DoD: It states that `curl` is not proof of browser SRI or CORS.
  - DoD: It forbids the floating URL for shipped pages.
  - DoD: It makes Mode B mandatory for `style-src 'self'` and sensitive routes.
- [ ] 4. Write the six-site route-class supply matrix (depends on 3).
  - DoD: There are 8 rows: mctl.ai, docs, tg public, tg lite/auth, academy, alice, seerrsense
    public, seerrsense consent.
  - DoD: Each row has: owner, source pin, GitOps tag `[CONFIG]` (dated 2026-11-09), `style-src`
    from evidence §4 or `not-run`, permitted mode(s), integrity status and owner ticket.
  - DoD: There is no invented URL, hash or CSP. The docs row notes "37 hashes unavailable /
    not-run".
  - DoD: There is an explicit "no CSP relaxation" statement.
- [ ] 5. Write the verification chain table (depends on 2).
  - DoD: There are rows for source pin, lock/URL, manifest, build artifact, OCI digest, GitOps
    desired, ArgoCD observed and HTTP response.
  - DoD: Each row is classified known, `unknown (not observed)` or `not-run`, for ui.mctl.ai and
    for consumers. The ui.mctl.ai row shows tag `7340576f6dcc`, Synced/Healthy, digest unknown.
  - DoD: It states that sensitive routes are verified only via source, fixtures or preview.
- [ ] 6. Write the caching, rollback and failure sections (depends on 2).
  - DoD: The immutable/never-mutate rule cites `scripts/check-token-version-bump.mjs`.
  - DoD: The `3600` vs `14400` difference is marked unexplained, with a follow-up owner
    (candidate gitops#500) and no fix.
  - DoD: There is an acceptance/rollback table (trigger, action, verification, forbidden
    remedies).
  - DoD: Rollback is no-downtime, by repointing to the last verified exact version.
  - DoD: On CDN outage or integrity mismatch the page fails safe, with no CSP bypass, no
    `integrity` removal and no floating fallback.
- [ ] 7. Write the security/migration gates G1-G4 and the owners list (design#34, design#78,
  telegram#599, academy#210, gitops#500) (depends on 1).
  - DoD: Enforcement is deferred to `web-contract-preview-assurance`.
  - DoD: Academy `^0.20.2` is recorded as current state, owned by academy#210.
  - DoD: No new issues are opened.
- [ ] 8. Format and validate (depends on 1-7).
  - DoD: `pnpm format:check` passes.
  - DoD: `git diff --name-only origin/main` lists only `docs/contracts/web-asset-integrity.md`.
  - DoD: `BASE_REF=origin/main pnpm check:token-version` passes.

## Tests

- [ ] T1. Run `pnpm format:check`. It passes with the new file.
- [ ] T2. Run `git diff --name-only origin/main...HEAD`. The output is exactly
  `docs/contracts/web-asset-integrity.md`.
- [ ] T3. Run `BASE_REF=origin/main pnpm check:token-version`. It passes.
- [ ] T4. Run `sha256sum apps/storybook/public/0.20.2/*.css` and
  `openssl dgst -sha384 -binary <file> | base64`. Both match every hash and byte size quoted in
  the example manifest.
- [ ] T5. Grep the contract for `'sha256-` CSP source expressions. There are none, so no docs CSP
  hashes were invented.
- [ ] T6. Read the matrix as a reviewer. Every unknown cell is `unknown (not observed)` or
  `not-run`, and no row adds `https://ui.mctl.ai` to a `style-src 'self'` policy.

## Rollback

This is a docs-only change. Revert the merge commit, or open a PR deleting
`docs/contracts/web-asset-integrity.md`. No runtime, CSS byte, cache, CSP or GitOps state depends
on the file, so reverting needs no CDN purge and no version bump. The redeploy that follows
serves the same CSS bytes.
