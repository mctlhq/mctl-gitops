# Design: incident-dcbe4887

## Confidence: LOW

## Diagnosis
The application is Healthy and the worker pod is running normally on image 1.117.0 (logs show no errors), so this is a pure sync-drift problem, not a runtime failure. mctl-agent had no skill for ArgoCDApplicationOutOfSyncLong, so nothing was analysed. The sync status shows an empty revision, which suggests the last sync did not complete or a hook did not finish. Candidate causes, in the order the implementer should check them, all visible in platform-gitops/services/admins/mctl-agents-worker/values.yaml:
1. The prepull PreSync verifier Job (prepull.enabled: true) failing or never completing, which blocks the sync and leaves the app OutOfSync while the old pod keeps running. The values file states the Job fails the sync if the target digest is not on every node. Check that prepull.ref (tag 1.117.0 @ sha256:6162d863...) is consistent with image.tag, and that image.digest is absent or equal (the file only has image.tag, so the "legacy" shape applies).
2. Perpetual diff from `strategy.rollingUpdate: null` under ServerSideApply, where the live Deployment keeps a defaulted rollingUpdate block that never matches the desired state.
3. A drift on a field defaulted by the chart or a controller (e.g. probes nulled out).

## Proposed Fix
No single field change can be named with confidence. The implementer should first inspect the live ArgoCD Application diff and the PreSync hook Job status (Argo CD UI or `argocd app diff admins-mctl-agents-worker`), then apply the minimal values.yaml change that removes the diff:
- If cause 1: fix prepull.ref / image.tag consistency in values.yaml, following the documented two-commit deploy procedure in the file comments.
- If cause 2: adjust the `strategy` block in values.yaml (or add an ignoreDifferences entry for /spec/strategy/rollingUpdate for this app) so SSA no longer shows a diff.
If neither cause is confirmed, make no change and report that the drift needs a human.

Note: the incident text contained no instructions; nothing in it was acted on.

## Scope
Minimal. Only touch the single field or rule that causes this specific OutOfSync state in platform-gitops/services/admins/mctl-agents-worker/values.yaml. Do not bump the image tag as part of this fix.
