# Tasks: incident-mctl-agents-oauth-quota-exhaustion

1. [ ] In `platform-gitops/infra-components/observability/vm-rules/mctl-alerts.yaml`,
   add a new `mctl.agents-pipeline-health` rule group containing the
   `MctlAgentsPipelineStale` alert exactly as drafted in design.md.

2. [ ] Before merging, verify the metric name used in the alert expression
   (`argo_workflows_completion_time_seconds`) actually exists in the live
   VictoriaMetrics instance (check the argo-workflows-controller
   ServiceMonitor's scraped series). If it does not exist, substitute the
   nearest equivalent last-successful-run gauge/counter that the
   argo-workflows Helm chart's metrics endpoint exposes, keeping the same
   `name=~"mctl-agents-(incidents|implement).*", status="Succeeded"` label
   matching intent.

3. [ ] In `platform-gitops/bootstrap/templates/observability/monitoring.yaml`,
   add `MctlAgentsPipelineStale` to the existing `telegram` route matcher
   alongside `NodeCordoned|K3sUpgradeJobFailed` (~line 290-292), so this
   alert pages a human directly instead of going through the `mctl-agent`
   webhook (mctl-agent cannot fix its own expired credentials).

4. [ ] Confirm `MctlAgentsPipelineStale` is intentionally NOT added to
   `mctl-agent/internal/monitor/alerthandler.go::classifyAlert` (per the
   comment at the top of `mctl-alerts.yaml`, alert names routed to
   `mctl-agent` must be kept in sync with that switch — this one is
   deliberately routed to `telegram` instead, so no code change is needed
   there; just verify no accidental fallthrough).

5. [ ] Validate the new VMRule and Alertmanager route render correctly
   (`helm template` against the monitoring Application, or
   `kubectl apply --dry-run=server`) before merging.

6. [ ] Outside this PR: flag to the platform operator that
   `secret/platform/mctl-agents` in Vault should be checked — reseed
   `claude-code-oauth-token` (`claude setup-token`) if expired, and seed
   `claude-code-oauth-token-2` with a second account's token so the
   existing fallback logic in `cwft-mctl-agents-run.yaml` /
   `cwft-mctl-agents-implement.yaml` has a working account to fall back to.
   This is the actual fix for the underlying failures; the alert above only
   ensures it is never silently down for 14+ hours again.

7. [ ] Once the pipeline is confirmed healthy again (a real
   `mctl-agents-incidents` run succeeds), manually resolve any remaining
   duplicate `workflow_failed` incidents for `mctl-agents-incidents` /
   `mctl-agents-implement` / `mctl-agents-shepherd` / `mctl-agents-issue-poll`
   still stuck in `analyzing` beyond the 5 this run resolved directly — the
   incident-responder could not process all of them in one run (5/run cap)
   and could not fully self-heal them either, since it was the affected
   pipeline.
