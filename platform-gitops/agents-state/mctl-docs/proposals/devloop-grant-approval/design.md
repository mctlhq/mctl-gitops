# Design: devloop-grant-approval

## Source commits
- mctl-api:55f168c — feat(api): let a DevLoop run approve through its human's aar_ grant
- mctl-api:d2f2c71 — feat(dev-loop): approve a DevLoop through its we_-bound grant
- mctl-api:6311b05 — fix(dev-loop): let the newest grant decide a DevLoop approval
- mctl-api:dab23f3 — fix(dev-loop): refuse approval over a denied, spent or expired grant
- mctl-api:4df8488 — feat(api): audit and gate the legacy approver relay (#571)
- mctl-agents:61eb4c6 — feat(devloop): approve through WorkItem, aar_ and agent run token
- mctl-gitops:653572f — chore(mctl-api): disable the legacy DevLoop approver relay

## Current state of documentation
No page covers DevLoop approval except the pending `platform-operations-approval-flow` proposal. Related: docs/security/authorization.md.

## Proposed solution
Land `platform-operations-approval-flow` first, then add a "Grant-based approval" subsection to it (target page per that proposal; fallback docs/guides/gitops-workflows.md). Grant issuance and endpoint names are not evident from commit titles: marked TODO.

## Alternatives
- Separate security page: rejected, approval is one flow and should be read together.

## Impact
Optional mermaid sequence diagram. No sidebar change.
