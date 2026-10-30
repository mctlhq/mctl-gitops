# Design: incident-2a6e551f

## Confidence: LOW

## Diagnosis
Same root cause as sibling incidents for labs/mctl-rules (967fa7e7, bd637526, 853412bc, c2c269da): the ArgoCD app is Synced but Degraded and the Deployment never reaches its expected replica count. No logs exist for the service, so the pod likely never becomes ready. Candidates, unconfirmed: probe path/port mismatch against port 3000, missing database secret, image pull failure for tag 0.1.0.

## Proposed Fix
Inspect platform-gitops/services/labs/mctl-rules/values.yaml for probe settings, database secret wiring and image tag; change only a field proven wrong. If nothing is provably wrong from repo state, make no change. Coordinate with proposal incident-5a936e29 so the same edit is not made twice.

## Scope
Minimal. Only touch the single field that causes this alert. Duplicate of incident-5a936e29.
