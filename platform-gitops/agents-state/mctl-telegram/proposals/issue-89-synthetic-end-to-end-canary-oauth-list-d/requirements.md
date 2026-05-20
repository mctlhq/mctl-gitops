# Synthetic end-to-end canary: OAuth + list_dialogs probe

## Context

`/healthz` in `cmd/server/main.go` (line 313) only confirms that the HTTP
process is alive; it exercises none of the real execution paths. In practice
three classes of failure have gone undetected: an expired Telegram OIDC client
secret, a FLOOD_WAIT on the canary Telegram account, and DB pool exhaustion.
All three would have been caught immediately by a probe that walks the same path
a real user walks: OAuth metadata discovery, bearer-token authentication, and a
read-only MTProto call via the session pool.

For Beta the team wants a synthetic canary binary (`cmd/canary`) that runs on a
known dedicated Telegram account, emits Prometheus metrics, is scheduled as a
Kubernetes CronJob every two minutes, and triggers a PagerDuty-level alert when
it fails for five consecutive minutes. The canary must never write to any
Telegram peer; it is explicitly limited to the `telegram:dialogs:read` and
`telegram:messages:read` scopes. FLOOD_WAIT events on the canary account must
produce a "degraded" signal rather than a tight retry loop.

## User stories

- AS a platform operator I WANT a canary probe to run every two minutes against
  the live server SO THAT silent failures in OAuth, the session pool, or MTProto
  are detected before users report them.
- AS a platform operator I WANT the canary to emit Prometheus metrics and fire a
  PrometheusRule alert SO THAT on-call receives a PagerDuty page within five
  minutes of a sustained failure.
- AS an on-call engineer I WANT canary step-level failure counters
  (`mctl_telegram_canary_step_failure_total{step=}`) SO THAT I can tell at a
  glance whether the failure is in OAuth discovery, `list_dialogs`, or
  `get_unread_messages`.
- AS a security reviewer I WANT the canary bearer token scoped to read-only
  scopes (`telegram:dialogs:read,telegram:messages:read`) with no send scopes SO
  THAT a compromised token cannot write to any Telegram peer.

## Acceptance criteria (EARS)

- WHEN the canary runs and all three probes succeed THEN THE SYSTEM SHALL set
  `mctl_telegram_canary_success` to 1 and push/expose the metric within the
  configured timeout.
- WHEN any probe returns an error or times out THEN THE SYSTEM SHALL set
  `mctl_telegram_canary_success` to 0, increment the corresponding
  `mctl_telegram_canary_step_failure_total{step=<name>}` counter, and exit with
  status 1.
- WHEN the OAuth metadata probe (`GET /.well-known/oauth-authorization-server`)
  returns a non-200 response or a response body missing the required JSON fields
  (`issuer`, `authorization_endpoint`, `token_endpoint`) THEN THE SYSTEM SHALL
  record step failure `step=oauth_metadata` and abort further probes.
- WHEN the `list_dialogs` MCP probe returns an MCP error result (IsError=true in
  the response body) THEN THE SYSTEM SHALL record step failure
  `step=list_dialogs` without retrying.
- WHEN the `list_dialogs` MCP probe response indicates a Telegram FLOOD_WAIT
  condition (response body contains "FLOOD_WAIT" or the step took longer than
  `CANARY_TIMEOUT`) THEN THE SYSTEM SHALL record step failure
  `step=list_dialogs`, set success to 0, and report degraded status; it SHALL
  NOT re-invoke the MCP endpoint in a tight loop.
- WHEN the optional `get_unread_messages` probe is enabled (via
  `CANARY_PROBE_UNREAD=true`) and it fails THEN THE SYSTEM SHALL record step
  failure `step=get_unread_messages` and set success to 0.
- WHILE `CANARY_BEARER_TOKEN`, `CANARY_BASE_URL`, or `CANARY_TG_USER_ID` are
  absent from the environment THEN THE SYSTEM SHALL log a clear error and exit
  with status 1 before making any network call.
- WHEN `PUSHGATEWAY_URL` is set THEN THE SYSTEM SHALL push all three metric
  families to the Pushgateway using job label `mctl_telegram_canary` after every
  run (success or failure).
- WHEN `PUSHGATEWAY_URL` is not set THEN THE SYSTEM SHALL serve metrics on
  `CANARY_METRICS_ADDR` (default `:9090`) at `/metrics` and block until
  terminated (daemon mode for local testing).
- WHEN the CronJob manifest runs on the cluster THEN THE SYSTEM SHALL complete
  each pod within two minutes so successive CronJob instances do not overlap
  under the default `concurrencyPolicy: Forbid`.
- IF `mctl_telegram_canary_success` has been 0 for all observations over the
  last 10 minutes THEN THE PrometheusRule SHALL fire the
  `MctlTelegramCanaryFailing` alert at severity=critical after a 5-minute
  `for:` window.
- WHILE the canary token is in use THEN THE SYSTEM SHALL NOT call any MCP tool
  that has `WithDestructiveHintAnnotation(true)` — specifically `send_message`,
  `pin_message`, `disconnect_telegram_account`, `delete_telegram_account`,
  `revoke_telegram_session`, and `set_telegram_access`.

## Out of scope

- The canary does not implement its own OAuth authorization flow; it uses a
  pre-issued bearer token (`CANARY_BEARER_TOKEN`) injected via Kubernetes Secret.
- The canary does not test the browser-based connect flow (`/telegram/connect`).
- The canary does not test the Local Bridge (`/bridge`) path.
- PrometheusRule integration with PagerDuty routing rules (that is owned by the
  mctl-gitops alertmanager configuration, not this repo).
- Horizontal scale-out of the canary; one pod per CronJob firing is sufficient.
- Any write-path (send, pin) probe — the issue explicitly prohibits write calls.

## Open questions

1. **Pushgateway vs. pull scrape for CronJob**: The issue lists both options.
   This proposal defaults to Pushgateway push (the only viable model for a
   short-lived CronJob pod), with `CANARY_METRICS_ADDR` as a daemon-mode
   fallback for local testing. If the cluster has no Pushgateway, a different
   scheduling primitive (Deployment with a sleep loop) would be required — not
   addressed here.
2. **Issue #86 PrometheusRule file**: The alert depends on a file introduced in
   #86 (`deploy/alerts/mctl-telegram.rules.yaml`). Because #86 is not yet merged,
   this proposal adds the canary alert as a standalone file
   (`deploy/alerts/canary.rules.yaml`) that the implementer can consolidate into
   #86's file once that lands.
3. **MCP StreamableHTTP protocol details**: The MCP path (default `/mcp`) uses
   `mark3labs/mcp-go` StreamableHTTP. The canary must POST a JSON-RPC 2.0
   `tools/call` request. The exact wire format is not documented in the issue;
   this proposal derives it from the `mcp-go` library's HTTP handler convention
   (see design.md). If the library's wire format changes, the canary probe body
   will need updating.
4. **Canary token provisioning on cluster**: The issue does not specify which
   Kubernetes namespace or Vault path holds `CANARY_BEARER_TOKEN`. This proposal
   documents the required Secret shape but does not prescribe the secrets-manager
   path — that is a gitops concern.
