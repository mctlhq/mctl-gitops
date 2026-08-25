# Tasks: issue-421-bounded-ttl

- [ ] 1. Add `POST /api/mcp/worker-token/renew` handler in
      `internal/workertoken` (new `NewRenewHandler(secret []byte, issuer
      string) http.HandlerFunc`, e.g. in a new `renewhandler.go` alongside
      `tokenhandler.go`): re-verify the presented bearer token via
      `localjwt.Verify`, require `mcp-worker-ro` in its `Audience`, require
      every claimed scope to be in `allowedReadOnlyScopes`, mint a new token
      with identical `Subject`/`TelegramID`/`Scopes`/`Audience` and
      `defaultWorkerTokenTTL`-or-capped-`ttl_hours` TTL, return the same
      `workerTokenResponse` shape as the mint handler. — DoD: handler
      compiles, is unit-testable in isolation (no HTTP server needed), never
      logs the raw token value.
- [ ] 2. Mount the new route in `cmd/server/main.go` next to the existing
      `/api/mcp/worker-token` registration (~line 454-457), behind the same
      `auth.Middleware(provider, true, m, resourceMeta)`, gated on
      `cfg.OAUTHJWTSecret != ""` like its neighbor. (depends on 1) — DoD:
      `go build ./...` succeeds; route reachable in an integration-style
      test hitting the chi mux.
- [ ] 3. Unit tests for the renew handler in
      `internal/workertoken/renewhandler_test.go`, modeled on
      `tokenhandler_test.go`'s `adminRequest`/`decodeJWTPayload` helpers:
      valid worker token renews with same sub/scopes/aud and a fresh exp;
      expired token is rejected (via the standard auth chain, i.e. test
      through `auth.Middleware` or replicate `Verify`'s expiry check
      directly); token with `aud` not containing `mcp-worker-ro` is
      rejected 403; token carrying a scope outside
      `allowedReadOnlyScopes` is rejected; `ttl_hours` override is
      clamped to `maxWorkerTokenTTL` same as the mint path. (depends on 1)
      — DoD: `go test ./internal/workertoken/...` green, covers every
      acceptance criterion in requirements.md for the endpoint.
- [ ] 4. Add `CANARY_TOKEN_RENEW_THRESHOLD` to `config`/`loadConfig` in
      `cmd/canary/main.go` (parsed like `CANARY_TIMEOUT`, default
      `defaultWorkerTokenTTL / 3` — canary has no `internal/workertoken`
      import, so hardcode the equivalent `10 * 24 * time.Hour` default
      with a comment cross-referencing the source of truth). — DoD: env
      var documented in the doc comment block the way `CANARY_TIMEOUT` is.
- [ ] 5. Implement `renewToken(ctx, client, cfg) (newToken string, err
      error)` in `cmd/canary/main.go`: POST to
      `cfg.baseURL + "/api/mcp/worker-token/renew"` with
      `Authorization: Bearer <cfg.bearerToken>`, decode
      `workerTokenResponse`. (depends on 2) — DoD: unit test with
      `httptest.Server` covering success and non-200 response.
- [ ] 6. Implement `patchCanarySecret(ctx, client, newToken string) error`
      in `cmd/canary/main.go` (or a small helper file in the same
      package): PATCH the in-cluster Kubernetes API for the
      `mctl-telegram-canary` Secret's `bearer_token` key, using
      `KUBERNETES_SERVICE_HOST`/`_PORT` and the mounted ServiceAccount
      token/CA at their standard `/var/run/secrets/kubernetes.io/...`
      paths; namespace read from the mounted
      `.../serviceaccount/namespace` file rather than hardcoded, so the
      binary stays environment-agnostic. — DoD: unit test with
      `httptest.Server` standing in for the API server verifies the
      correct PATCH path, `strategic-merge-patch+json` content type, and
      base64-encoded `data.bearer_token` body.
- [ ] 7. Wire steps 5-6 into `run()`: after the existing `tokenExpiry`
      gauge computation, if `okExp && time.Until(exp) <
      cfg.tokenRenewThreshold`, call `renewToken` then
      `patchCanarySecret`; on success update `cfg.bearerToken` in memory
      for the rest of this run and log success; on failure log the error
      and `met.stepFailures.WithLabelValues("token_renew").Inc()` without
      aborting the run. (depends on 4, 5, 6) — DoD: `run()`'s existing
      test coverage extended to cover the new branch (threshold not
      crossed = no-op; threshold crossed + renew succeeds = bearerToken
      updated + steps continue with it; threshold crossed + renew fails =
      run continues with old token + failure metric incremented).
- [ ] 8. Add `deploy/canary/serviceaccount.yaml`: `ServiceAccount
      mctl-telegram-canary`, `Role mctl-telegram-canary-secret` (verbs
      `get`, `patch`; resource `secrets`; `resourceNames:
      ["mctl-telegram-canary"]`, namespace `labs`), `RoleBinding` tying
      them together. — DoD: manifest reviewed for least privilege (no
      wildcard resourceNames, no extra verbs).
- [ ] 9. Update `deploy/canary/cronjob.yaml` to set
      `spec.jobTemplate.spec.template.spec.serviceAccountName:
      mctl-telegram-canary`. (depends on 8) — DoD: diff reviewed; `suspend:
      true` left untouched (out of scope, unrelated to this issue).
- [ ] 10. Update `docs/runbooks/canary.md`'s "Token expiring / expired"
      mitigation section to describe the new self-renewal behavior
      (renews automatically under the threshold; manual remint via
      `POST /api/mcp/worker-token` remains the fallback/escalation path
      if `token_renew` step failures keep appearing in
      `mctl_telegram_canary_step_failure_total`). (depends on 7) — DoD:
      runbook no longer says "the canary cannot renew itself yet."
- [ ] 11. Manual rollout verification against `labs`: with the CronJob
      still `suspend: true` for its unrelated reason, trigger one ad hoc
      run (`kubectl -n labs create job --from=cronjob/mctl-telegram-canary
      mctl-telegram-canary-manual-verify`) with a short-lived test worker
      token (mint one with a `ttl_hours` just under the renewal threshold)
      to confirm renewal + Secret patch actually work end-to-end against
      the real API server and RBAC, before relying on the 2-minute
      schedule to eventually exercise it. (depends on 9, 10) — DoD:
      confirmed via pod logs that `token_renew` succeeded and the Secret's
      `bearer_token` changed.

## Tests

- [ ] T1. `internal/workertoken/renewhandler_test.go`: valid worker token
      renews to a new token with identical sub/tg_id/scopes/aud and a
      later `exp`.
- [ ] T2. `internal/workertoken/renewhandler_test.go`: token with `aud`
      not containing `mcp-worker-ro` (e.g. no aud, or `aud=["bridge"]`) is
      rejected 403, no token minted.
- [ ] T3. `internal/workertoken/renewhandler_test.go`: expired token is
      rejected by the auth chain before the handler body runs (401).
- [ ] T4. `internal/workertoken/renewhandler_test.go`: `ttl_hours`
      requested above `maxWorkerTokenTTL` is clamped, matching
      `tokenhandler_test.go`'s existing clamp test for mint.
- [ ] T5. `cmd/canary`: `renewToken` against an `httptest.Server` returning
      200 with a `workerTokenResponse` body succeeds; returning non-200
      returns an error.
- [ ] T6. `cmd/canary`: `patchCanarySecret` against an `httptest.Server`
      sends `PATCH /api/v1/namespaces/<ns>/secrets/mctl-telegram-canary`
      with `Content-Type: application/strategic-merge-patch+json` and
      `{"data":{"bearer_token":"<base64>"}}`.
- [ ] T7. `cmd/canary`: `run()` with a token just under the renewal
      threshold and a stub renew server updates `cfg.bearerToken` and
      subsequent probe steps in the same run use the new value.
- [ ] T8. `cmd/canary`: `run()` with a renewal failure (stub server
      returns 500) still completes the probe using the original token and
      increments `mctl_telegram_canary_step_failure_total{step="token_renew"}`.
- [ ] T9. `cmd/canary`: `run()` with a token well above the threshold
      never calls the renew endpoint at all (no unnecessary network call
      every run).

## Rollback

- The renew endpoint (tasks 1-3) is purely additive; if it misbehaves,
  remove its route registration in `cmd/server/main.go` (task 2) or revert
  that commit — `POST /api/mcp/worker-token` (mint) and every other route
  are untouched, so this is a single, low-risk revert with no migration to
  undo.
- The canary-side renewal (tasks 4-7) degrades safely by construction: on
  any failure it logs, increments a metric, and keeps using the existing
  token. If it turns out to be actively harmful (e.g. hammering the renew
  endpoint, or corrupting the Secret), revert the `cmd/canary` commit and
  re-deploy the previous image tag in `deploy/canary/cronjob.yaml`
  (`image: ghcr.io/mctlhq/mctl-telegram:<previous-tag>`) — the CronJob
  keeps working exactly as it does today, reading a manually-maintained
  Secret, until the next scheduled manual remint.
- The RBAC change (tasks 8-9) can be reverted independently by removing
  `serviceAccountName` from the CronJob spec (or deleting
  `serviceaccount.yaml`); the pod falls back to `default` with no Secret
  access, which only disables renewal (fail-open per the design), it does
  not break the probe itself.
- No database migration, no data backfill, nothing to roll back at the
  storage layer.
