# Design: incident-4331f490

## Confidence: LOW

## Diagnosis
Both session-borrow burn-rate alerts (this slow-burn ticket and the paired
fast-burn incident fbca040c-3a52-4b74-b27c-fc6d74fc130c) fired at the same
instant, 2026-09-28T06:03:43Z, off the same underlying SLI:
mctl_telegram:session_borrow_errors:ratio_rate6h /
mctl_telegram:session_borrow_errors:ratio_rate1h, built from
mctl_sessions_borrow_total{result="error"} (Pool.Borrow() failures,
deliberately excluding expected TTL expirations). No log line in any sampled
Loki window names "borrow", "session", or "pool", and no ERROR-level lines
appear at all, which fits: this SLI is metric-only telemetry from
Pool.Borrow(), not something the app logs as text, so its absence from Loki
is not evidence against a real failure.

The strongest concrete lead is a known, already-documented risk sitting in
this exact service's own deployed configuration
(platform-gitops/services/labs/mctl-telegram/values.yaml, canary CronJob
comment block, "extraObjects" section): the synthetic canary was supposed to
be moved off the human operator's Telegram identity (210408407) onto a
dedicated identity (924671154) specifically because "sharing one MTProto
user across prod+preview causes AUTH_KEY_DUPLICATED" — and the same comment
admits the out-of-band Secret (mctl-telegram-canary, not tracked in git) was
never actually reminted: "both databases confirm 210408407 is active on
stable and preview simultaneously." Operator 210408407 is also
TG_LOGIN_ADMINS, i.e. a real, regularly-used identity. AUTH_KEY_DUPLICATED
on a shared MTProto auth key would surface as Pool.Borrow() errors for that
identity's pooled session in production (the job this SLO's recording rules
scrape is job=labs-mctl-telegram only, per the VMServiceScrape selector
noted in mctl-telegram-slo.yaml — preview is never scraped into this
series), which is exactly the numerator these two alerts watch. The SLO
recording-rule file also notes this service is low-traffic enough that "a
couple of errors can cross a burn threshold" in a 1h/6h window, consistent
with a short, self-contained burst rather than an ongoing outage (both
alerts fired once, occurrence_count=1, and no further evidence of
elevated errors appears in the ~1h of logs available after the alert fired).

This cannot be confirmed with the tools available here: there is no
Prometheus/VictoriaMetrics query tool in this run, and the canary's
tg_user_id/bearer_token Secret is out-of-band (Vault/kubectl-managed, not in
git), so its current value cannot be read from this checkout either.
Confidence is therefore LOW — this is the best available lead, not a
verified root cause.

## Proposed Fix
Since the candidate root cause (a possibly-still-misrouted out-of-band
Secret) has no git-tracked field to change, and rotating a live Secret is
outside what an unattended PR should do, the safe, git-actionable action is
to record the diagnosis and the exact manual remediation as a runbook so a
human (or the operator flow already described in values.yaml) can act on it
without re-deriving this investigation, and so a recurrence auto-links back
to this finding.

Add a new file:
`platform-gitops/docs/runbooks/mctl-telegram-session-borrow-alerts.md`

Contents: the diagnosis above, plus the concrete manual remediation step:
verify the `mctl-telegram-canary` Secret in namespace `labs` — keys
`tg_user_id` / `bearer_token` — actually holds identity `924671154` per the
decision already recorded in
`platform-gitops/services/labs/mctl-telegram/values.yaml`; if it still holds
`210408407`, remint it via the self-renewal flow described in that same
values.yaml comment block (mctlhq/mctl-telegram#421 / #412,
POST /api/mcp/worker-token), then confirm no further AUTH_KEY_DUPLICATED /
Pool.Borrow() errors appear in `mctl_telegram_client_errors_total` or the
session-borrow SLI over the following 1h/6h windows.

## Scope
Minimal: one new runbook file, no changes to deployed manifests, alert
rules, or application code. This does not silence or alter the alert
thresholds — it only records the diagnosis path for whoever handles the
manual remediation, since the candidate fix is outside GitOps' reach.
