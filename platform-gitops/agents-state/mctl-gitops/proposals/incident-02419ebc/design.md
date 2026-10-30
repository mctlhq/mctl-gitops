# Design: incident-02419ebc

## Confidence: LOW

## Diagnosis
ArgoCD reported health "Missing" for labs-smoke-test-svc at 18:14 UTC. The pods were serving HTTP 200 health probes with no errors through 18:51, and the old ReplicaSet (fb6d58db) was replaced by a new one (546dc7f545) around 18:48, so the workload itself was healthy. At 19:11 UTC the ArgoCD application no longer exists, and logs stopped after 18:51. The most likely explanation is that this is a short-lived smoke-test service that was created or retired (Missing is the normal state of an app whose resources are not yet synced or have just been pruned), and the polling detector raised a transient incident. mctl-agent has no skill for this signal. No runtime fault was observed.

## Proposed Fix
No runtime change. The implementer should verify before applying anything:
1. Check whether platform-gitops/services/labs/smoke-test-svc still exists in mctl-gitops. If it was retired, no action is needed and no change should be made.
2. If the manifests still exist but the ArgoCD Application is absent, check that the Application/ApplicationSet generator covers labs/smoke-test-svc and fix that single entry.
3. If neither applies, make no change and note this in the PR/status.

## Scope
Minimal. Do not touch other tenants or services. Do not change alert rules unless step 2 shows a concrete defect.
