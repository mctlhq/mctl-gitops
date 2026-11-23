# Design: incident-30628085

## Confidence: LOW

## Diagnosis
mctl-agent had no skill for ArgoCDApplicationDegraded. root-app is the app-of-apps parent; its health aggregates its children, so it is Degraded because a child application is Degraded, most likely admins-mctl-api (incident-39f5cb26) and the underlying mctl-api crash loop (incident-c2384949). No direct observation was made.

## Proposed Fix
No independent change to root-app. It should recover when the child apps are fixed. Make no change unless a defect in the root-app definition itself is positively identified.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
