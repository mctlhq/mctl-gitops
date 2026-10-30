# Design: incident-6010313b

## Confidence: LOW

## Diagnosis
The vault StatefulSet reports ready replicas different from desired. The skill statefulset-replicas-mismatch gave a medium-confidence, non-fixable diagnosis. Its generic guidance lists several possible causes (crash loop, Pending pod, failing readiness probe, unbound PVC, stuck revision). No logs were available, so the actual cause is unknown. A common cause for Vault is a sealed pod failing its readiness probe after a restart, which is an operational unseal step, not a config change.

## Proposed Fix
Do not make blind changes. The implementer should inspect the vault StatefulSet values in mctl-gitops (replica count, readiness probe, update strategy, PVC settings) for an obvious misconfiguration. If none is found, make no change and record in the PR that the cause is operational (for example a sealed pod or a stuck pod) and needs a human. Do not delete pods or alter secrets.

## Scope
Minimal. Only touch a single misconfigured field if one is clearly identified.
