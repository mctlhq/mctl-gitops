# Design: issue-421-bounded-ttl

## Current state

**Token minting.** `internal/workertoken/tokenhandler.go` implements
`POST /api/mcp/worker-token`. It is mounted in `cmd/server/main.go:454-457`
behind `auth.Middleware(provider, true, m, resourceMeta)`, requiring the
caller to already hold an authenticated identity with `admin:users`
(`id.HasScope("admin:users")`, tokenhandler.go:122-125). Given a target
`telegram_id`, it mints a JWT via `localjwt.Issuer.Mint` with:
- `Subject: "tg:" + telegram_id`, `TelegramID`, `Scopes` (defaulting to
  `allowedReadOnlyScopes = ["telegram:dialogs:read",
  "telegram:messages:read"]`, or a caller-supplied subset of it),
- `Audience: ["mcp-worker-ro"]` (plus `cfg.OAUTHJWTAudience` if configured),
- TTL = `req.TTLHours` clamped to `[0, maxWorkerTokenTTL]`, defaulting to
  `defaultWorkerTokenTTL` (30 days) when unset, hard-capped at
  `maxWorkerTokenTTL` (90 days).

**Token verification.** `internal/auth/localjwt/issuer.go`'s
`Provider.Authenticate` (used as the plain MCP `provider` everywhere,
including for the worker-token mint route itself) calls `Verify`, which
checks HMAC signature, `iss`, and rejects on `time.Now().Unix() >
c.ExpiresAt` (issuer.go:112-135) — i.e. **an expired token already fails
standard authentication** before any handler runs. `CheckAudience` is then
applied by `Provider.Authenticate` using the deployment's
`OAUTH_JWT_AUDIENCE`/`OAUTH_JWT_AUDIENCE_REQUIRED` config, which is
independent of and looser than the `mcp-worker-ro` value — it does not by
itself guarantee the presented token is a worker token. `auth.Identity`
(internal/auth, `Identity` struct) carries `Scopes`, `TelegramID`,
`Subject`, but **not** `Audience` or `ExpiresAt` — those live only in
`localjwt.Claims`, which is not exposed past `Provider.Authenticate`.

**Canary runtime.** `cmd/canary/main.go` is deliberately dependency-free
from `internal/...` ("black-box HTTP client" per its package doc). It reads
`CANARY_BEARER_TOKEN` once at process start (`loadConfig`, main.go:60-63),
already parses the token's `exp` claim locally without verification
(`tokenExpiry`, main.go:163-181, used only for the
`mctl_telegram_canary_token_expires_in_seconds` gauge shipped for this same
issue), and runs to completion in a single `run()` call with no persistent
state or retry loop. It never mints or renews anything; token lifecycle is
entirely external to it today.

**Deployment.** `deploy/canary/cronjob.yaml` runs the canary every 2
minutes (currently `suspend: true` for an unrelated reason) with
`CANARY_BEARER_TOKEN` sourced from `secretKeyRef: mctl-telegram-canary /
bearer_token`. The pod spec sets no `serviceAccountName`, so it runs as
`default` in `labs` with no RBAC grants — it cannot read or write any
Secret today. There is no `ServiceAccount`/`Role`/`RoleBinding` manifest for
the canary in this repo yet.

**Already shipped (out of scope here, described for completeness).** The
`mctl_telegram_canary_token_expires_in_seconds` gauge (main.go:139-183),
the `MctlTelegramCanaryTokenExpiring` alert
(`deploy/alerts/canary.rules.yaml`), and the runbook mitigation section
(`docs/runbooks/canary.md`) are already merged and explicitly say "the
canary cannot renew itself yet; that is mctl-telegram#421" — confirming
this proposal is the remaining half of the issue.

## Proposed solution

### 1. `POST /api/mcp/worker-token/renew` (`internal/workertoken`)

A new handler in the same package, `NewRenewHandler(secret []byte, issuer
string)`, mounted in `cmd/server/main.go` next to the existing mint route,
behind the **same plain MCP `provider`** but gated differently: instead of
requiring `admin:users`, it re-parses the raw bearer token from the
`Authorization` header itself (mirroring the redundant-but-necessary
pattern `cmd/canary`'s own `tokenExpiry` already uses, except here it goes
through `localjwt.Verify` for a checked, not just decoded, read) to recover
the full `localjwt.Claims`, because `auth.Identity` does not carry
`Audience` or `ExpiresAt`. Concretely:

1. `auth.Middleware` has already run `Provider.Authenticate` → `Verify` →
   `CheckAudience` (using deployment-wide `OAUTH_JWT_AUDIENCE` config) and
   rejected expired/malformed tokens with 401. The handler still needs the
   *specific* `mcp-worker-ro` audience, which the generic middleware policy
   does not guarantee (`OAUTH_JWT_AUDIENCE` defaults to `""`, i.e.
   disabled).
2. The handler extracts the bearer token from `Authorization` again,
   calls `localjwt.Verify(tok, secret, issuer)` a second time (cheap, HMAC
   only) to get `Claims` with `Audience` populated, and checks `slices.Contains(claims.Audience,
   "mcp-worker-ro")`. Reject with 403 if absent — this is the
   privilege-relevant check the issue calls out ("аud не mcp-worker-ro").
3. Validate every scope in `claims.Scopes` is still in
   `allowedReadOnlyScopes` (defense in depth against a future signing-key
   compromise or bug upstream; today it is unreachable because only this
   package mints `mcp-worker-ro` tokens).
4. Mint a new token with **identical** `Subject`, `TelegramID`, `Scopes`,
   `Audience` and a fresh TTL computed exactly like the mint path
   (`defaultWorkerTokenTTL`, optionally shortened via the same
   `ttl_hours` request field, capped at `maxWorkerTokenTTL` — no privilege
   or lifetime escalation beyond what the mint endpoint already allows for
   this same subject).
5. Log `slog.Info("worker token renewed", "subject", claims.Subject,
   "target_tg_id", claims.TelegramID, "scopes", claims.Scopes, "ttl", ttl)`
   — same shape as the mint log, no token value logged, nothing new needed
   in `internal/audit/redact.go` since neither handler ever puts the token
   string into a log field.

No new `auth.Provider` is introduced, matching `workertoken.NewHandler`'s
existing doc-comment rationale for reusing the plain `/mcp` provider rather
than adding a dedicated one.

### 2. Canary renewal logic (`cmd/canary`)

Add to `cmd/canary/main.go`:
- `CANARY_TOKEN_RENEW_THRESHOLD` config (default `defaultWorkerTokenTTL / 3`
  = 10 days, parsed the same way `CANARY_TIMEOUT` is), and a `renewToken`
  step that runs at the top of `run()`, right after the existing
  `tokenExpiry` gauge computation, and only if `time.Until(exp) <
  threshold`.
- `renewToken` POSTs to `cfg.baseURL + "/api/mcp/worker-token/renew"` with
  the current `CANARY_BEARER_TOKEN` as the bearer, no body, same
  `client.Do` / `context.WithTimeout(ctx, cfg.timeout)` pattern already
  used for every other step. On success it gets back the same
  `workerTokenResponse{worker_token, expires_at}` shape the mint endpoint
  already returns.
- On success, write the new token into the `bearer_token` key of the
  `mctl-telegram-canary` Secret via a direct Kubernetes API call: `PATCH
  https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT/api/v1/namespaces/labs/secrets/mctl-telegram-canary`
  with `Content-Type: application/strategic-merge-patch+json`, body
  `{"data":{"bearer_token":"<base64 of new token>"}}`, bearer-authenticated
  with the token at
  `/var/run/secrets/kubernetes.io/serviceaccount/token` and TLS verified
  against `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt` — both
  auto-mounted into the pod once `serviceAccountName` is set, no new
  dependency. This deliberately does **not** add `k8s.io/client-go`: the
  canary's own package doc already commits to being a minimal black-box
  HTTP client with no `internal/` imports, and one PATCH call does not
  justify the dependency weight and update burden `client-go` would bring
  to a 250-line binary. Reuse the existing `net/http` `client`.
- On any failure in this step (renew call, or Secret patch), log the error,
  increment `met.stepFailures.WithLabelValues("token_renew")`, and continue
  the run using the still-valid `cfg.bearerToken` already in memory —
  renewal failure must never abort a probe run that would otherwise
  succeed. This mirrors the existing "abort only when truly blocking"
  philosophy in `run()` (only `oauth_metadata` failure aborts early today).
- The in-memory `cfg.bearerToken` is updated to the renewed token for the
  remainder of *this* run so subsequent steps (`mcp_init`,
  `list_dialogs`) use the fresh token rather than racing its own
  expiry mid-run; the next CronJob invocation reads the Secret fresh via
  `secretKeyRef` as it always has.

### 3. RBAC and Secret write access (`deploy/canary/`)

Add `deploy/canary/serviceaccount.yaml` (new file) with:
- `ServiceAccount mctl-telegram-canary` in `labs`.
- `Role mctl-telegram-canary-secret` in `labs`, granting `get`, `patch` on
  `resources: ["secrets"], resourceNames:
  ["mctl-telegram-canary"]` only — no wildcard, no `list`/`watch`/`delete`,
  no other resource types.
- `RoleBinding` binding the Role to the ServiceAccount.

Update `deploy/canary/cronjob.yaml` to set
`spec.jobTemplate.spec.template.spec.serviceAccountName:
mctl-telegram-canary`.

### Why this shape

- **No escalation path.** The renew handler cannot change `sub`,
  `tg_id`, `scopes`, or `aud` — every field is copied from the verified
  claims of the token the caller already possesses. It literally cannot
  mint a token for a different Telegram identity or a wider scope, which
  is the exact property the issue demands ("subject и scopes берутся из
  предъявленного токена... никакой эскалации").
- **Renewal window, not indefinite life.** Because renewal requires a
  currently-valid token and every renewal is itself bounded by
  `maxWorkerTokenTTL`, a compromised or leaked worker token still dies
  within 90 days of its *original* mint if nobody is actively running the
  canary with it — there is no mechanism here to mint a token whose chain
  of renewals traces back further than a real, currently-valid credential.
- **Narrow RBAC.** Scoping the `Role` to a single named Secret and two
  verbs keeps the blast radius of a compromised canary pod to "can read/
  overwrite its own bearer token," not "can read arbitrary Secrets in
  `labs`."
- **Fail-open on renewal, fail-closed on the endpoint.** The canary
  degrades to "still uses the old, still-valid token" if the renew call or
  RBAC isn't wired up yet, so the endpoint and the CronJob/RBAC change can
  ship as two independent deploys (endpoint first is safe with no canary
  changes at all; canary changes are safe to deploy before RBAC exists,
  they'll just log+metric a failure every run until the Role lands).

## Alternatives

1. **Full OAuth refresh-token grant for worker tokens.** Rejected per the
   issue's own reasoning: `POST /api/mcp/worker-token` is not the OAuth
   server, worker tokens have no refresh token today, and building
   rotation + reuse detection for a cron job that can legitimately
   double-run (`concurrencyPolicy: Forbid` reduces but does not eliminate
   overlap risk with `activeDeadlineSeconds: 120` and a 2-minute schedule)
   would trade a scheduled, well-understood failure mode for a
   probabilistic, hard-to-debug one.
2. **Grant the canary `admin:users` and let it call the existing mint
   endpoint for itself.** Rejected — this is strictly worse than the
   status quo: it would let a compromised canary pod mint a token for
   *any* `telegram_id`, not just renew its own. The issue explicitly flags
   this as the reason `NewAgentTokenHandler` keeps that capability out of
   reach of agent workers, and the same reasoning applies here.
3. **Raise `maxWorkerTokenTTL`/mint at the 90-day ceiling and rely on the
   alert alone.** Rejected — the issue calls this out directly as
   "отодвигает отказ, а не устраняет его": it delays the scheduled outage
   without removing it and quietly spends down the safety margin #412
   intentionally introduced. Also does nothing for anyone who mints a
   fresh canary token at the 30-day default, which remains the common
   case.
4. **Have the canary write the renewed token to a shared volume /
   ConfigMap instead of the Secret directly, with a separate reconciler
   syncing it into the Secret.** Rejected as unnecessary indirection: the
   canary already has (once RBAC is added) narrowly-scoped write access to
   exactly the one Secret key it needs; introducing an intermediate
   resource and a second component to keep in sync adds moving parts
   without reducing the RBAC surface (the intermediate resource still
   needs write access from the pod).

## Platform impact

- **Migrations:** none (no DB schema change; `internal/workertoken` has no
  persistent storage).
- **Backward compatibility:** `POST /api/mcp/worker-token` (mint) is
  unchanged. The new `/renew` route is additive. Existing
  `CANARY_BEARER_TOKEN` values keep working unmodified until their natural
  expiry; the canary's renewal logic is purely additive to `run()` and only
  activates near expiry, so normal runs are unaffected.
- **Resource impact:** one new `ServiceAccount`/`Role`/`RoleBinding` in
  `labs` (negligible). Two additional short-lived outbound HTTP calls from
  the canary pod roughly once every ~20 days (10-day threshold against a
  30-day TTL), not every run — negligible against the existing
  `activeDeadlineSeconds: 120` budget and the `10m`/`32Mi` request
  envelope; no resource limit change proposed.
- **Risks + mitigations:**
  - *Risk:* renew endpoint becomes a second mint surface if the audience
    check is implemented loosely. *Mitigation:* explicit
    `mcp-worker-ro`-membership check against the freshly-verified `Claims`,
    not against the looser deployment-wide `OAUTH_JWT_AUDIENCE` policy;
    covered by a unit test asserting a non-worker token (e.g. an
    interactive user session JWT with no `mcp-worker-ro` audience) is
    rejected.
  - *Risk:* Secret write races between two canary runs (should not happen
    under `concurrencyPolicy: Forbid`, but `activeDeadlineSeconds: 120`
    plus scheduler jitter is not an absolute guarantee). *Mitigation:*
    Kubernetes Secret PATCH is a single atomic write of the whole
    `bearer_token` key; worst case is "last writer wins" with both writers
    holding a validly-renewed token, not corruption.
  - *Risk:* RBAC manifest drifts from actual Secret name/namespace.
    *Mitigation:* `resourceNames` pins the exact Secret name; a
    misconfigured Role fails closed (403 from the API server), which the
    canary already treats as a non-fatal, alerted, logged failure.
  - *Risk:* this ships while the CronJob is `suspend: true`, so the
    renewal path gets no production exercise until someone unsuspends it.
    *Mitigation:* explicitly flagged in tasks.md as a rollout step — verify
    renewal manually (e.g. a one-off `kubectl create job --from=cronjob`)
    before relying on it, independent of whether/when the suspend flag is
    lifted for the unrelated SendCode investigation.
