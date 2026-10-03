# Re-resolve tenant groups on OAuth refresh instead of freezing them at first login

## Context

mctl-api resolves a GitHub user's authorization groups exactly once, in the
GitHub OAuth callback (`internal/api/oauth_handlers.go:262`,
`groups := o.ResolveGroups(login)`). That slice is carried into the
authorization code (`OAuthServer.IssueCode`), into the first access token and
refresh token (`ExchangeCode`), and then copied forward unchanged on every
rotation: `RefreshAccessToken` re-issues the JWT from the groups the store
hands back (`internal/auth/oauth_server.go`, RefreshStore path and in-memory
path), and `refreshstore.PostgresStore.rotateTx` writes the predecessor row's
`groups` JSONB into the successor row verbatim
(`internal/auth/refreshstore/postgres.go:303-323`). With a 30-day refresh TTL
that rotation slides forward, a connector that stays in use keeps its
first-login groups indefinitely. Only the raw GitHub-token path re-resolves per
request (`internal/auth/oidc.go:560`, `resolveGroups(login, validator, resolver)`).

Two consequences, both observed or latent in production. Access is not granted
when membership is added: on 2026-09-27 a user created tenant `karabu` and is
its owner in `tenants/karabu/values.yaml`, but their live MCP session had been
minted before `karabu` existed, so every tenant call answered "access denied"
and the client reported the account was "not a member of any workspace". Any
"create a tenant, then deploy into it" flow in one session hits this. And
access is not revoked when membership is removed: a user dropped from
`tenants/<t>/values.yaml`, or whose tenant was deleted, keeps the group claim
for as long as the refresh chain lives. The second is a security defect, and it
is the one that decides the fallback policy below.

## User stories

- AS a platform user who has just created or joined a tenant I WANT my existing
  MCP/CLI session to see the new tenant SO THAT I do not have to sign out and
  back in before deploying into it.
- AS a platform operator removing someone from `tenants/<t>/values.yaml` I WANT
  that removal to take effect on a bounded, short timeline SO THAT revocation
  is real and does not depend on the user choosing to re-authenticate.
- AS a platform operator I WANT admin membership (`admins`, from
  `GitHubValidator.IsAdmin`) re-evaluated on exactly the same terms SO THAT
  granting or withdrawing admin rights behaves like any other group change.
- AS an operator during a gitops outage I WANT a resolver failure to degrade
  predictably and visibly SO THAT it neither logs the whole platform out nor
  silently preserves revoked access forever.

## Acceptance criteria (EARS)

- WHEN a refresh-token grant is exchanged at `POST /oauth/token` THE SYSTEM
  SHALL resolve the caller's groups from the configured `TenantResolver` and
  `GitHubValidator.IsAdmin` at that moment, and SHALL issue the access token
  with the freshly resolved groups rather than the groups stored with the
  refresh token.
- WHEN a user has been added to a tenant in gitops and the reader has synced
  that commit THE SYSTEM SHALL include that tenant in the groups claim of the
  next access token issued by a refresh-token grant, with no re-login.
- WHEN a user has been removed from a tenant in gitops and the reader has
  synced that commit THE SYSTEM SHALL omit that tenant from the groups claim of
  the next access token issued by a refresh-token grant.
- WHEN the refresh-token grant is served by the persistent `refreshstore.Store`
  path THE SYSTEM SHALL apply the re-resolution rule, and WHEN it is served by
  the in-memory `refreshTokenStore` fallback THE SYSTEM SHALL apply the same
  rule with the same outcome.
- WHEN groups are resolved on any path THE SYSTEM SHALL derive the `admins`
  group from `GitHubValidator.IsAdmin(login)` at that moment, adding it for a
  login that has become an admin and omitting it for a login that is no longer
  one, regardless of what the stored or claimed groups say.
- WHEN a JWT issued by this server is validated on a request THE SYSTEM SHALL
  build the caller's groups from a resolution no older than the configured
  group-cache TTL (default 30s) rather than from the token's `groups` claim,
  so that a membership change reaches a live session without waiting for the
  access token to expire.
- WHILE no `TenantResolver` is configured THE SYSTEM SHALL keep the stored or
  claimed groups unchanged, so a deployment without a gitops reader behaves
  exactly as it does today.
- IF the tenant resolver returns an error, or reports that its checkout has
  never been synced (`LastSync()` is zero), THEN THE SYSTEM SHALL treat the
  resolution as failed, SHALL NOT interpret it as "the user has no tenants", and
  SHALL log a warning naming the login and the reason.
- WHILE the resolver's checkout exists but its last successful sync is older
  than the staleness-warning threshold (a fixed 15m package constant, not
  configurable) THE SYSTEM SHALL keep using
  the checkout's answer as a *successful* resolution, SHALL log a warning, and
  SHALL expose the sync age as a Prometheus gauge so the condition can be
  alerted on. A stale checkout SHALL NOT, by default, count toward the
  degraded-grace window or trigger fail-closed. Rationale: when the fetch is
  broken because GitHub is down, a removal cannot be pushed to gitops either, so
  failing closed would lock every tenant user out with no security gain. A
  fetch that is broken only on mctl-api's side, such as an expired token or a
  revoked deploy key, is an ops incident, and the gauge alert covers it.
  (reviewer amendment 2026-09-27)
- WHERE an operator sets `OAUTH_GROUPS_MAX_STALENESS` to a positive duration THE
  SYSTEM SHALL additionally treat a checkout older than that as a failed
  resolution (strict mode). The default is unset, which disables strict mode.
  (reviewer amendment 2026-09-27)
- WHILE group resolution has been failing (as defined above) for no longer than the degraded-grace
  window (default: one access-token TTL) THE SYSTEM SHALL fall back to the
  stored or claimed tenant groups, combined with a freshly computed `admins`.
- IF group resolution has been failing for longer than the degraded-grace
  window THEN THE SYSTEM SHALL fail closed by dropping all tenant groups,
  retaining only `admins` as computed by `GitHubValidator.IsAdmin`, so that a
  resolver outage cannot defeat a removal for longer than that window.
- WHILE resolution is failing THE SYSTEM SHALL still complete the refresh-token
  grant and still rotate the refresh token, so the session survives the outage
  and self-heals on the next exchange once the resolver recovers.
- WHEN a refresh token is replayed after rotation THE SYSTEM SHALL continue to
  reject it and revoke its family exactly as today; group re-resolution SHALL
  NOT alter rotation, reuse detection, the grace-window successor derivation,
  or client_id matching.

## Out of scope

- The Dex JWT path (`DexVerifier.Verify`): its groups come from Dex claims, not
  from gitops, and re-resolving them would change which identity provider is
  authoritative.
- Service, surface-relay and usage-writer principals (`staticServiceUser`,
  `surfaceUserFor`, `usageWriterUserFor` in `internal/auth/oidc.go`) — they do
  not carry gitops-derived tenant groups.
- Changing the `refreshstore.Store` interface or the `oauth_refresh_tokens`
  schema to persist re-resolved groups on rotation. Stored groups stay the
  first-login snapshot and are only used as a bounded fallback.
- Access-token revocation. Access tokens remain unrevocable and bounded only by
  `OAUTH_TOKEN_TTL` (ceiling `maxOAuthTokenTTL`, `cmd/api/main.go`).
- Making the gitops sync interval (hardcoded `60*time.Second` at
  `cmd/api/main.go:765`) configurable.
- Changing `gitops.Reader.ListTenants` / `GetTenantsForUser` semantics for other
  callers. Freshness is judged in `internal/auth`, not by editing the reader.

## Open questions

- The issue offers "cap staleness to the 1h access-token TTL" as an
  alternative to resolving at validate time. This proposal resolves at validate
  time behind a 30s memo, because the reported `karabu` symptom is a
  *same-session* failure that a 1h cap would not fix. Reviewers who consider
  per-request resolution too costly for `/mcp` can reduce this to the refresh
  paths only; the acceptance criteria for the issue would still be met.
- Default degraded-grace window is taken as one access-token TTL
  (`AccessTokenTTL`, default 1h), which is the bound the issue names. Whether
  operators want a shorter fixed floor (e.g. 15m) is a judgement call recorded
  here, not blocked on.
- Fail-closed is implemented as "empty tenant groups", not "refuse the refresh".
  Refusing would sign the user out during a gitops outage and re-login would
  fail the same way, so it is strictly worse; recorded in case a reviewer
  disagrees.
- `GetTenantsForUser` returning `(nil, nil)` for a missing checkout
  (`internal/gitops/reader.go:544`) is indistinguishable from a genuine
  "no tenants" answer. This proposal adds a freshness gate in `internal/auth`
  via an optional `LastSync() time.Time` capability check rather than changing
  the reader, to avoid affecting its other callers. Changing the reader to
  return an error for an absent checkout is the cleaner long-term fix and is
  noted as an alternative.
