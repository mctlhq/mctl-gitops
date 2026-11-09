# Design: issue-210-feat-web-asset-integrity-contract-immuta

## Current state

How immutable CSS is produced and served today, from code read in the clone at
`7340576f6dccbf5da47049d64a5bef216277bb7a`, root version `0.20.2`:

- `packages/css/scripts/build-css.mjs` builds `dist/theme.css`, `global.css`, `prose.css`,
  `site.css`, `telegram.css` and `tailwind.css`. Each sheet's first line is
  `/* @mctlhq/css <version> — <name>. */`. The script then copies the sheets twice:
  - to `apps/storybook/public/{mctl,global,prose,site}.css` (floating);
  - to `apps/storybook/public/<version>/` (`mctl.css` is a copy of `theme.css`).
  A build only writes its own version. Older directories survive only because they are committed:
  19 directories from `0.5.0` to `0.20.2`, with `site.css` present from `0.15.0` on.
- `nginx.conf` serves the floating sheets with `Cache-Control: public, max-age=3600` and ACAO `*`.
  Versioned sheets match a semver regex that includes prerelease, and are served with
  `public, max-age=31536000, immutable` and ACAO `*`. `security-headers.conf` adds `nosniff`,
  `Referrer-Policy` and `X-Frame-Options: SAMEORIGIN`. It sets no CSP.
- `scripts/check-token-version-bump.mjs` (CI `check:token-version`) is the only thing that keeps
  "immutable" true. It requires a version bump for changes under
  `packages/{tokens,css}/{src,scripts}`, and refuses: a version that moves backwards; any edit,
  move or delete of a version directory already on `main`; and a version that is not `X.Y.Z(-pre)`.
- `.github/workflows/deploy.yml` deploys every green `main` commit, not a tag. It dispatches
  `mctl-gitops` `release-deploy.yaml` with `image_tag=${SHA:0:12}` and
  `image_name=ghcr.io/mctlhq/mctl-design`. No image digest or attestation is recorded.
- `.github/workflows/publish.yml` publishes `@mctlhq/*` to GitHub Packages on a semver tag, after
  checking the tag is on `main` and `check:versions` passes. It produces no provenance attestation.
- `README.md` lines 73-100 document the pinned URL (`/0.19.0/...`, which is stale compared with
  `0.20.2`) and the floating URL. They show no `integrity` or `crossorigin` on the stylesheet
  links. `packages/css/README.md` says to prefer the pinned CDN copy.
- `docs/evidence/web-contract-evidence.md` is the only document under `docs/`. Sections 2-4 and 7-8
  hold the live HTTP, CSP and parity evidence and the proposed entry gate for this item.
  `docs/contracts/` does not exist yet.
- `.prettierignore` excludes `apps/storybook/public/`, but `docs/` is covered by
  `pnpm format:check` (`.prettierrc`: printWidth 100).
- Committed `0.20.2` bytes, computed locally in this investigation (`[CODE]`):

  | File       | Bytes | SHA-256 (matches evidence §3)   | sha384 (`[CODE]` only, never browser-checked)                       |
  | ---------- | ----- | ------------------------------- | ------------------------------------------------------------------- |
  | mctl.css   | 36645 | `063ceae8...` (full in evidence) | `sha384-3c3+7j/sxG7OAo0w/yu2pbf6w6gfo4Wmog6O/9Hh/6uS1/ysGw7jx9JMmJhCbSdJ` |
  | global.css | 740   | `cd78060b...`                   | `sha384-QI5S3hNyBuvXCFO1r4dGHnHjwPBFfInNOAtwUndgzzREPzLWFy3rVFOjLk7Z8Fqm` |
  | prose.css  | 2898  | `71536bf8...`                   | `sha384-iBepqPx8VGFFM+TEA8To9z2KXjf3l+WOSIZ0eqckqW1SspX5n17F06nGq+cAh5g4` |
  | site.css   | 20854 | `d184836c...`                   | `sha384-qlcodqkR2eUiRvfnSbsSiyqozeCRlSN2XcBFBh89Icj/J+fOzr9VXUH46sKSvHBj` |

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-design/values.yaml`: `image.repository
  ghcr.io/mctlhq/mctl-design`, `image.tag "7340576f6dcc"`, hosts `ui.mctl.ai` and
  `admins-mctl-design.mctl.ai`. The tag has moved on from the evidence run's `7e1fbb0634d5`.
  No digest is pinned.
- `mctl_get_service_status(admins, mctl-design)`: ArgoCD `Synced`, `Healthy`, imageTag
  `7340576f6dcc`, updatedAt `2026-11-09T01:38:09Z`. `revision` was empty, so the observed digest
  and the revision are `unknown (not observed)`.
- GitOps `image.tag` for the consumers (desired state only; ArgoCD was not re-queried):
  - `admins/mctl-web` `7.21.1` (hosts mctl.ai, mctl.ru)
  - `admins/mctl-docs` `0.1.66`
  - `labs/mctl-telegram` `0.137.1`
  - `labs/mctl-telegram-preview` `main-d5b3a7d`. The evidence report recorded `main-5fb1de8`, so
    preview has moved.
  - `labs/mctl-academy` `0.1.76`
  - `labs/mctl-alice` `2.13.1`
  - `labs/seerrsense` `1.14.1`
  No consumer `values.yaml` declares a CSP or a `ui.mctl.ai` reference; CSPs are set elsewhere,
  in app or ingress, which was not observed.
- The mctl-gitops checkout is at `d704b725f3cbde4856432b4c29aa93dcd481f5a8` (2026-11-09T01:38:50Z).
- Not observed in this run: consumer source and lockfiles, OCI digests, edge cache behaviour,
  browser SRI behaviour, and the full docs CSP header. All of these are recorded as gaps.

## Proposed solution

Add one file, `docs/contracts/web-asset-integrity.md`, written in the same style as the evidence
report. It uses the same provenance tags (`[CODE]`, `[CONFIG]`, `[LIVE]`, `[PREVIEW]`), the same
`unknown (not observed)` and `not-run` vocabulary, and the rule that neither of those counts as a
pass. It uses RFC 2119 keywords (MUST, SHOULD, MAY) for specified requirements. Sections:

1. **Scope and status.** Docs-only. The contract does not authorize enforcement. It links epic
   #330, evidence #207/#208 and this issue.
2. **Terms.** Exact version, floating sheet, manifest, delivery mode A/B, route class, verified
   version.
3. **Release manifest specification.** A field table with columns field / requirement / `0.20.2`
   status:
   - `designVersion`
   - `sourceCommit` (40-hex, MUST)
   - `provenance` (CI run URL, image digest; SHOULD carry a signed attestation)
   - `assets[]`, each with `path`, `url`, `npmExport`, `bytes`, `mediaType: text/css`,
     `sha256`, and optional `sri`
   - `immutability`: a reference to `check:token-version`

   It then gives one illustrative, non-executable YAML example for `0.20.2`, built from the
   table above. The SHA-256 values are tagged `observed` because evidence §3 matched them at the
   edge. The sha384 values are tagged `[CODE]` only. `sourceCommit` is
   `unknown (not observed)`, and the image digest and attestation are `not-run`. The example is
   labelled "illustrative, non-executable, not a published artifact". The contract also specifies
   how to check a version against its bytes: hash `apps/storybook/public/<v>/<file>`, the npm
   tarball file, and the CDN body, and require all three to be equal. It notes that `mctl.css` on
   the CDN equals `@mctlhq/css/theme.css`.
4. **Delivery modes.**
   - Mode A, exact-version CDN: `<link rel="stylesheet" href="https://ui.mctl.ai/<v>/mctl.css">`,
     with `integrity` + `crossorigin="anonymous"` allowed only after gate G3 (below). Source
     permission is evaluated against the route's effective `style-src` (or `default-src` fallback),
     NOT inferred from its `script-src`; Academy public is an example of stricter script policy
     with CDN-allowed styles. It states that `curl` is not evidence for browser SRI or CORS,
     and that the floating URL MUST NOT be used for anything shipped to users.
   - Mode B, locally vendored: the CSS is copied byte for byte from a manifest version and served
     from `'self'`. A `--check` CI step compares the SHA-256 against the manifest. The line-1
     version banner is the human-readable cross-check. Mode B is required for `style-src 'self'`
     and sensitive routes.
5. **Six-site supply matrix.** Route classes: mctl.ai public; docs public; tg public; tg lite/auth;
   academy; alice; seerrsense public; seerrsense consent. Columns: owner repo, source pin
   (`unknown (not observed)` for all), GitOps tag `[CONFIG]`, observed `style-src` (from evidence
   §4, landing pages only, and `not-run` for auth/consent), permitted mode(s), integrity status
   (`not-run`), and owner ticket. Alice is Mode B only. Sensitive classes are verified through
   source/preview/fixtures only. The docs CSP row is marked "37 hashes unavailable / not-run".
   The matrix states that no CSP is relaxed.
6. **Verification chain.** A table with one row per link: source pin, lock/URL, manifest, build
   artifact, OCI digest, GitOps desired, ArgoCD observed, HTTP response. Each row has columns for
   who verifies, how, and the current status for ui.mctl.ai and for consumers. The ui.mctl.ai
   ArgoCD row is `Synced/Healthy`, tag `7340576f6dcc`, digest unknown.
7. **Caching.** States the immutable rule and the never-mutate rule, citing
   `check-token-version-bump.mjs` and the admin-merge + CDN-purge note from `CLAUDE.md`. Also:
   floating TTL is `3600` at origin vs `14400` at the edge, the cause is unexplained, and it is
   tracked as an open follow-up with gitops#500 as candidate owner. No fix is proposed. Edge
   `Age`/HIT is `not-run`.
8. **Rollback and failure.**
   - Acceptance/rollback table: trigger, action, verification, and what is forbidden.
   - Rollback means repointing the consumer to the last verified exact version, which is still
     served because its directory is committed. Mode B rollback means re-syncing the previous
     manifest version.
   - On an integrity mismatch the browser blocks the sheet. The page MUST stay functional
     unstyled or use its local fallback (design#78 for Telegram). Removing `integrity`, widening
     CSP or switching to the floating URL are forbidden.
   - Withdrawing a version needs an admin merge plus a CDN purge, outside CI.
9. **Security and migration gates.**
   - G1: SHA-256 manifest verification (MUST).
   - G2: SRI sha384 (MAY).
   - G3: enforcement only after `web-contract-preview-assurance` verifies ACAO, `crossorigin`,
     cache and real-browser outcomes.
   - G4: consumer pins exact (no `^`). Academy's `^0.20.2` is recorded as the current state,
     owned by academy#210.
10. **Owners.** design#34, design#78, telegram#599, academy#210, gitops#500, each with a
    one-line scope. No new issues are created.

Why this shape: it reuses the evidence report's vocabulary, so the two documents can be read
side by side. It records the `0.20.2` values the evidence already has and creates no new artifact
that CI would need to keep correct, because the manifest is illustrative and not executed.

## Alternatives

- **Commit a real `manifest.json` under `apps/storybook/public/<version>/` and a generator in
  `build-css.mjs`.** Dropped. The issue rules it out (NO-GO on asset/config changes). It would also
  touch `packages/css/scripts`, which would force a version bump under `check:token-version`. And
  a new file inside a published version directory is exactly the mutation that check forbids.
- **Extend `docs/evidence/web-contract-evidence.md` instead of a new contract file.** Dropped. The
  evidence report is a dated point-in-time record, and specified requirements would blur the
  line between evidence and specification that the issue asks to keep.
- **Add SRI snippets to `README.md` now.** Dropped. Browser SRI/CORS is `not-run`, and the issue
  defers enforcement to the preview-assurance phase. Changing the README would also have to fix
  the stale `0.19.0` examples, which is outside this item.

## Platform impact

- No migration, runtime, image, CSP, cache or CI change. ui.mctl.ai serves identical bytes before
  and after.
- `check:token-version` is untouched, because no watched path changes. `format:check` covers the
  new Markdown, so tables must be Prettier-formatted.
- A merge to `main` triggers `deploy.yml`, which builds a new SHA-tagged image. The Storybook
  bundle and CSS bytes are unchanged, but the image tag moves. This is the normal, accepted effect
  of any docs merge.
- Risk: the contract could be read as authorizing SRI rollout. Mitigation: an explicit status
  banner and gate G3, and every enforcement step marked deferred.
- Risk: invented values. Mitigation: every unobserved value is `unknown (not observed)` or
  `not-run`. sha384 values are tagged `[CODE]`-only, and the docs CSP hashes are not reproduced.
- Risk: values go stale. GitOps tags drift; the telegram-preview tag has already moved. Mitigation:
  each `[CONFIG]`/`[LIVE]` value carries its observation date and source.

## Open questions

- The canonical source SHA for `0.20.2` and its git tag are unobserved, because the clone is
  shallow (one commit, no tags).
- Whether a signed attestation is a MUST or a SHOULD. Today neither `publish.yml` nor
  `deploy.yml` produces one, and this proposal says SHOULD.
- The follow-up owner for the floating TTL difference. gitops#500 is the candidate; the epic
  owner decides.
- Image digests for every service and ArgoCD `revision` for mctl-design (returned empty) are
  `unknown (not observed)`.
- The real paths for the telegram lite/auth and SeerrSense consent route classes are `not-run`,
  because consumer source was not read.
