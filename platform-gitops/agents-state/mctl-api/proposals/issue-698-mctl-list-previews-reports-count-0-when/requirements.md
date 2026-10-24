# mctl_list_previews: fail closed on unreadable state and list the real preview Helm releases

## Context

`GET /api/v1/previews` (`ListPreviews` in `internal/api/handlers_read.go`) and the
MCP tool `mctl_list_previews` (`internal/mcp/server.go`, `toolListPreviews`) have
two defects. First, every failure of the ArgoCD read (unauthenticated, forbidden,
transport or a malformed envelope such as "missing items array") is answered with
HTTP 200 and `{"items": [], "count": 0}` plus a `note` or `error` string. A read
that could not happen is reported as "no previews". An agent or human that checks
`count == 0`, for example to decide whether a stale preview needs cleanup, is told
nothing exists. This was reproduced on 2026-10-24 against production:
`mctl_list_previews(team=labs, service=psa-smoke)` returned
`{"count":0,"items":[],"note":"ArgoCD query failed: parsing argocd list response: missing items array"}`.

Second, the handler looks for ArgoCD Applications named
`preview-{team}-{service}-{id}`, but previews are not ArgoCD Applications. The
mctl-gitops ClusterWorkflowTemplate `wft-preview-deploy` runs
`helm upgrade --install "preview-${COMPONENT}-${PREVIEW_ID}"` directly into
namespace `${TEAM}-preview`. So even a successful ArgoCD read cannot return a
preview that `mctl_create_preview` created. This proposal makes the endpoint fail
closed and read the preview Helm releases from the preview namespace.

## User stories

- AS a platform agent deciding whether to clean up previews I WANT a failed read to be an error SO THAT I never act on "nothing is there" when the platform could not look.
- AS a tenant developer I WANT `mctl_list_previews` to list the previews that `mctl_create_preview` created SO THAT I can find, reuse or delete them.
- AS an operator I WANT the tool description to describe what is actually listed SO THAT callers are not misled about naming and source.

## Acceptance criteria (EARS)

- WHEN `GET /api/v1/previews?team=T` is called by a user with access to T AND the preview-namespace read succeeds THE SYSTEM SHALL return HTTP 200 with `items` holding one entry per preview Helm release in namespace `T-preview`, `count` equal to `len(items)`, `team` = T, `namespace` = `T-preview`.
- WHEN a Deployment in `T-preview` carries `app.kubernetes.io/managed-by=Helm` and `app.kubernetes.io/instance=preview-<service>-<id>` (the release name `wft-preview-deploy` produces, with `<id>` matching `^[a-z0-9]{1,6}$`) THE SYSTEM SHALL list it with `service`, `preview_id`, `release`, `namespace`, replica readiness fields and the creation timestamp.
- WHEN `service=S` is given THE SYSTEM SHALL return only releases whose name is exactly `preview-S-<id>` with `<id>` containing no hyphen, so that service `psa` does not match release `preview-psa-smoke-abc123`.
- IF the preview-namespace read fails for any reason (no Kubernetes client configured, forbidden, transport error, timeout, any other API error) THEN THE SYSTEM SHALL return HTTP 503 with an error message naming the namespace and the failure, and SHALL NOT include `count` or `items` in the body.
- IF the preview namespace `T-preview` does not exist (Kubernetes NotFound on a namespace get) THEN THE SYSTEM SHALL return HTTP 200 with `items: []`, `count: 0` and `preview_namespace: "absent"`, because absence was observed, not inferred.
- IF the namespace existence check itself fails THEN THE SYSTEM SHALL return HTTP 503 as for any failed read.
- WHEN the REST endpoint answers with a non-2xx status THE SYSTEM SHALL surface `mctl_list_previews` as an MCP tool error (`IsError: true`), not as a successful text result.
- WHILE the handler serves `/api/v1/previews` THE SYSTEM SHALL NOT call ArgoCD.
- THE SYSTEM SHALL keep the existing 401 (no user), 400 (missing team) and 403 (no tenant access) responses unchanged.
- THE SYSTEM SHALL describe `mctl_list_previews` as listing preview Helm releases in `{team}-preview` named `preview-{service}-{id}`, and SHALL state that a failed read is an error.

## Out of scope

- Changing how `wft-preview-deploy` / `wft-preview-delete` name or deploy previews (mctl-gitops).
- Preview TTL / expiry reporting (`mctl.ai/expires-at` lives on the Helm storage Secret, which mctl-api will not read; tracked by the TTL issue filed alongside #698).
- Fixing the ArgoCD client's "missing items array" parse failure (`internal/argocd/client.go`) for other callers.
- Changing `mctl_create_preview` / `mctl_delete_preview`.

## Open questions

- Source of truth choice: the issue offers Helm release Secrets or `mctl.ai/preview` labelled resources. This proposal reads Deployments (labels `app.kubernetes.io/instance` / `managed-by=Helm`) because reading Helm release Secrets requires `list secrets` in the preview namespace, which exposes every synced preview secret and contradicts the tenant chart's stated "without granting ... secret access" stance. Consequence: a release whose Deployment was never created (failed install) or that uses `blueGreen` (no Deployment) is not listed. `wft-preview-deploy` forces `blueGreen.enabled=false`, so this does not affect current previews. Reviewer should confirm this trade-off.
- The RBAC grant (`get`/`list` on `apps/deployments` in `{team}-preview`, plus namespace `get` which already exists cluster-wide) must land in mctl-gitops `helm-charts/tenant/templates/preview.yaml`. Until it is synced for a tenant, this endpoint returns 503 for that tenant, which is correct but visible.
- The exact HTTP status for failures: 503 is proposed for all backend read failures (matching `unavailable` patterns elsewhere in `internal/api`). 502 for a malformed answer was considered and not adopted, to keep one "unknown" status for callers.
