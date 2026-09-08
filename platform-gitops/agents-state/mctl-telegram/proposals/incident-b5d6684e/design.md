# Design: incident-b5d6684e

## Confidence: LOW

## Diagnosis
MctlTelegramSessionBorrowSlowBurn fires when
mctl_telegram:session_borrow_errors:ratio_rate6h (Pool.Borrow() failures,
excluding expected TTL expirations) exceeds 6.0% over 6h — 6x the 99% session
-borrow-success objective's error budget (see
platform-gitops/infra-components/observability/vm-rules/mctl-telegram-slo.yaml).
No skill matched this ticket because the pipeline has no diagnostic rule for
this specific SLO burn signal.

The available Loki window (last ~50 lines, effectively ~10 minutes of
base-service traffic) shows no error-level log entries and no line mentioning
"borrow" or "pool" — mctl-telegram appears not to log anything at the point a
Pool.Borrow() call returns a non-ok result; only the
mctl_sessions_borrow_total{result} counter is incremented. That makes this
class of alert undiagnosable from logs alone, which is itself worth fixing
regardless of the specific trigger this time.

One concrete, already-documented hazard exists in this tenant's own
values.yaml (labs/mctl-telegram/values.yaml, canary CronJob comment): the
canary's out-of-band Secret (mctl-telegram-canary) was intended to move from
tg_user_id 210408407 to 924671154 on 2026-08-23, but the comment states the
Secret "was never reminted" and that both the stable and preview databases
show 210408407 active simultaneously. Two MTProto sessions sharing one
tg_user_id's auth key across stable+preview is the documented precondition
for AUTH_KEY_DUPLICATED, which would surface as Pool.Borrow() errors for that
identity. However, the canary log lines actually returned in this window show
tg_user_id=924671154 completing successfully (ok:true), so if the Secret is
still misconfigured it is not currently affecting the canary's own probes —
and the canary is only one identity, not the general population the SLO
ratio sums over. This is a plausible contributing lead, not a confirmed root
cause for the current burn.

Given the lack of per-failure log evidence and the inability to query the
underlying mctl_sessions_borrow_total{result} breakdown by tg_user_id or
error reason from the tools available here, the specific failing session(s)
cannot be identified with confidence in this pass.

## Proposed Fix
Two parts, both minimal and scoped to restoring diagnosability rather than
guessing at the exact failing session:

1. mctl-telegram (Go code): log a WARN-level line at the point
   mctl_sessions_borrow_total{result="error"} is incremented (the
   Pool.Borrow() call site in the session pool package), including
   tg_user_id, the error/result reason, and whether the identity is also
   active in another environment. Today only the counter increments; there is
   no accompanying log line, so the next occurrence of this alert has the
   same undiagnosable-from-logs problem this one does.
2. Operational verification (not a gitops file change): confirm whether the
   mctl-telegram-canary Secret's tg_user_id is actually 924671154 or still
   210408407 as the values.yaml comment warns it might be, and if it is still
   210408407, remint it via the documented POST /api/mcp/worker-token path
   (mctl-telegram#412/#421) rather than editing the Secret by hand. This
   cannot be verified or applied from this proposal — it requires reading a
   live out-of-band Secret, which is out of scope for a git-based proposal —
   so it is left as a task for the implementer/operator to check, not as a
   file edit.

## Scope
Minimal: one added log statement at the existing Pool.Borrow() error path in
mctl-telegram. No behavior change to borrow logic, retry policy, or resource
sizing — none of those are supported by the evidence available here.
