# Tasks: incident-d683e015

1. [ ] In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-run.yaml`,
       in the `run-orchestrator` template's `env:` list, add a new
       `INCIDENT_RESPONDER_BUDGET_USD` entry with value `"20.00"` immediately
       after the existing `MENTOR_BUDGET_USD` entry (see design.md for the
       exact diff and comment block to include).
2. [ ] Verify the YAML still parses (correct indentation matching the sibling
       `SERVICE_AGENT_BUDGET_USD` / `MENTOR_BUDGET_USD` entries) and that no
       other `env:` entry named `INCIDENT_RESPONDER_BUDGET_USD` already
       exists in this template.
3. [ ] No image tag bump or other dependent change needed — this is a plain
       ClusterWorkflowTemplate manifest change picked up on the next Argo
       sync, no code release required.
4. [ ] Cross-check after merge: if `mctl-agents-incidents` ticks keep failing
       at the same ~5-6 minute mark after this change ships, that rules out
       the budget-cap theory and points back to the already-tracked OAuth
       token exhaustion (`incident-mctl-agents-oauth-quota-exhaustion`) as
       the sole cause — escalate a Vault reseed of
       `secret/platform/mctl-agents: claude-code-oauth-token` /
       `claude-code-oauth-token-2` to the platform operator instead of
       iterating further on this file.
