# Rollbacks require an owner grant and restore tag plus digest

version-status: unverified, see commit SHA (mctl MCP not used; inbox reports mctl-api 4.170.1 from gitops bump commits)

## Context
On 2026-11-17 mctl-api added `POST /api/v1/deploy/rollback` and the MCP tool `mctl_rollback_deployment` (8780f98). A production rollback is now planned from an earlier production DeployRecord and applied only behind an owner's `deploy.apply` grant. The previous ungoverned `rollback-revision` route now refuses production deployments (`rollback_requires_grant`) (8780f98, 46694e8).

In mctl-gitops (2026-11-19) the `rollback-service` workflow template was changed to restore the image tag and digest together via `scripts/rollback-image-ref.py` (c6f49f9), and the script fails closed on unreadable history and distrusts digests shared across tags (ad65613, 7fc94b6, 6fd14e2, 8d09fb4). `docs/guides/rollbacks.md` was not read by the researcher; it likely describes the old tag-only, ungoverned rollback.

## User stories
- AS a tenant owner I WANT to know that production rollbacks need my grant SO THAT I know where to approve them.
- AS a developer I WANT to know how to plan a rollback (REST/MCP) SO THAT I can request one.
- AS a platform admin I WANT to know a rollback restores tag and digest together and when it refuses SO THAT I can interpret failures.

## Acceptance criteria (EARS)
- WHEN a reader opens Rollbacks THE SYSTEM SHALL state that production rollback is planned from an earlier production DeployRecord and that commit and digest come from the record, never from the request.
- WHEN a reader opens Rollbacks THE SYSTEM SHALL explain that approval and apply use the `deploy.apply` grant bound to the plan digest, decided by an owner on the fresh-login approval page.
- IF a reader wants to plan a rollback THEN THE SYSTEM SHALL show the REST call (`POST /api/v1/deploy/rollback`) and the MCP tool `mctl_rollback_deployment`, with request body marked `<TODO: confirm with author of 8780f98>`.
- WHEN a reader opens Rollbacks THE SYSTEM SHALL state that only tenants in PromoteTenants (currently `admins`) may plan a rollback and that the generic `rollback-revision` route returns `rollback_requires_grant` for those workspaces.
- WHEN a reader opens Rollbacks THE SYSTEM SHALL state that the workflow restores tag and digest together and refuses (rather than rolling back by tag alone) when the digest cannot be determined or history is unreadable.
- WHEN a reader opens MCP Tools Reference THE SYSTEM SHALL list `mctl_rollback_deployment`.

## Out of scope
- Migration guide for legacy rollback users.
- Internals of the reconciler and DeployRecord schema.
- `docs/guides/rollbacks.md` body review beyond the sections changed here.
