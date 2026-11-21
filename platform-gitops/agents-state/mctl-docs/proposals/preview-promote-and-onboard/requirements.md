# Promote a verified preview to production and onboard previews from a DeployIntent

version-status: unverified, see commit SHA (mctl MCP not used; inbox reports mctl-api 4.170.1)

## Context
On 2026-11-17 mctl-api added `POST /api/v1/deploy/promote` and MCP tool `mctl_promote_deployment` (db4dda2). A promotion is planned from a verified preview DeployRecord, applied behind an owner's `deploy.apply` grant, refused if the production values moved since the plan (a3cc4b3), and the promoted digest is compared with the preview's (5067b9d). Separately, a service with no `values.yaml` in gitops can now be planned and applied as `action=onboard` from a DeployIntent, instead of being refused with `onboard_requires_preview_onboard` (d45bcc4, 5786817).

`docs/guides/previews.md` was not read; coverage is assumed absent.

## User stories
- AS a developer I WANT to promote a tested preview SO THAT production runs exactly the image the preview ran.
- AS a tenant owner I WANT to know what I approve and when a promotion is refused SO THAT I can trust the grant.
- AS a developer I WANT to onboard a new service as a preview from a DeployIntent SO THAT I need no hand-written values.

## Acceptance criteria (EARS)
- WHEN a reader opens Previews THE SYSTEM SHALL describe promotion preconditions: preview record submitted, run succeeded, observed healthy, image digest recorded.
- WHEN a reader opens Previews THE SYSTEM SHALL state that tag and digest come from the preview record and no request field names them.
- IF a reader wants to promote THEN THE SYSTEM SHALL show `POST /api/v1/deploy/promote` and `mctl_promote_deployment` with the body marked `<TODO: confirm with author of db4dda2>`.
- WHEN a reader opens Previews THE SYSTEM SHALL state that apply is refused with `deploy_apply_not_reproducible` when the production values changed since planning.
- WHEN a reader opens Previews THE SYSTEM SHALL explain `digest_check` values `match`, `mismatch`, `unverified`.
- WHEN a reader opens Previews THE SYSTEM SHALL explain that a service without values in gitops is planned as `onboard` and needs owner approval, and that audit keeps values out.
- WHILE only the `admins` tenant may promote THE SYSTEM SHALL say so ("until the MCP gateway policy exists").

## Out of scope
- Port below 1024, chart sidecar slots (dropped items in the inbox).
- Reconciler internals, migration guides, Argo workflow internals (gitops#2746, #2740).
