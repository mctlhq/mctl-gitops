# Tasks: issue-65-stop-returning-the-github-access-token-t

> Scope was corrected at approval — see **Operator decisions** at the bottom
> of this file. The token stays for `docs`/`mcp` and is dropped only for
> `tg-mcp`. Tasks below already reflect that; the decisions section explains
> why.

- [ ] 1. In `handleGitHubCallback`, make `token: accessToken` conditional on
      the flow when building `mcpPayload` (`cloudflare-worker/index.js:536-545`,
      inside `if (fragmentTargets[ghFlow])`): include it when `ghFlow` is
      `docs` or `mcp`, omit it when `ghFlow` is `tg-mcp`. `ghFlow` is already
      in scope (`index.js:466`); do NOT add a flow marker to the payload.
      — DoD: a `tg-mcp` payload has no `token` key at all (so it reaches
      neither `putOAuthSession` nor `encryptSessionPayload`); a `docs`/`mcp`
      payload is unchanged from today. `accessToken` is still used for the
      two earlier `githubAPI()` calls in both cases.

- [ ] 2. Add a `SESSION_RESPONSE_FIELDS` constant and an exported
      `buildSessionResponsePayload(payload)` allowlist function next to the
      other exported session helpers (near `redeemFromCookie`,
      `index.js:255-260`) — DoD: the list is
      `['login', 'name', 'avatar_url', 'html_url', 'sig', 'token']`; the
      function returns a new object containing only those keys that are
      present in the input, and omits every other key (`sessionId`, `exp`,
      and anything unrecognized). A comment above the constant states why
      `token` is on the list (it is the credential docs.mctl.ai hands the
      user for api.mctl.ai/mcp, not a leak) and names mctlhq/mctl-api#218 as
      the prerequisite for removing it.

- [ ] 3. Update `handleGitHubSession` (`index.js:699-700`) to build its 200
      response via `buildSessionResponsePayload(payload)` instead of the
      `sessionId`/`exp` destructure (depends on 2) — DoD: the success-path
      body is `JSON.stringify(buildSessionResponsePayload(payload))`; the
      401 "Session expired or missing" path is untouched.

- [ ] 4. Add `buildSessionResponsePayload` to the `oauth.test.mjs` import
      list from `./index.js` (depends on 2) — DoD: import list updated, test
      file still parses.

- [ ] 5. Add unit tests for `buildSessionResponsePayload` in
      `oauth.test.mjs` (depends on 2, 4) — DoD: new `test(...)` blocks
      covering the cases in the Tests section below, written as explicit
      `assert.equal('<key>' in result, ...)` checks rather than a single
      deep-equal, so a stray field still fails the test.

- [ ] 6. Run the worker test suite (depends on 1-5) — DoD:
      `npm run test:worker` exits 0 with all tests, old and new, passing.

- [ ] 7. PR description (depends on 1-6) — DoD: it states, in this order:
      (a) that issue #65's literal acceptance criterion ("no
      `token`/`access_token` field in any response reaching the browser") is
      **deliberately not met** for `docs`/`mcp`, and why —
      `mctl-docs/.../McpSetup.vue:168-170` reads `data.token` and renders it
      as the `api.mctl.ai/mcp` bearer, so removing it breaks MCP onboarding;
      (b) that `tg-mcp` provably does not read the session
      (`mctl-telegram/internal/web/connect.go` runs its own local-jwt OAuth),
      which is why dropping the token there is safe; (c) that both facts were
      checked in the sibling repositories, which this repo cannot demonstrate
      on its own; (d) that the token's real blast radius is mctl-api access
      as that user, not GitHub `read:user`; and (e) links to
      mctlhq/mctl-docs#93 and mctlhq/mctl-api#218 as the follow-ups that
      actually close the gap.

## Tests

- [ ] T1. A `docs`/`mcp`-shaped payload (with `token`) produces a result
      **containing** `token` — the regression guard against someone
      "fixing" the allowlist and silently breaking MCP onboarding.
- [ ] T2. A `tg-mcp`-shaped payload (no `token`) produces a result with no
      `token` key — `'token' in result` is `false`, not `token: undefined`.
- [ ] T3. `buildSessionResponsePayload` strips `sessionId` and `exp` (same
      behavior as today's destructure, now via allowlist).
- [ ] T4. An input payload carrying an unrecognized field (e.g.
      `internal_id`) produces a result without it. This is the test the
      allowlist exists for; without it the change is untested.
- [ ] T5. `buildSessionResponsePayload` passes through `login`, `name`,
      `avatar_url`, `html_url`, `sig` unchanged when present, and does not
      invent keys for fields absent from the input.
- [ ] T6. Existing tests in `oauth.test.mjs` (fragment URL shape, encryption
      round-trip, HMAC verify/sign, `redeemFromCookie` liveness,
      `getUnlimitedUsers`) continue to pass unmodified.
- [ ] T7. (Manual, best-effort) Exercise `for=docs` end-to-end against the
      deployed worker and confirm `docs.mctl.ai/mcp/connecting` still fills
      the MCP config snippets with a real token. This is the acceptance
      check that matters most — the failure mode this scope correction
      exists to prevent is exactly a green test suite over a broken
      onboarding page.

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

## Operator decisions (approve, 2026-08-30)

The proposal's central open question — "does any consumer read `data.token`
from `/api/github/session`?" — was answered by the operator against the
sibling repositories, which this clone could not see. **The answer is yes,
and the proposal's assumption is wrong.** Scope is rewritten accordingly.

Findings (verified, not assumed):

- `mctl-docs/docs/.vitepress/theme/components/McpSetup.vue:168-170` does
  `if (data.token) setAuth(data.token, ...)`, and the same token is then
  rendered into the Claude / Cursor / VS Code / Windsurf / Gemini / Copilot
  MCP config snippets as `Authorization: Bearer <token>` against
  `api.mctl.ai/mcp`. Delivering that token to the browser IS the product
  feature of `docs.mctl.ai/mcp/connecting` — it is not an incidental leak.
- The `tg-mcp` flow does **not** consume the session at all.
  `labs-mctl-telegram.mctl.ai/telegram/connect` is served by
  `mctl-telegram/internal/web/connect.go`, which runs its own local-jwt
  OAuth and never calls `/api/github/session`.

Decisions:

1. **REJECT the original design step 1.** Do NOT remove `token: accessToken`
   from `mcpPayload` unconditionally — that breaks docs MCP onboarding.
2. **Make the payload flow-conditional instead** (rewritten task 1): include
   `token` for `docs`/`mcp`, omit it for `tg-mcp`. `ghFlow` is already in
   scope where `mcpPayload` is built, so no flow marker is needed in the
   payload, and the response builder stays a plain allowlist — a `tg-mcp`
   session simply has no `token` to copy. Bonus over filtering at the
   response boundary: for `tg-mcp` the token never reaches the Cache API
   entry or the encrypted cookie either.
3. **KEEP design step 2 (allowlist), with `token` on the list.** The
   blocklist-destructure at `index.js:699-700` is the real defect and must
   go: any field a future change adds to `mcpPayload` leaks by default
   today.
4. Put a comment next to the allowlist stating why `token` is present (it
   is the user-facing mctl-api credential, delivered by design) and what
   would remove it (mctl-api issuing its own scoped token — see decision 6).
5. Tests must cover: `token` passed through when present; no `token` key
   when absent; an unrecognized field does not reach the response; the 401
   path unchanged. The allowlist test is the one that must exist — without
   it the actual fix is unverified.
6. **Out of scope, filed separately by the operator:**
   (a) **mctlhq/mctl-docs#93** — `McpSetup.vue:118` persists the token in
   `localStorage`, a strictly worse exposure than the JSON response this
   issue is about: any XSS on docs.mctl.ai at any later time reads it.
   (b) **mctlhq/mctl-api#218** — replacing the raw GitHub token as the
   mctl-api bearer with a scoped, revocable mctl-issued token. That is the
   real fix and is larger than this audit.

**The PR description MUST state** that issue #65's literal acceptance
criterion ("no `token`/`access_token` field in any response reaching the
browser") is deliberately NOT met for the `docs`/`mcp` flows, and why —
otherwise the review gate will read the divergence as an oversight. Blast
radius of the token is mctl-api access as that user, not merely GitHub
`read:user`; say so plainly.
