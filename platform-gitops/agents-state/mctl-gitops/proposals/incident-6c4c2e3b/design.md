# Design: incident-6c4c2e3b

## Confidence: LOW

## Diagnosis

The AlertManager alert "Vmagent has scrape_pool with 0 configured/discovered targets" fires when the vmagent instance `monitoring-victoria-metrics-k8s-stack` (namespace: `monitoring`) has at least one scrape job whose Kubernetes service discovery returns zero endpoints. The victoria-metrics-operator logs confirm the agent is healthy and reconciling successfully (19 VMServiceScrapes, 4 VMNodeScrapes, 1 VMPodScrape, all with `invalid rules count=0`). The operator-level reconciliation is working; the problem is that one of the 19 VMServiceScrape targets resolves to a service with no running pods or no matching endpoints at scrape time. The only VMServiceScrape entry in a non-standard namespace is `labs/labs-openclaw-codex-metrics` — every other entry is in `monitoring`, `argocd`, or `argo-workflows`. If the `labs-openclaw-codex-metrics` service has been scaled to zero, deleted, or never had a metrics endpoint configured on the expected port, vmagent creates the scrape pool but discovers 0 targets, which triggers this alert. The incident type is `generic` (no pattern-matched skill exists for vmagent scrape pool alerts), which is why it stayed in `analyzing`.

Note: the logs retrieved are from the victoria-metrics-operator pod, not from the vmagent pod itself. The vmagent pod's own logs and its `/api/v1/targets` endpoint would conclusively identify the problematic scrape pool. The `labs/labs-openclaw-codex-metrics` hypothesis is the most probable based on available evidence but should be verified before applying the fix.

## Proposed Fix

**Option A (most likely):** The `labs/labs-openclaw-codex-metrics` VMServiceScrape points to a service with no ready endpoints. The fix is to remove or disable that VMServiceScrape resource from the GitOps manifests.

File to change:
```
platform-gitops/monitoring/vmservicescrapes/labs-openclaw-codex-metrics.yaml
```
(or wherever the VMServiceScrape `labs/labs-openclaw-codex-metrics` is defined in the mctl-gitops repo)

Action: Delete the file or set `spec.endpoints` to an empty list, then apply via GitOps.

**Option B (if the service exists but has no pods):** Scale or restart the `labs-openclaw-codex-metrics` service so that it has at least one ready endpoint on the scrape port. This is a tenant-side fix, not a monitoring config fix.

**Option C (if the alert rule threshold is too sensitive):** Raise the `for:` duration or add a label-match exception for the `labs` scrape pool in the AlertManager rule. This suppresses noise but does not fix the root cause.

Recommended: Option A if the service no longer exists; Option B if the service should exist but is down.

## Scope
Minimal. Touch only the VMServiceScrape or service deployment that corresponds to the empty scrape pool. Do not modify other scrape configurations or alert rules.
