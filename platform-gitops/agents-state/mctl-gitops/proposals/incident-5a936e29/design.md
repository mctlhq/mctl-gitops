# Design: incident-5a936e29

## Confidence: LOW

## Diagnosis
The ArgoCD application labs-mctl-rules is Synced but Degraded, and the service produced zero log lines in the last hour, so the pod most likely never starts serving (not ready, or never scheduled/started). mctl-agent had no matching skill. Related incidents for the same service (a7ba7606, bd637526, 853412bc, c2c269da) show replica mismatch, stalled rollout and non-ready pod, which point to one root cause: the Deployment never becomes ready. Candidate causes, none confirmed: readiness probe path/port mismatch (chart default is /healthz and /readyz, service port is 3000), missing database credentials secret (hasDatabase=true), or image pull failure for tag 0.1.0. Verify before changing anything.

## Proposed Fix
Inspect platform-gitops/services/labs/mctl-rules/values.yaml. Check (1) health_check_path / probe settings against what the app actually serves on port 3000, (2) that the database ExternalSecret and Vault path teams/labs/mctl-rules/database exist, (3) that image.tag 0.1.0 exists in the registry. Change only the single field proven wrong. If none is provably wrong from repo state, make no change and report that the incident needs live cluster inspection.

## Scope
Minimal. Only touch the single field that causes this specific alert. This is the primary proposal for the group; the other four incidents for labs/mctl-rules are duplicates and reference the same root cause.
