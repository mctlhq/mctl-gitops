# Design: incident-e22f370d

## Confidence: LOW

## Diagnosis
The `MctlTelegramSessionBorrowSlowBurn` alert is a multi-window burn-rate
alert on mctl-telegram's session-borrow latency SLO, firing at 6x the normal
burn rate sustained over a 6h window. No skill matched this ticket because
none of the existing skills cover Telegram MTProto client-pool behavior — it
fell straight to escalation (`escalated`, analysis: "no skill matched").

The available evidence (15 most recent log lines from `labs/mctl-telegram`,
covering roughly the last 7 minutes — the pod logs at high volume so this is
a small slice of the 6h alert window) shows no errors: MCP tool calls
(`get_unread_messages`, `list_dialogs`, `get_messages`) all returned
`"status":"ok"`, and the canary CronJob's synthetic probe completed
successfully (`"canary run complete","ok":true,"duration_seconds":1.195`). The
one notable line is:
```
{"msg":"idle telegram client, closing","user_id":9980,"idle":620147626715}
```
This shows the service evicting an MTProto client for user 9980 after an idle
period (~620s if the field is nanoseconds-as-int64, i.e. ~10.3 minutes). If
idle-client eviction is aggressive relative to real request spacing, borrowing
a session after eviction requires re-establishing the MTProto connection
(and possibly re-auth), which is markedly slower than reusing a warm client —
consistent with a sustained, moderate (6x) burn rather than a hard outage.
This is a plausible mechanism, but the fetched log window did not capture the
alert's own multi-hour trend, so the link between "idle client closing" and
the specific burn-rate breach is inferred, not confirmed. Hence LOW confidence.

Reviewed `platform-gitops/services/labs/mctl-telegram/values.yaml`: it exposes
no session-pool-size or idle-timeout tuning as an environment variable today.
Whatever idle-eviction policy exists (that produced the log line above) is
therefore internal to the mctl-telegram binary, not a gitops value — so a fix
cannot be a values.yaml-only tweak; it needs a knob added or changed in the
mctl-telegram Go service itself. This is why this proposal targets the
`mctl-telegram` service repo rather than the default `mctl-gitops`.

## Proposed Fix
In the `mctlhq/mctl-telegram` repo, locate the MTProto client-pool /
idle-eviction logic that produced the `"idle telegram client, closing"` log
line and:
1. Confirm whether the idle-close timeout is currently hardcoded.
2. If hardcoded, make it configurable via a new environment variable (e.g.
   `TELEGRAM_CLIENT_IDLE_TIMEOUT`), with a default equal to the current
   hardcoded value so behavior does not change until the value is tuned.
3. Once configurable, add the new env var under `env:` in
   `platform-gitops/services/labs/mctl-telegram/values.yaml`, set to a value
   large enough to avoid evicting clients between normal request intervals
   for this tenant's usage pattern, but not so large that idle MTProto
   connections are held indefinitely.

## Scope
Minimal: touch only the idle-eviction timeout/config path in mctl-telegram
and, if a new env var is introduced, the corresponding line in
`platform-gitops/services/labs/mctl-telegram/values.yaml`. Do not change pool
sizing, retry logic, or unrelated session-lifecycle code (TTL exemptions,
revocation, etc. are deliberately tuned per existing comments in values.yaml
and are unrelated to this alert).
