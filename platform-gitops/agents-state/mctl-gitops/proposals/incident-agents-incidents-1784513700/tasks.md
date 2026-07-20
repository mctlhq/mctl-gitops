# Tasks: incident-agents-incidents-1784513700

1. [ ] Do not action independently — this incident is a duplicate of the
       already-tracked issue in
       `mctl-gitops/proposals/incident-mctl-agents-oauth-quota-exhaustion`
       (status: implemented) and `mctl-gitops/proposals/incident-argo-mct`
       (status: in-progress). Confirm both proposals' current status before
       doing anything else.
2. [ ] Verify whether the `MctlAgentsPipelineStale` alert (added by
       `incident-mctl-agents-oauth-quota-exhaustion`) has actually fired —
       failures for this pipeline have now been ongoing for 9+ hours, past
       its 6h threshold. If it has not fired, that alert itself needs
       follow-up (metric name / routing may need verification, as flagged
       LOW confidence in that proposal).
3. [ ] Confirm with the platform operator whether
       `secret/platform/mctl-agents: claude-code-oauth-token-2` is seeded in
       Vault; reseed/rotate credentials as needed. This is the suspected
       real fix and is out-of-band, not a GitOps PR.
4. [ ] Once the credential issue is resolved, confirm no further
       fast-fail (122.201957s-class) `workflow_failed` incidents recur for
       the `mctl-agents-incidents` pipeline for at least 24h.
