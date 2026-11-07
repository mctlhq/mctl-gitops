# Design: agent-scopes-run-tokens

version-status: unverified, see commit SHA

## Source commits
- mctl-api:352f9f5 - feat(auth): add implement agent scope and exchange template
- mctl-api:48578a0 - fix(auth): apply the intents route deny to every agent scope
- mctl-api:0196447 - fix(approvals): scoped tokens only, service-requested grant, no key-conflict leak
- mctl-api:df43377 - docs(approvals): agent approval access needs a scoped run token

## Current state of documentation
- `docs/security/authorization.md` exists (per docs-tree 2026-04-27). Its current content was not re-read; it is presumed to lack agent scopes. Implementer must check for overlap first.

## Proposed solution
UPDATE `docs/security/authorization.md`: append a section "Agent scopes and run tokens" (see proposed-content.md). Source of truth: mctl-api `docs/implement-agent-scope.md` at 352f9f5 and commit bodies. Cross-link to the action-approvals section (proposal `action-approvals-execution-bound`).

## Alternatives
- Standalone `docs/security/agent-scopes.md`: dropped, content is short and tied to Authorization; revisit if more scopes are documented.
- Skip as internal: dropped, tokens/scopes affect integrators' security posture.

## Impact
- Sidebar/nav: none for an update.
- Mermaid: none required.
- Versioning: applies to the mctl-api release containing 352f9f5 (latest tag seen 4.154.0, unverified).
