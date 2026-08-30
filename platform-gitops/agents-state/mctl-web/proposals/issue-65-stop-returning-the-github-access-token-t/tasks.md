# Tasks: issue-65-stop-returning-the-github-access-token-t

- [ ] 1. Remove `token: accessToken` from `mcpPayload` in `handleGitHubCallback`
      (`cloudflare-worker/index.js` around line 588), keeping `login`, `name`,
      `avatar_url`, `html_url`, `sig`, `sessionId`, `exp` as-is.
      — DoD: `mcpPayload` no longer has a `token` field; `accessToken` is
      still used for the two `githubAPI()` profile/email calls earlier in
      the function; no other reference to `mcpPayload.token` or
      `payload.token` remains in `index.js`.

- [ ] 2. Add `SESSION_RESPONSE_FIELDS` constant and an exported
      `buildSessionResponsePayload(payload)` allowlist function next to the
      other exported session helpers (near `redeemFromCookie`,
      `index.js:255-260`) (depends on 1) — DoD: function returns a new
      object containing only `login`, `name`, `avatar_url`, `html_url`,
      `sig` when present in the input, and omits every other key
      (including `token`, `sessionId`, `exp`, or anything unrecognized).

- [ ] 3. Update `handleGitHubSession` (`index.js:699-700`) to build its
      200 response body via `buildSessionResponsePayload(payload)` instead
      of the `sessionId`/`exp` destructure (depends on 2) — DoD: the
      success-path `Response` body is `JSON.stringify(buildSessionResponsePayload(payload))`;
      the 401 "Session expired or missing" path is untouched.

- [ ] 4. Add `buildSessionResponsePayload` to the `oauth.test.mjs` import
      list from `./index.js` (depends on 2) — DoD: import list updated,
      test file still parses.

- [ ] 5. Add unit tests for `buildSessionResponsePayload` in
      `oauth.test.mjs` (depends on 2, 4) — DoD: new `test(...)` blocks
      covering:
      - a payload with `token`, `sessionId`, `exp`, `login`, `name`,
        `avatar_url`, `html_url`, `sig` set produces an object with exactly
        `{ login, name, avatar_url, html_url, sig }` — no `token`,
        `sessionId`, or `exp` key present (use
        `assert.equal('token' in result, false)` style checks, not just a
        deep-equal, so the test still fails if an unexpected field sneaks
        in).
      - a minimal payload missing optional fields (e.g. no `name`) does not
        produce `name: undefined` as an own key — DoD: `'name' in result`
        is `false` when absent from input.

- [ ] 6. Run the worker test suite and confirm it passes (depends on 1-5)
      — DoD: `npm run test:worker` (i.e.
      `node --test cloudflare-worker/oauth.test.mjs`) exits 0 with all
      tests, old and new, passing.

- [ ] 7. Manual/PR-description verification of the acceptance criteria
      (depends on 1-6) — DoD: PR description explicitly states that (a) no
      `token`/`access_token` field reaches the browser from
      `/api/github/session` for any of the three fragment flows
      (`docs`, `mcp`, `tg-mcp`), (b) the normal landing OAuth flow and
      `check-team` are unaffected (no code changes touch `userData` or
      `handleCheckTeam`), and (c) flags the cross-repo open question about
      whether `mctl-docs`/`mctl-telegram` consumers relied on the removed
      `token` field, asking reviewers with visibility into those repos to
      confirm before merge.

## Tests

- [ ] T1. `buildSessionResponsePayload` strips `token` even when present in
      the input payload (regression guard for the original leak).
- [ ] T2. `buildSessionResponsePayload` strips `sessionId` and `exp` (same
      behavior as today's destructure, now via allowlist).
- [ ] T3. `buildSessionResponsePayload` passes through `login`, `name`,
      `avatar_url`, `html_url`, `sig` unchanged when present.
- [ ] T4. `buildSessionResponsePayload` does not invent keys for fields
      absent from the input (no `undefined`-valued keys).
- [ ] T5. Existing tests in `oauth.test.mjs` (fragment URL shape, encryption
      round-trip, HMAC verify/sign, `redeemFromCookie` liveness,
      `getUnlimitedUsers`) continue to pass unmodified — confirms this
      change is additive and doesn't regress the surrounding OAuth
      machinery.
- [ ] T6. (Manual, not automatable in this repo) Exercise the `for=docs`
      and `for=tg-mcp` login flows against a real GitHub OAuth app in a
      preview/staging environment and confirm `POST /api/github/session`
      returns 200 with `{login, name, avatar_url, html_url, sig}` and no
      `token`, and that the consuming pages still complete their connect
      flow (best-effort — full verification requires the `mctl-docs`/
      `mctl-telegram` repos, which are out of scope here).

## Rollback

This is a single-file (`cloudflare-worker/index.js`) plus single-test-file
(`cloudflare-worker/oauth.test.mjs`) change with no data migrations. Rollback
is a plain `git revert` of the merge commit on `main`, followed by the
normal tag-and-deploy (`mctl_deploy_service` or pushing a new
`MAJOR.MINOR.PATCH` tag per `CLAUDE.md`). Because the OAuth session Cache
API entries and `__gh_session` cookies are short-lived (`SESSION_TTL_SEC =
300` seconds) and self-expiring, there is no persistent state to clean up
on rollback — any in-flight sessions from immediately before rollback simply
expire naturally within 5 minutes.
