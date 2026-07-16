# Design: incident-mctl-agents-oauth-quota-exhaustion

## Diagnosis
`mctl-agents-run` (invoked by the `mctl-agents-incidents` CronWorkflow, schedule
`15,45 * * * *`) has failed on every single tick for at least 14.5 consecutive
hours (2026-07-15T11:47Z through 2026-07-16T02:20Z, 16+ occurrences, each
completing in only ~100-210s — far too fast to represent real orchestrator
work, which normally runs multiple service-agents plus a mentor pass).

`cwft-mctl-agents-run.yaml` runs `run-orchestrator` first on the primary
`claude-code-oauth-token`, and only retries with `claude-code-oauth-token-2` on
failure (`run-fallback` step, gated by
`when: "{{steps.run.status}} != Succeeded"`). The fallback step's own guard
script (lines ~186-190) exits 1 immediately if `CLAUDE_CODE_OAUTH_TOKEN` is
empty — deliberately failing loudly rather than masking the problem. That is
correct behavior, but it means both the primary and fallback attempts fail
fast if (a) the primary OAuth token is exhausted or invalid, and (b)
`claude-code-oauth-token-2` was never seeded in Vault at
`secret/platform/mctl-agents`. That combination matches the observed
~100-210s failure time (pod schedule + fast SDK auth failure + fast fallback
guard exit + a no-op commit-and-push) far better than a timeout, OOM, or
scheduling issue would (those would show much larger or much more variable
durations, as seen in the unrelated `shepherd`/`issue-poll` incidents in the
same queue, which fail after 8250s and 14850s respectively — a different
signature, out of scope for this proposal).

This is not a novel failure mode. `cwft-mctl-agents-run.yaml` documents a
near-identical prior incident directly in its own comments: "the
incident-responder cron shares `claude-code-oauth-token` with every other
pipeline consumer, so a quota exhaustion event otherwise hard-fails EVERY
30-min tick until the window resets (observed 2026-07-12 18:16-20:16 UTC, 5
failed runs)." Separately, `platform-gitops/argo-workflows/secrets/mctl-agents-secrets.yaml`
anticipates exactly this scenario: "If owner's claude.ai session is
invalidated -> token dies -> workflow fails -> re-run setup-token + re-seed
Vault. Consider adding a smoke alert on the CronWorkflow's last-success age
(>48h = investigate)." That smoke alert was never built — which is why a
credential problem that should have paged a human once has instead silently
produced 16+ duplicate, evidence-free `workflow_failed` incidents that pile up
in `analyzing` with nothing able to triage them (the incident-responder is
the very pipeline that is down).

Live corroborating signal at triage time: `mctl_list_recent_agent_runs` shows
`mctl-agents-implement` (which shares the identical primary/fallback OAuth
pattern per its own comments — "Same shared mutex as cwft-mctl-agents-run —
both push to mctl-gitops main") currently succeeding on recent ticks
(05:01-05:15), while no successful `mctl-agents-incidents` completion appears
in that same recent window. This is consistent with — though does not fully
confirm — the two pipelines drawing from the same credential but not failing
in perfect lockstep (e.g. token quota recovering intermittently, or `implement`
succeeding on the primary token while `incidents` keeps drawing the account
into the same 5-hour usage-limit window). Full confirmation requires the
Vault key state, which is not observable from this repo checkout.

## Confidence: LOW
The exact current state of Vault's `secret/platform/mctl-agents` keys
(`claude-code-oauth-token`, `claude-code-oauth-token-2`) cannot be verified
from this repo checkout, from Loki (no logs exist for these short-lived job
pods), or from the workflow audit log (individual failed Workflow records for
this ID range have already been pruned). The Argo Workflow Controller's exact
exposed metric name for "time since last Succeeded run of a given
ClusterWorkflowTemplate" was inferred from the standard `argo_workflows_*`
metrics family shipped by the argo-workflows Helm chart, not independently
confirmed against the live VictoriaMetrics instance. The implementer must
verify the metric name before merging (see tasks.md) and should confirm with
the platform operator whether `claude-code-oauth-token-2` is actually seeded,
since that is the real fix for the underlying auth failures — not achievable
via a gitops PR, and out of scope here.

## Proposed Fix
1. Add a new VMRule alert group to
   `platform-gitops/infra-components/observability/vm-rules/mctl-alerts.yaml`
   (alongside the existing `mctl.tenant-quotas` / `argocd` / `minio.disk-usage`
   groups) that fires once when the `mctl-agents-incidents` / `mctl-agents-implement`
   pipelines have had no successful completion for an extended window:

   ```yaml
   - name: mctl.agents-pipeline-health
     rules:
       - alert: MctlAgentsPipelineStale
         expr: |
           time() - max(
             argo_workflows_completion_time_seconds{
               name=~"mctl-agents-(incidents|implement).*",
               status="Succeeded"
             }
           ) > 21600
         for: 5m
         labels:
           severity: warning
         annotations:
           summary: >-
             mctl-agents cron pipeline has had no successful run in 6h --
             check Vault secret/platform/mctl-agents: claude-code-oauth-token
             may be expired/exhausted and claude-code-oauth-token-2 may be
             unseeded (see platform-gitops/argo-workflows/secrets/mctl-agents-secrets.yaml)
   ```

   6h (21600s) is intentionally shorter than the 48h floated in the
   ExternalSecret comment: the observed outage was already 14+ hours old and
   had generated 16+ duplicate incidents well before 48h would have elapsed.
   The implementer should confirm this threshold against real noise levels,
   and MUST confirm the exact metric name (see Confidence note) — if
   `argo_workflows_completion_time_seconds` does not exist in the live
   instance, use whatever equivalent last-success gauge/counter the
   argo-workflows ServiceMonitor actually exposes (candidates:
   `argo_workflows_success_count` combined with `absent()`/`increase()`
   logic, or `argo_workflows_pod_missing`).

2. Route `MctlAgentsPipelineStale` to the existing `telegram` receiver (not
   `mctl-agent`) in
   `platform-gitops/bootstrap/templates/observability/monitoring.yaml`,
   as a new matcher alongside the existing `NodeCordoned|K3sUpgradeJobFailed`
   telegram route (~line 290):

   ```yaml
   - receiver: telegram
     matchers:
       - alertname =~ "NodeCordoned|K3sUpgradeJobFailed|MctlAgentsPipelineStale"
   ```

   mctl-agent cannot self-remediate an expired OAuth token (it's the thing
   that would be down), so this must page a human directly — the same
   pattern the file already uses for other operator-only failure modes.

## Scope
Minimal. One new alert rule plus one new Alertmanager route matcher. Does
NOT touch the CronWorkflow schedules, the shared `mctl-gitops-main-writes`
mutex, or the primary/fallback OAuth logic in `cwft-mctl-agents-run.yaml` /
`cwft-mctl-agents-implement.yaml` — that logic is already correctly designed
to fail loudly rather than mask the problem. Does NOT reseed the Vault
secret; that is an out-of-band operator action this proposal surfaces via
alerting rather than performs.
