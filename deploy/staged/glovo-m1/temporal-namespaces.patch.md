# Temporal changes P1 would make (text only, not applied)

Both target files are reconciled and are NOT touched in P0.

## `platform-gitops/infra-components/data/temporal/tenant-namespace-job.yaml`

Append to the namespace list:

    mctl-assistants
    mctl-assistants-provider-glovo

## `platform-gitops/infra-components/data/temporal/networkpolicy.yaml` (`allow-temporal-ingress`)

Append ingress peers for the namespaces running the control worker and the
provider worker. Existing peers (mctl-agents, kuptsi) stay unchanged; P1 only
appends.

Blocked until #2469 proves client authentication: the Temporal server has no
client auth today, so a new namespace is reachable by any peer.
