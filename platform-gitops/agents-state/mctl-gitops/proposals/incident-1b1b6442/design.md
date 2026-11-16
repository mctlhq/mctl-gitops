# Design: incident-1b1b6442

## Confidence: LOW

## Diagnosis
mctl-agent had no skill for KubeDeploymentRolloutStuck. Logs could not be read (no tenant named "mctl-api"). A stuck rollout is most plausibly a consequence of the new mctl-api pods crash looping (see incident-c2384949) and failing readiness. Unverified.

## Proposed Fix
No independent change. Resolve incident-c2384949 first; this alert should clear once the rollout completes. If the implementer finds a defect in the mctl-api values (probe path, resources, image tag), fix only that single field, coordinated with incident-c2384949 to avoid duplicate PRs. Otherwise make no change.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
