# Design: incident-36b13eac

## Confidence: LOW

## Diagnosis
Same root cause as sibling incidents for labs/mctl-rules (967fa7e7, a7ba7606, 853412bc, c2c269da): the rollout does not progress because the pod never becomes ready. The app is Synced but Degraded and has no logs. Candidates, unconfirmed: probe path/port mismatch against port 3000, missing database secret, image pull failure for tag 0.1.0.

## Proposed Fix
Inspect platform-gitops/services/labs/mctl-rules/values.yaml for probe settings, database secret wiring and image tag; change only a field proven wrong. If nothing is provably wrong from repo state, make no change. Coordinate with proposal incident-5a936e29.

## Scope
Minimal. Only touch the single field that causes this alert. Duplicate of incident-5a936e29.
