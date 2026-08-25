# Canary self-renewal for bounded worker tokens

## Context

`cmd/canary` authenticates against production `tg.mctl.ai` with a single
static `CANARY_BEARER_TOKEN` (`cmd/canary/main.go:60`, read once from the
`mctl-telegram-canary` Secret via `secretKeyRef` in
`deploy/canary/cronjob.yaml`). Since #412 introduced `defaultWorkerTokenTTL`
(30 days) and `maxWorkerTokenTTL` (90 days) in `internal/workertoken`, every
worker token minted by `POST /api/mcp/worker-token` carries a hard expiry.
That is the correct security posture (bounded credential lifetime instead of
the year-long hand-signed JWT it replaced), but it turns "canary token
expires" from a hypothetical into a calendar event: the current production
token expires 2026-09-23, and on that date the canary goes red and stays red
until a human with `admin:users` manually remints it and edits the Secret.

The remaining-lifetime metric and alert this issue also asked for
(`mctl_telegram_canary_token_expires_in_seconds`,
`MctlTelegramCanaryTokenExpiring` in `deploy/alerts/canary.rules.yaml`, and
the matching mitigation section in `docs/runbooks/canary.md`) are already
shipped — they explicitly cite this issue as the reason self-renewal doesn't
exist yet. This proposal covers exactly that remaining gap: giving the
canary a way to refresh its own credential before it expires, without ever
being able to mint a token for a different identity or a broader scope than
the one it was deployed with.

## User stories

- AS the mctl-telegram on-call engineer I WANT the canary to renew its own
  bearer token before expiry SO THAT token expiration stops being a
  scheduled outage that requires manual intervention on a specific calendar
  date.
- AS a platform operator I WANT the canary's renewal path to be incapable of
  escalating privilege or changing identity SO THAT giving the canary
  Secret-write RBAC does not reopen the "agent worker mints its own
  replacement" risk that `NewAgentTokenHandler` deliberately avoids.
- AS an on-call engineer reading `mctl_telegram_canary_token_expires_in_seconds`
  I WANT the metric to keep working as a safety net when self-renewal fails
  SO THAT a broken renewal path still surfaces as an alert instead of a
  silent, permanent expiry.

## Acceptance criteria (EARS)

- WHEN a request is made to `POST /api/mcp/worker-token/renew` with a valid,
  unexpired bearer token whose audience contains `mcp-worker-ro` THE SYSTEM
  SHALL mint and return a new token with the same `sub`, `tg_id`, and
  `scopes` as the presented token, and an `aud` equal to the presented
  token's `aud`.
- WHEN minting the renewed token THE SYSTEM SHALL apply the same TTL rules as
  `POST /api/mcp/worker-token` (`defaultWorkerTokenTTL` when no override is
  requested, capped at `maxWorkerTokenTTL`).
- IF the presented token is expired THEN THE SYSTEM SHALL reject the renewal
  request with 401 (this is already the behavior of `localjwt.Verify` /
  `auth.Middleware`, since an expired token fails standard authentication
  before the handler runs).
- IF the presented token's audience does not contain `mcp-worker-ro` THEN THE
  SYSTEM SHALL reject the renewal request with 403 and SHALL NOT mint a
  token.
- IF the presented token carries a scope outside `allowedReadOnlyScopes`
  (should be unreachable given how tokens are minted today, but not
  provable from the token alone) THEN THE SYSTEM SHALL reject the renewal
  request rather than propagate an unvalidated scope into the new token.
- WHEN a renewal succeeds THE SYSTEM SHALL log it at the same level of detail
  as a mint (`admin_user_id` is not applicable here; log `subject`,
  `target_tg_id`, `scopes`, `ttl` instead) and SHALL NOT log the token value
  itself, consistent with `internal/workertoken.NewHandler`'s existing mint
  logging and `internal/audit/redact.go`.
- WHEN the canary process starts a run THE SYSTEM SHALL compute the
  remaining lifetime of `CANARY_BEARER_TOKEN` using the existing
  `tokenExpiry` helper (`cmd/canary/main.go`).
- IF the remaining lifetime is below a configurable renewal threshold
  (default: one third of `defaultWorkerTokenTTL`, i.e. 10 days) THEN THE
  SYSTEM SHALL call `POST /api/mcp/worker-token/renew` before running the
  probe steps.
- WHEN a renewal call succeeds THE SYSTEM SHALL write the new token into the
  `bearer_token` key of the `mctl-telegram-canary` Secret in the `labs`
  namespace via the Kubernetes API, using the in-cluster ServiceAccount
  credentials mounted into the CronJob pod.
- IF the renewal call fails (HTTP error, network error, or Secret write
  failure) THEN THE SYSTEM SHALL log the failure, increment
  `mctl_telegram_canary_step_failure_total{step="token_renew"}`, and
  continue the run with the existing (still-valid, not-yet-expired) token
  rather than aborting the probe.
- WHILE the CronJob's ServiceAccount lacks `get`/`patch` RBAC on the
  `mctl-telegram-canary` Secret THE SYSTEM SHALL fail the renewal step
  gracefully (log + metric, no crash) exactly like any other renewal
  failure, so this feature can be deployed to the endpoint first and the
  RBAC/write-back second without a hard dependency ordering.
- WHEN the CronJob pod's Secret-write RBAC is in place THE SYSTEM SHALL use
  a `ServiceAccount` scoped to a `Role` permitting only `get` and `patch` on
  the single named Secret `mctl-telegram-canary` in the `labs` namespace
  (no wildcard resource names, no cluster-wide `Role`/`ClusterRole`).
- WHEN a renewed token is written back to the Secret THE SYSTEM SHALL leave
  `tg_user_id` and any other existing Secret keys untouched (patch only
  `bearer_token`).

## Out of scope

- Full OAuth-style refresh tokens, rotation, or reuse detection for worker
  tokens. The issue explicitly rules this out: worker tokens are not issued
  by the OAuth server and have no refresh grant.
- Any change to `POST /api/mcp/worker-token` (the admin mint path) itself.
- Revocation of previously issued worker tokens (tracked separately, see
  #399 referenced in the issue).
- Extending self-renewal to the agent-token or bridge-token mint paths
  (`internal/agentapi`, `internal/bridge`) — this proposal is scoped to
  `internal/workertoken` and `cmd/canary` only.
- Un-suspending the canary CronJob (currently `suspend: true` in
  `deploy/canary/cronjob.yaml` pending an unrelated SendCode-throttling
  investigation). This proposal must not flip that flag; it only needs to
  leave the CronJob in a state where un-suspending it later doesn't
  immediately hit the 2026-09-23 expiry wall.
- Adding a general-purpose Kubernetes client library (`client-go`) as a
  project dependency — see design.md for why a minimal REST call is
  preferred instead.

## Open questions

- Exact renewal threshold fraction ("a third of TTL" per the issue) is
  taken literally: 10 days for a 30-day default TTL. If a future PR changes
  `defaultWorkerTokenTTL`, the threshold should scale with it rather than
  stay a hardcoded 10 days — implemented as `defaultWorkerTokenTTL / 3`
  read from a `CANARY_TOKEN_RENEW_THRESHOLD` env var with that computed
  value as default, so an operator can override it without a code change.
- The issue does not specify whether the CronJob's `activeDeadlineSeconds:
  120` needs to grow to accommodate the extra renew + Secret-patch HTTP
  round trips. Assumption: two additional sub-second HTTP calls fit
  comfortably inside the existing 120s budget; no change proposed unless
  observed otherwise.
- Whether the renewed token should also be echoed back as a Prometheus
  gauge timestamp (e.g. `mctl_telegram_canary_token_renewed_at`) for
  observability of the renewal path itself, separate from the existing
  expiry gauge. Not required by the issue; recorded here as a
  nice-to-have, not included in this proposal's scope. The existing
  `MctlTelegramCanaryTokenExpiring` alert remains the safety net if
  renewal silently stops working.
