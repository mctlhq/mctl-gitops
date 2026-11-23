# DevLoop and release approvals are decided on the MFA-protected decide page

version-status: unverified, see commit SHA (mctl MCP not used; inbox reports mctl-api 4.170.1)

## Context
On 2026-11-18 mctl-api made the DevLoop decide page the only place a DevLoop proposal is approved. The page requires an ID token whose `amr` names `mfa` (00e9fd9). A bearer call to the DevLoop approve route, or direct `mctl-agents-approve` execution (MCP `mctl_trigger_approve`), is refused with 403 `decide_page_required` (2019361, 0453322). The refusal and `GET /api/v1/agents/dev-loop/{id}/approval` carry a `decide_url` bound to exactly that grant (00e9fd9, 236b60e); malformed links are refused (0469fed).

The release and deploy approval pages also changed: they link the tag commit, release, GitOps commit and preview host (8972d94, cb1e91d), say where a promotion goes and end with "You can close this tab." (ad889ab). Their ledger-enforcement text was changed twice (193abba, 7ae67a4); the final wording is not settled by the commits, so it is not documented here. The pages `docs/security/authorization.md`, `docs/mcp/tools-reference.md` and `docs/guides/gitops-workflows.md` were not read.

## User stories
- AS a tenant owner I WANT to know approvals happen on a page with MFA SO THAT I can complete them.
- AS a developer using an AI client I WANT to know the client must hand me a `decide_url` SO THAT I do not expect the model to approve.
- AS a platform admin I WANT to know the break-glass setting SO THAT I can restore bearer approve if needed.

## Acceptance criteria (EARS)
- WHEN a reader opens Authorization THE SYSTEM SHALL state that DevLoop approvals are decided only on the decide page, with a fresh sign-in and a second factor.
- WHEN a bearer caller tries to approve THE SYSTEM SHALL be documented as returning 403 `decide_page_required`, with the `decide_url` when the grant is pending, the page is enabled and the caller may see the grant.
- IF a reader uses MCP THEN THE SYSTEM SHALL show that `mctl_approve_dev_loop` and `mctl_trigger_approve` do not decide and that the client hands over `decide_url`.
- WHEN a reader opens Authorization THE SYSTEM SHALL state that the decide link is bound to the exact grant, context digest and content digest and that truncated links are refused with a 400 page.
- WHEN a reader opens GitOps Workflows THE SYSTEM SHALL describe the links on the release and deploy approval pages.
- WHILE `DEVLOOP_BEARER_APPROVE_ENABLED=true` THE SYSTEM SHALL be described as the operator break-glass; agent credentials stay refused. <TODO: confirm with author of 2019361 whether this is public-facing>

## Out of scope
- Ledger enforcement semantics of the release gate (wording changed in 193abba and 7ae67a4; needs author clarification).
- ZITADEL configuration; migration guide; screenshots.
