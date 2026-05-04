# Loki Ruler API Unauthenticated Remote File Read (CVE-2026-21726)

## Context
CVE-2026-21726 discloses an unauthenticated path traversal vulnerability in the Loki Ruler API endpoint `/loki/api/v1/rules/{namespace}`. By double-URL-encoding the `namespace` path segment an attacker can escape the expected rules directory and read any file accessible to the Loki process, including mounted Kubernetes Secret volumes and service account tokens. No authentication is required to exploit the endpoint; the only prerequisite is network access to the Loki Ruler API port.

The architecture tracks `grafana/loki` as a dependency (see `context/architecture.md` Dependencies section). Loki v3.7.1 is the patched release that addresses this CVE. Because the Loki process may run with access to mounted secrets and platform service account tokens, exploitation could allow lateral movement across the platform. The fix is a version-pin update to v3.7.1 or later; no schema migrations or CRD changes are involved. If the Loki Ruler component is not enabled in the current deployment, the version should still be pinned to eliminate the exposure and keep the platform on a supported, secure release.

## User stories
- AS a platform engineer I WANT Loki pinned to v3.7.1 or later SO THAT the Ruler API path traversal vulnerability is closed.
- AS a security officer I WANT confirmation that no unauthenticated read path exists against Loki file system SO THAT mounted secrets and service account tokens are not exposed to external actors.
- AS a tenant operator I WANT assurance that Loki does not expose the underlying cluster file system SO THAT tenant secrets cannot be read via Loki's network endpoint.

## Acceptance criteria (EARS)
- WHEN the Loki version deployed in the cluster is queried THE SYSTEM SHALL report v3.7.1 or later.
- WHEN an unauthenticated request using a double-URL-encoded path traversal sequence is sent to `/loki/api/v1/rules/{namespace}` THE SYSTEM SHALL return an HTTP 4xx error and not return file contents from the Loki process file system.
- WHEN the Loki image tag is updated in the GitOps repository THE SYSTEM SHALL reference the official v3.7.1 (or later) image digest.
- WHILE the Loki rollout is in progress THE SYSTEM SHALL keep log ingestion and query serving available with at most one pod unavailable at a time (rolling update strategy).
- IF the Loki pod fails readiness checks after the image update THE SYSTEM SHALL not promote the new version and shall retain the previous running pod.
- WHEN the upgrade is complete THE SYSTEM SHALL successfully receive log streams and answer queries for both `admins` and `labs` tenants without manual intervention.

## Out of scope
- Enabling or disabling the Loki Ruler component — operational configuration is unchanged; only the version is updated.
- Implementing network policies to restrict access to the Ruler API port — a defence-in-depth measure to be addressed in a separate proposal.
- Rotating any service account tokens or secrets that may have been accessible to the Loki process before this patch.
- Upgrading Grafana or Prometheus alongside this change.
