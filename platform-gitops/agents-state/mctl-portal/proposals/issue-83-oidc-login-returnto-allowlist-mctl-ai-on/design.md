# Design: issue-83-oidc-login-returnto-allowlist-mctl-ai-on

## Current state
`plugins/oidc-provider-backend/src/router.ts` implements a small OIDC
provider used by Dex/Traefik ForwardAuth. The relevant handler:

```ts
// GET /login?returnTo=https://tenant-service.mctl.ai/
router.get('/login', async (req: Request, res: Response) => {
  const returnTo = typeof req.query.returnTo === 'string' ? req.query.returnTo.trim() : '';
  if (!returnTo) {
    res.status(400).send('Missing returnTo');
    return;
  }
  const session = await readSessionCookie(req);
  if (session && session.expiresAt > Date.now()) {
    res.setHeader('Set-Cookie', buildSessionCookie(session.sessionId, returnTo));
    res.redirect(returnTo);
    return;
  }
  res.redirect(await buildGitHubAuthRedirect(returnTo));
});
```
(`router.ts` lines ~254-269, matching the issue's cited evidence.)

`returnTo` is only checked for emptiness. It flows two ways:
1. Already-authenticated: straight into `buildSessionCookie` (which derives
   a cookie `Domain` from the URL host, see `deriveCookieDomain`, lines
   ~74-87) and `res.redirect(returnTo)`.
2. Not authenticated: into `buildGitHubAuthRedirect(returnTo)` (lines
   ~58-68), which calls `store.savePendingAuth(githubState, returnTo, ...)`
   and later, in the `/github/callback` handler (lines ~355-445), the
   persisted `pending.returnTo` is used unconditionally for
   `buildSessionCookie` and `res.redirect(pending.returnTo)`.

Neither path validates the host, so any URL (including
`https://evil.example/`, protocol-relative `//evil.example`, or a lookalike
host like `https://mctl.ai.evil.example/`) is accepted and eventually
redirected to.

The codebase already has two precedents for exactly this kind of
"allow this domain and its subdomains" host check:
- `deriveCookieDomain` (lines ~74-87): `host === 'localhost' || ...`,
  `host.endsWith('.mctl.ai')`, `host.endsWith('.mctl.me')`.
- `decodeOpenAICodexReturnTo` (lines ~595-613): parses a `returnTo` out of
  an OAuth `state` blob and accepts it only if
  `host === 'localhost' || host.endsWith('.mctl.ai') || host.endsWith('.mctl.me')`.

Both use `URL.hostname` plus `endsWith('.mctl.ai')`, i.e. a dot-boundary
suffix check, which is the same technique the issue asks for. Neither
handles the bare-apex case (`host === 'mctl.ai'` without a leading dot)
explicitly as a *combined* helper, and neither enforces `https`-only or
handles relative paths, because those call sites don't need to (a cookie
domain calculation ignores scheme; the Codex flow always receives a
previously-validated absolute URL).

There is no `router.test.ts` today; `oidc-provider-backend` has
`sessionAuth.test.ts` and `oidcStore.test.ts` as its Jest test precedents.

## Proposed solution
Add a single, exported, pure helper in `router.ts`:

```ts
function isAllowedReturnTo(returnTo: string): boolean {
  // Relative path: allowed, but must not be scheme-relative ("//host/...")
  // or otherwise browser-interpretable as an absolute URL.
  if (returnTo.startsWith('/') && !returnTo.startsWith('//') && !returnTo.startsWith('/\\')) {
    return true;
  }
  try {
    const url = new URL(returnTo);
    if (url.protocol !== 'https:') {
      return false;
    }
    const host = url.hostname.toLowerCase();
    return host === 'mctl.ai' || host.endsWith('.mctl.ai');
  } catch {
    return false;
  }
}

function sanitizeReturnTo(returnTo: string): string {
  return isAllowedReturnTo(returnTo) ? returnTo : DEFAULT_POST_LOGIN_PATH;
}
```

with `DEFAULT_POST_LOGIN_PATH = '/'` treated as a same-origin relative path
(i.e. it resolves against the issuer host the browser is already on for
`/login`'s already-authenticated branch, and against the issuer's own
`/authorize`-style redirect target for the GitHub round-trip branch — see
"Platform impact" for the one nuance this creates).

Wiring: call `sanitizeReturnTo` once, immediately after the existing
"missing returnTo" check in the `/login` handler, and use the sanitized
value everywhere `returnTo` is currently used in that handler:

```ts
router.get('/login', async (req: Request, res: Response) => {
  const rawReturnTo = typeof req.query.returnTo === 'string' ? req.query.returnTo.trim() : '';
  if (!rawReturnTo) {
    res.status(400).send('Missing returnTo');
    return;
  }
  const returnTo = sanitizeReturnTo(rawReturnTo);
  const session = await readSessionCookie(req);
  if (session && session.expiresAt > Date.now()) {
    res.setHeader('Set-Cookie', buildSessionCookie(session.sessionId, returnTo));
    res.redirect(returnTo);
    return;
  }
  res.redirect(await buildGitHubAuthRedirect(returnTo));
});
```

Because `buildGitHubAuthRedirect` persists whatever `returnTo` it is given
via `store.savePendingAuth`, and `/github/callback` later replays
`pending.returnTo` verbatim (lines ~444-445) without its own check, doing
the validation once at the `/login` entry point is sufficient for both the
already-authenticated redirect and the full GitHub OAuth round-trip: a
malicious value is downgraded to `DEFAULT_POST_LOGIN_PATH` before it is
ever persisted or redirected to, so `/github/callback` naturally redirects
to the safe default too. This keeps the change small and localized to a
single call site plus one helper, per the issue's "Expected fix" framing.

`isAllowedReturnTo` is a plain function with no `req`/`res` dependency, so
it is directly unit-testable (matching the `sessionAuth.ts` /
`sessionAuth.test.ts` style already used in this plugin) without needing to
mock Express.

Log line: on rejection, emit a single `logger.warn` with the rejected
host (via the existing `summarizeUrlHost` helper, lines ~150-156) but never
the full attacker-supplied string verbatim into an unbounded log field
beyond what `summarizeUrlHost` already does for other endpoints in this
file, keeping logging conventions consistent with the rest of the router.

## Alternatives
1. **Allowlist only in `buildSessionCookie`/`deriveCookieDomain`.**
   Rejected: `deriveCookieDomain` only decides the cookie's `Domain`
   attribute; it already silently falls back to no `Domain` for unknown
   hosts, but it does not stop `res.redirect(returnTo)` itself from sending
   the browser to an attacker-controlled host. The open redirect is in the
   `res.redirect` calls, not the cookie, so validating there would not
   close the actual vulnerability.
2. **Validate again inside `/github/callback` instead of (or in addition
   to) `/login`.** Considered for defense-in-depth, but `pending.returnTo`
   at that point can also legitimately be an internal `/authorize?...`
   relative URL coming from the `/authorize` handler's own
   `buildGitHubAuthRedirect(req.originalUrl)` call (a different, trusted
   caller of the same helper). Re-validating there with the same
   `mctl.ai`-only allowlist would incorrectly reject that internal
   `/authorize` round-trip unless carefully special-cased. Validating once,
   at the single untrusted entry point (`/login`'s raw query param), is
   simpler and avoids that collision; this is recorded as a possible
   follow-up hardening step rather than done now, to keep the change
   minimal and matching the issue's exact evidence location.
3. **Reuse/extend `decodeOpenAICodexReturnTo`'s allowlist (which also
   allows `localhost` and `*.mctl.me`) as the shared helper.** Rejected for
   this proposal: the issue explicitly asks for `mctl.ai`/`*.mctl.ai` only,
   https-only, and lists `mctl.ai.evil.example` as a required rejection
   case; broadening to `mctl.me`/`localhost` would pass acceptance criteria
   the issue does not ask for and could mask the fact that the Codex flow's
   own allowlist is a separately-scoped piece of code. A future cleanup
   could factor a shared `isMctlHost(host, {allowMe, allowLocalhost})`
   helper, but that is left as a follow-up, not part of this fix.

## Platform impact
- **Migrations**: none. No schema, config, or persisted-data changes.
- **Backward compatibility**: relative paths (e.g. `/catalog`) and
  `https://<anything>.mctl.ai/...` / `https://mctl.ai/...` absolute URLs —
  the only forms used by legitimate callers today (Traefik ForwardAuth
  targets, tenant dashboards under `*.mctl.ai`) — continue to work
  unchanged. Only genuinely off-platform or malformed `returnTo` values
  change behavior, and they change from "open redirect" to "redirect to
  default page", which is the intended fix.
- **Resource impact**: negligible; one extra `URL` parse and string
  comparison per `/login` call.
- **Risks + mitigations**:
  - Risk: a legitimate internal caller passes `http://` (not `https://`)
    to `/login` in some environment (e.g. a non-TLS-terminated internal
    hop). Mitigation: grep across the repo for `/login?returnTo=` call
    sites before merging (Traefik ForwardAuth config, any frontend links)
    to confirm all are `https://*.mctl.ai` or relative; call this out
    explicitly in the PR description so a reviewer with production
    knowledge can double check.
  - Risk: `DEFAULT_POST_LOGIN_PATH = '/'` might not be a meaningful landing
    page in production. Mitigation: kept intentionally simple (same-origin
    root of the issuer) so it never introduces a redirect vulnerability
    itself; can be pointed at a nicer product page later without touching
    the validation logic (tracked in Open Questions).
  - Risk: regression in the GitHub OAuth round-trip if the sanitized
    `returnTo` is only swapped in one of the two `/login` branches.
    Mitigation: the design computes `returnTo` once, right after the
    empty-check, and uses that single sanitized variable in both branches
    and in the value handed to `buildGitHubAuthRedirect`, so there is only
    one place that can drift.
