# Design: incident-249e2819

## Diagnosis
The ArgoCD application "forgejo" has been Degraded for 30 minutes. No skill matched, and the responder could not gather logs or pod state because the platform has no tenant named "forgejo" (it is not a catalogue service), so the application is deployed outside the mctl tenant model. Root cause is unknown.

## Proposed Fix
Investigate in mctl-gitops: locate the ArgoCD Application manifest for forgejo and determine which resource is unhealthy (likely a Deployment/StatefulSet/PVC or an image/chart value). Fix only the specific value found. If the application is intentionally unused or not yet finished, either correct its values or remove/disable the Application manifest, whichever the repository history supports.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.

## Confidence: LOW
No logs or resource state were observable. Verify the actual degraded resource before applying any change; if nothing clearly wrong is found in the manifests, make no change and record that in the PR.
