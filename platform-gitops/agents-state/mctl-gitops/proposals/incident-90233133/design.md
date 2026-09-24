# Design: incident-90233133

## Diagnosis
`mctl-agents-implement-ab568250` (implementer run for
`issue-1280-spike-observability-run-the-live-tracing`) failed both its
primary attempt (account-1 OAuth token) and its account-2 fallback attempt,
tripping the CWFT's `assert-attempt` step and firing a `workflow_failed`
incident. `assert-attempt` already prints the correct diagnosis to its own
stderr: "Neither the primary attempt nor the account-2 fallback succeeded
... Most often the Claude five_hour/seven_day usage limit / HTTP 429 on both
accounts, or token-2 unset." Inspecting the raw Claude Agent SDK session logs
for both `run-implementer` pods confirms this: the primary attempt's stream
carried a `RateLimitEvent` with `rate_limit_type='five_hour'`,
`overage_status='rejected'`, `overage_disabled_reason='out_of_credits'`, and
the fallback attempt's stream carried a `RateLimitEvent` with
`rate_limit_type='seven_day'`, `utilization=0.82` (`allowed_warning`) — i.e.
both accounts were at or near their usage ceiling in the same window, so the
existing single-fallback design (mirrors cwft-mctl-agents-run/-investigate/
-shepherd) had no further account to retry on.

This is why both attempts left their proposal's `.status.yaml` at
`status: in-progress` (their claim, never advanced to `implemented`/`error`)
and only `commit-and-push`'s own small diff (13 insertions/3 deletions)
landed — that push just persists the stuck claim, not a completed proposal.

The skill did not miss anything: this incident escalated with an EMPTY
`analysis` field even though the workflow already knew the cause. That is
the actual defect this proposal targets — not the rate limit itself, which
is an external Anthropic account-capacity constraint outside gitops' control
and not something a config change here can fix. The `notify-telegram` onExit
step's incident-creation body
(`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`,
step `notify-telegram`, the `BODY=$(jq -nc ...)` block around line 1102) only
sets `summary` to a generic "implement `<subject>` `<status>` after `<dur>`s
— `<url>`" string. It never carries the specific failure reason that
`assert-attempt` already computed, so every incident of this shape reaches
`mctl-api` with `analysis` empty, forcing a human or agent to re-open the
Argo UI / pull ~170KB-per-pod raw SDK logs to recover a conclusion the
workflow already reached internally.

## Proposed Fix
In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`:

1. Add `{{workflow.failures}}` (Argo's built-in variable holding each failed
   node's `displayName`, `message`, and `templateName`) to the environment of
   the `notify-telegram` step, e.g.:
   ```yaml
   - name: WORKFLOW_FAILURES
     value: "{{workflow.failures}}"
   ```
2. In the `source:` script's incident-leg `BODY=$(jq -nc ...)` construction
   (currently only `id`, `source`, `type`, `tenant`, `service`, `summary`,
   `severity`, `status`, `fingerprint`), add the failed-node detail as a new
   `analysis` field, passed through `jq --arg failures "$WORKFLOW_FAILURES"`
   so any characters in the failure message are safely JSON-encoded:
   ```yaml
   BODY=$(jq -nc --arg id "$INCIDENT_ID" --arg summary "$SUMMARY" \
     --arg fingerprint "$FINGERPRINT" --arg failures "$WORKFLOW_FAILURES" '{
     id: $id,
     source: "argo-workflows",
     type: "workflow_failed",
     tenant: "admins",
     service: "mctl-agents",
     summary: $summary,
     analysis: $failures,
     severity: "warning",
     status: "analyzing",
     fingerprint: $fingerprint
   }')
   ```
   `{{workflow.failures}}` is only non-empty when the workflow actually has
   failed nodes, matching the existing `WORKFLOW_STATUS = Failed || Error`
   guard around this block, so `analysis` degrades gracefully (empty string)
   on any other status without an extra conditional.

## Scope
Minimal. Only the `notify-telegram` template's env block and its incident
`BODY` construction in `cwft-mctl-agents-implement.yaml` change. No change
to `assert-attempt`'s pass/fail logic, no change to retry/backoff behavior,
no new fallback account, no alerting-threshold change. Does not attempt to
fix or work around the underlying Claude usage-limit exhaustion, which is an
account-capacity condition outside this repo's control and expected to
self-resolve once the five_hour/seven_day window rolls over.

## Confidence: LOW
I confirmed the exact failure mechanism (assert-attempt's Succeeded/Succeeded
check on `{{steps.implement.status}}` / `{{steps.implement-fallback.status}}`)
and the incident-body construction directly from
`cwft-mctl-agents-implement.yaml` in this checkout, and confirmed via raw SDK
log grep that both attempts did emit rate-limit-adjacent events consistent
with assert-attempt's own stated cause. I did not independently verify that
`{{workflow.failures}}` renders as valid, non-huge JSON for THIS specific
failure shape (two `continueOn: {failed: true, error: true}` steps followed
by a hard-failing `assert-attempt`) — Argo's `workflow.failures` payload can
be large or include multiple entries, and the `jq --arg` call assumes it is
well-formed text, not literal JSON that needs `--argjson`. The implementer
should verify the rendered variable's shape on a real failing run (or a
`argo lint`/dry-run) before merging, and truncate/summarize it if it turns
out to be unexpectedly large.
