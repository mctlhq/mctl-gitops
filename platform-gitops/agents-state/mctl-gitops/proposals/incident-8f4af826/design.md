# Design: incident-8f4af826

## Confidence: LOW

## Diagnosis
Same root cause as sibling incidents for labs/mctl-rules (967fa7e7, a7ba7606, bd637526, 853412bc): ArgoCD health Degraded while sync is Synced, with no service logs. The Deployment most likely never becomes ready. Candidates, unconfirmed: probe path/port mismatch against port 3000, missing database secret, image pull failure for tag 0.1.0. The skill argocd_sync_failed ran and gave a LOW-confidence, non-fixable diagnosis.

## Proposed Fix
Inspect platform-gitops/services/labs/mctl-rules/values.yaml for probe settings, database secret wiring and image tag; change only a field proven wrong. If nothing is provably wrong from repo state, make no change. Coordinate with proposal incident-5a936e29.

## Scope
Minimal. Only touch the single field that causes this alert. Duplicate of incident-5a936e29.
