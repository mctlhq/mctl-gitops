# Design: incident-89811906

## Confidence: LOW

## Diagnosis
The mctl-agents `implement` Argo workflow ran two `run-implementer` attempts (a
primary and an account-2 fallback) for proposal issue-591, and the
`assert-attempt` step recorded that both failed. The step's own log names the
two most likely causes: the Claude five-hour/seven-day usage limit (HTTP 429)
being hit on both configured accounts, or the account-2 fallback token
(`token-2`) being unset in the workflow's environment. No skill matched this
because it is a workflow-orchestration failure, not a service-level bug the
existing skills know how to diagnose from application logs — hence status
`analyzing` with an empty `analysis` field. This incident is not the only one:
a sibling incident (argo-mctl-agents-implement-4df6cd9e, proposal issue-242)
failed with the identical `assert-attempt` message about 3 minutes later,
which points at a shared root cause (credential/config or capacity) rather
than something specific to either proposal. This proposal and
incident-89812083 (issue-242) describe the same underlying fault; the fix
described here is identical to that proposal's.

## Proposed Fix
This is written LOW confidence because the two candidate causes require
verification against the account-2 secret and the Claude account usage
dashboards, which this responder cannot access.

1. Verify the account-2 (fallback) Claude credential referenced by the
   mctl-agents `implement` Argo Workflow template is present and current in
   Vault / the ExternalSecret backing it (commonly surfaced to the workflow as
   a `token-2`-style env var or secret key). If it is unset or expired,
   restore it.
2. If both accounts' credentials are valid, the cause is usage-limit
   exhaustion (five_hour/seven_day window) rather than a config error — in
   that case, add spacing/backoff between concurrent `implement` workflow
   runs (e.g. an Argo Workflow `synchronization` semaphore limiting concurrent
   `run-implementer` steps) so parallel proposal runs do not exhaust both
   accounts' rate-limit windows at the same time.
3. Once the credential/capacity issue is fixed, the two proposals that were
   pushed to `needs-triage` by this failure (issue-591 and issue-242 — see
   sibling incident argo-mctl-agents-implement-4df6cd9e) need to be manually
   moved back to `accepted` for `mctl_trigger_implementer` to retry them, per
   its documented behavior that `needs-triage` results are not retried
   automatically.

## Scope
Minimal: verify/restore the account-2 secret wiring for the mctl-agents
`implement` workflow, and only add a concurrency guard if usage-limit
exhaustion (not a missing secret) turns out to be the actual cause. Since this
is the same root cause as incident-89812083, applying that proposal's fix
resolves this incident too — treat the two as one fix, not two separate
changes.
