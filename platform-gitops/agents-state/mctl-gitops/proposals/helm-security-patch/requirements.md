# Helm Security Patch: upgrade to v4.1.4

## Context
Three vulnerabilities have been disclosed against Helm in versions v4.0.0–v4.1.3.
GHSA-vmx8-mqv2-9gmg permits arbitrary file writes outside the plugin directory during plugin
installation. GHSA-hr2v-4r36-88hr enables path traversal during chart extraction via a
specially crafted `name` field in `Chart.yaml` containing a dot-segment (e.g. `../`).
GHSA-q5jf-9vfq-h4h7 permits bypassing the plugin signature check — plugins are installed
without a `.prov` file even when verification is enabled.

The platform uses Helm for the `base-service` chart and ApplicationSet-based deploys. The
Helm CLI is also involved in ArgoCD and scaffolding processes. The path traversal during
chart extraction is especially critical in a GitOps context: a malicious chart in the
repository can lead to arbitrary file writes on the node. The fix is shipped in v4.1.4
(patch release, no breaking changes).

## User stories
- AS a platform engineer I WANT Helm upgraded to v4.1.4 SO THAT chart extraction cannot be exploited for path traversal attacks against cluster nodes or the ArgoCD server filesystem.
- AS a security officer I WANT plugin signature verification to actually enforce .prov file checks SO THAT unsigned plugins cannot be installed silently.
- AS a platform engineer I WANT plugin installation to be safe SO THAT malicious plugins cannot write files outside the designated plugin directory.

## Acceptance criteria (EARS)
- WHEN Helm is used in any platform component (ArgoCD, CI, CLI) THE SYSTEM SHALL run version v4.1.4 or newer.
- WHEN a chart archive is extracted and `Chart.yaml` contains a name with dot-segment path characters THE SYSTEM SHALL reject extraction and return an error (GHSA-hr2v-4r36-88hr).
- WHEN a Helm plugin is installed with signature verification enabled THE SYSTEM SHALL require a valid `.prov` file and refuse installation if it is absent or invalid (GHSA-q5jf-9vfq-h4h7).
- WHEN a Helm plugin archive is extracted THE SYSTEM SHALL restrict all extracted files to the designated plugin directory and not write to any path outside it (GHSA-vmx8-mqv2-9gmg).
- WHILE ArgoCD is reconciling Applications that use Helm THE SYSTEM SHALL use only the patched Helm binary bundled with the updated ArgoCD image (or a patched sidecar).
- IF the Helm binary version in the ArgoCD image is older than v4.1.4 THEN THE SYSTEM SHALL not be used for chart rendering until the image is updated.

## Out of scope
- Helm major version upgrade (v4.x → v5.x).
- Changes to the `base-service` chart structure or tenant `values.yaml`.
- Audit of existing charts for suspicious names in Chart.yaml (separate task).
- Upgrade of ArgoCD to a new major version solely to obtain the new Helm (Helm is upgraded within the existing ArgoCD version or an ArgoCD patch release that ships the new Helm).
