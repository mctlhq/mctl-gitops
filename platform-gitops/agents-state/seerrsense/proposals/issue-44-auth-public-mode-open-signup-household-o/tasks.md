# Tasks: issue-44-auth-public-mode-open-signup-household-o

- [ ] 1. Add `SEERRSENSE_OPEN_SIGNUP` and `SEERRSENSE_HOUSEHOLD_EMAILS` to
      `OAuthEnvSchema` and `OAuthConfig` in `src/auth/config.ts`. `openSignup`
      is `parsed.SEERRSENSE_OPEN_SIGNUP === "true"` (strict); `householdEmails`
      is parsed with the same trim/lowercase/filter pipeline as `allowedEmails`
      (`:92-97`). — DoD: `npm run typecheck` passes; `tests/config.test.ts`
      gains cases proving `"TRUE"`, `"1"`, `"yes"` and an unset variable all
      yield `openSignup === false`.

- [ ] 2. Gate the allowlist check on `openSignup` at `src/auth/routes.ts:364`
      (depends on 1) — DoD: the condition reads
      `if (!config.openSignup && !config.allowedEmails.has(identity.email))`;
      the warn log and the `access_denied` redirect are unchanged; nothing else
      in the callback moves.

- [ ] 3. Restrict the household fallback to its owners in
      `src/providers/seerr/tenants.ts` (depends on 1) — DoD: `TenantResolver`
      takes `householdEmails: Set<string>` (defaulting to an empty set so the
      existing three-argument construction still compiles);
      `householdTenant(email, ownerOnly)` returns `{ email, source: "none" }`
      when `ownerOnly` and the address is not listed; the no-identity path
      (`:50-52`) passes `ownerOnly: false`; `Tenant` gains `subject?: string`,
      populated from the value `resolve()` already computes; wired at
      `src/api/server.ts:121-125`.

- [ ] 4. Write `src/providers/seerr/guard.ts`: `isBlockedAddress(ip)`,
      `assertPublicSeerrUrl(raw, { lookup })`, `BlockedAddressError` — DoD:
      https-only; userinfo, query and fragment refused; every range listed in
      `requirements.md` refused, including `100.64/10`, `169.254.169.254`,
      `fc00::/7`, `fe80::/10` and IPv4-mapped/compatible IPv6 unwrapped and
      re-tested; refuses when *any* resolved address is blocked; `lookup` is
      injectable and defaults to `dns.promises.lookup(host, { all: true, verbatim: true })`.

- [ ] 5. Call the guard in `PUT /api/v1/account/connection`
      (`src/api/account.ts:70-90`) before the `SeerrClient` is constructed
      (depends on 4) — DoD: a blocked address returns 400 with a generic
      message and a warn log naming the host and never the key; no `fetch` is
      issued; the existing "an API key is required the first time" path is
      unchanged.

- [ ] 6. Harden `SeerrClient` (`src/providers/seerr/client.ts:41-69`) (depends
      on 4) — DoD: `SeerrCredentials` gains `untrusted?: boolean` and an
      injectable `lookup`; when `untrusted`, `fetch()` re-runs the guard
      (memoised a few seconds per instance), passes an `undici` `Agent` whose
      `connect.lookup` answers only with a guard-approved address re-checked by
      `isBlockedAddress`, and sets `redirect: "manual"`; any 3xx is refused
      rather than followed; `createDefaultSeerrClient()` does **not** set
      `untrusted`; the per-user client in `tenants.ts:61-71` and the `PUT`
      candidate in `account.ts:85-90` do.

- [ ] 7. Introduce `SeerrUnreachableError` and `SeerrAccessChallengeError`
      (depends on 6) — DoD: a 3xx whose `location` host ends in
      `.cloudflareaccess.com`, or a response carrying `cf-access-*` /
      `cf-mitigated` headers, raises the Access error; every other untrusted
      failure raises `SeerrUnreachableError` carrying the upstream status only
      internally; `src/api/account.ts:97-102` maps the two to the Zero-Trust
      message and to a generic "could not reach that Seerr"; the upstream
      status, status text, body and resolved IP appear in no caller-visible
      string; trusted (household) clients keep today's message.

- [ ] 8. Add `@fastify/rate-limit` and `undici` to `package.json` dependencies
      (depends on 6) — DoD: `npm ci` succeeds; `package-lock.json` is committed;
      the production image (`npm ci --omit=dev`) still starts.

- [ ] 9. Register and configure the rate limiter in `src/api/server.ts`
      (depends on 8) — DoD: registered once with `global: false` and
      `hook: "preHandler"` so the subject resolved by the global auth
      `preHandler` (`:131-164`) is available to the key generator; per-IP limits
      on `/oauth/*`, `/account/session` and `PUT /api/v1/account/connection`;
      per-subject limits (falling back to IP) on `/mcp` and `/api/v1/*`; health
      probes and `/assets/*` unlimited; every window and ceiling read from
      `SEERRSENSE_RATE_LIMIT_*` with the defaults recorded in
      `requirements.md`; `onExceeding` logs a warn line with the route and a
      hashed key, never the token; the Fastify instance is created with
      `trustProxy` so `request.ip` is the client and not the ingress.

- [ ] 10. Build the model budget (depends on 3) — DoD: `resolve_usage` table
      added to `SCHEMA_SQL` in `src/auth/store-pg.ts` (new table only, no column
      added to an existing one); `countResolve(subject, day)` implemented as a
      single atomic `INSERT ... ON CONFLICT DO UPDATE SET count = count + 1
      RETURNING count` and `purgeResolveUsage(before)` wired into the hourly
      sweep at `src/api/server.ts:107-114` with 7-day retention; both methods
      also on `MemoryAuthStore`; the global ceiling uses the reserved subject
      `"__global__"`; a `BudgetedIntentExtractor` wraps `NebiusIntentExtractor`
      with a bounded 500-entry / 10-minute intent cache keyed on the existing
      `normalise()`; a cache hit consumes no budget; `ResolveBudgetError` is
      rendered as `isError: true` plain text by `resolve_media`
      (`src/mcp/server.ts:62-81`) and as HTTP 429 with the same sentence by
      `GET /api/v1/resolve` (`src/api/server.ts:346-363`); both call sites pass
      `tenant.subject`.

- [ ] 11. Turn logging on (`src/api/server.ts:91`) — DoD:
      `createMcpFastifyApp` receives a pino logger at `LOG_LEVEL` (default
      `info`) with `redact` covering `authorization`, `cookie`, `apiKey`,
      `seerrApiKeySealed` and `cfAccessClientSecret`; if the helper does not
      forward Fastify options, the Fastify instance is built directly with the
      same DNS-rebinding protection and this is recorded in the PR description;
      stdio mode still writes nothing to stdout (`src/index.ts:10-19`); warn
      lines exist for a refused sign-in, a refused household fallback, a blocked
      address, a rate-limit hit and budget exhaustion.

- [ ] 12. Document the new variables and behaviour (depends on 1, 9, 10) —
      DoD: `README.md:94-119` gains `SEERRSENSE_OPEN_SIGNUP`,
      `SEERRSENSE_HOUSEHOLD_EMAILS`, `SEERRSENSE_RESOLVE_DAILY_LIMIT`,
      `SEERRSENSE_RESOLVE_GLOBAL_DAILY_LIMIT`, the `SEERRSENSE_RATE_LIMIT_*`
      family and `LOG_LEVEL`; the "Whose Seerr" section (`README.md:139-145`)
      states that the household is offered only to listed owners; the Security
      Model section records that user-submitted addresses are https-only,
      resolved, filtered and pinned, and that rate-limit state is per-process.

- [ ] 13. Operator checklist, not code (depends on 12) — DoD: written into the
      PR description as an ordered list: (a) merge and sync the `mctl-gitops`
      `values.yaml` change adding `SEERRSENSE_HOUSEHOLD_EMAILS` with the owner's
      address, plus the limits, **before** deploying this image; (b) deploy;
      (c) confirm `kubectl logs` now shows request logs and that the owner still
      resolves to `household`; (d) publish the Google OAuth client from Testing
      to Production (scopes are `openid email profile`, non-sensitive, so no
      Google review is required; `/privacy` and `/terms` already exist); (e)
      only then set `SEERRSENSE_OPEN_SIGNUP=true`; (f) recommended, separately:
      tighten pod egress in the workspace network policy as defence in depth.

## Tests

All follow the env-reshaping pattern already in `tests/account.test.ts:83-104`
and `:225-252`: set `process.env`, dynamically `import` `buildServer`, inject
`buildServer({ fetchImpl })` and `vi.stubGlobal("fetch", ...)`. Every test below
must fail if its guard is removed.

- [ ] T1. Open signup off by default: an unlisted address is redirected with
      `error=access_denied`. With `SEERRSENSE_OPEN_SIGNUP=true` the same address
      reaches the consent page. With the flag off and
      `SEERRSENSE_ALLOWED_EMAILS` empty, every address is still denied. Also:
      `"TRUE"`, `"1"` and `"yes"` deny.

- [ ] T2. `tests/tenants.test.ts`: a subject with no `user_connections` row and
      an address not in `SEERRSENSE_HOUSEHOLD_EMAILS` resolves to
      `source: "none"` with `client === undefined`; the same subject with the
      address listed resolves to `source: "household"` with the shared client
      and the `attributedUserId`. The existing static-token and stdio cases
      (`:88-110`) still get the household client.

- [ ] T3. `PUT /api/v1/account/connection` returns 400 for
      `http://media.example.com`, `https://10.0.0.1`, `https://169.254.169.254`,
      `https://localhost`, `https://127.0.0.1`, `https://[::1]`,
      `https://[::ffff:10.0.0.1]`, `https://100.64.0.1`, `https://[fd00::1]`,
      and a hostname the injected test resolver maps to `10.0.0.5` — and
      asserts the fetch stub was **not called** for any of them.

- [ ] T4. `isBlockedAddress` unit table, including `2130706433`, `0x7f.1`,
      `::ffff:a00:1` and a public control (`93.184.216.34`, `2606:2800::1`) that
      must be allowed, so the guard is not trivially "block everything".

- [ ] T5. A public host whose `describeSelf()` answers `302` to a private
      address is refused at dial time, and the redirect is not followed (the
      stub records exactly one request).

- [ ] T6. A stored connection whose hostname resolves publicly at write time and
      privately at the next dial is refused by the dial-time guard, proving the
      check is not only in the `PUT`.

- [ ] T7. A `302` to `https://team.cloudflareaccess.com/cdn-cgi/access/login/...`
      from `describeSelf()` yields the Zero-Trust-specific message; a `403` from
      the same host yields the generic one; neither response body nor upstream
      status text appears in the reply.

- [ ] T8. The (N+1)th request inside the window returns 429 on `/oauth/authorize`,
      on `/account/session` and on `PUT /api/v1/account/connection` (per IP),
      and on `/mcp` and `/api/v1/search` (per subject) — with a second subject
      still served, proving the key is the subject and not a global counter.

- [ ] T9. The (N+1)th model-backed `resolve_media` for one subject in a day
      returns the "daily limit reached, try again tomorrow" message with
      `isError: true`, and `generateObject` (mocked) is **not** invoked. The
      global ceiling refuses a second subject once reached.

- [ ] T10. The counter survives a rebuilt app instance: consume the cap against
      one `buildServer(...)`, close it, build another over the same store, and
      the first call is still refused.

- [ ] T11. A repeated normalised query ("The Matrix!" then "the matrix") calls
      the mocked extractor once and consumes one unit of budget, not two. A
      query answered by native Seerr search alone consumes none.

- [ ] T12. No log line emitted during a full attach-and-resolve run contains the
      submitted API key, the Cloudflare service token, or an `Authorization`
      header value (capture the pino stream in the test).

- [ ] T13. Regression: with `SEERRSENSE_OPEN_SIGNUP` unset and
      `SEERRSENSE_HOUSEHOLD_EMAILS` set to the existing owner, the whole of
      `tests/account.test.ts`, `tests/oauth.test.ts` and
      `tests/integration.test.ts` pass unchanged.

## Rollback

The change is one image and two ordered gitops edits, so rolling back is ordered
too.

1. **Fastest mitigation, no deploy.** Set `SEERRSENSE_OPEN_SIGNUP` to anything
   other than `true` (or remove it) in `mctl-gitops` and sync. The gate returns
   to the allowlist immediately on the next pod start; already-signed-in
   strangers keep a token until it expires (default 1 h,
   `SEERRSENSE_ACCESS_TOKEN_TTL`) but every one of them resolves to
   `source: "none"` unless they attached their own Seerr, so the operator's
   instance is not exposed. To cut existing sessions immediately, rotate
   `SEERRSENSE_OAUTH_JWT_SIGNING_KEY`, which invalidates every issued token.
2. **If the limits or the guard are too tight.** Raise
   `SEERRSENSE_RATE_LIMIT_*` and `SEERRSENSE_RESOLVE_*` in gitops — all are
   environment variables and need no release.
3. **Full rollback.** `mctl_rollback_service` to the previous image tag
   (1.6.0). The previous image ignores `SEERRSENSE_HOUSEHOLD_EMAILS` and
   `SEERRSENSE_OPEN_SIGNUP`, so the gitops values can stay in place; do **not**
   remove `SEERRSENSE_HOUSEHOLD_EMAILS` while rolling back, since it must
   already be present if this release is ever rolled forward again. The
   `resolve_usage` table is left behind, unused and harmless — no down migration
   is needed, and no existing table or column was changed.
4. **What cannot be undone by a rollback.** Publishing the Google OAuth client
   to Production is a console action; if signup must be closed after publishing,
   step 1 is the control, not the Google client state.
