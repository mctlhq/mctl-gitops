# Design: devloop-decide-page-mfa

version-status: unverified, see commit SHA

## Source commits
- mctl-api:00e9fd9 — feat(api): require MFA on the DevLoop decide page, hand out decide_url
- mctl-api:2019361 — fix(api): decide DevLoop approvals on the decide page only
- mctl-api:0453322 — fix(api): refuse direct mctl-agents-approve without the decide page
- mctl-api:236b60e — fix(api): gate the refusal decide_url on grant visibility
- mctl-api:0469fed — fix(api): refuse a decide link whose binding is not exact
- mctl-api:46569d7 — fix(api): keep a closed DevLoop grant's state refusal; lint
- mctl-api:8972d94 — feat(api): link tag commit and release on the release approval page
- mctl-api:193abba — fix(release): say on the approval page that the ledger is enforced
- mctl-api:ad889ab — fix(approval-page): fit long hashes, say where a promotion goes, end with close-tab
- mctl-api:7ae67a4 — fix(api): stop release page claiming the gate enforces the ledger
- mctl-api:cb1e91d — feat(api): show commits and preview host as links on the deploy approval page

## Current state of documentation
- `docs/security/authorization.md`, `docs/mcp/tools-reference.md`, `docs/guides/gitops-workflows.md` exist (titles only known). Likely silent on the decide page.
- Related existing proposals: `devloop-grant-approval`, `action-approvals-execution-bound`, `approve-content-digest`; the implementer should check overlap and merge wording.

## Proposed solution
UPDATE authorization.md with a "Approving DevLoop proposals" section; UPDATE tools-reference.md notes for `mctl_approve_dev_loop` and `mctl_trigger_approve`; UPDATE gitops-workflows.md with an "Approval pages" subsection. Open questions are TODO-marked (final ledger wording, `DEVLOOP_BEARER_APPROVE_ENABLED` exposure).

## Alternatives
- New page `docs/security/approvals.md`: reasonable if overlap with existing proposals makes authorization.md too long; dropped to keep one change set.
- Document only the MCP tools: dropped, the behaviour change is a security rule.

## Impact
- No sidebar change unless the alternative is chosen.
- Mermaid sequence diagram included.
- Applies to main; no versioning.
