# Document the required reviewed-content digest on proposal approval

## Context
mctl-api commit 6aeed3b ("require the reviewed content digest on direct approve") makes `mctl_trigger_approve` and the `mctl-agents-approve` operation require `expected_content_digest`: the digest of the proposal content the approver reviewed. Without it the call is refused before submission. The approval docs do not mention this, so anyone following them gets a 400.

version-status: unverified, see commit SHA 6aeed3b (the `mctl_trigger_approve` tool schema in the MCP tool list already shows the required parameter).

## User stories
- AS a platform admin I WANT to know how to compute and pass the digest SO THAT approving a proposal does not fail.
- AS an agent author I WANT the refusal codes documented SO THAT I can handle them.

## Acceptance criteria (EARS)
- WHEN a reader opens the approval section THE SYSTEM SHALL state that `expected_content_digest` is required for `mctl_trigger_approve` and has the form `sha256:<64 lowercase hex>`.
- WHEN a reader needs the value THE SYSTEM SHALL point to `scripts/proposal-content-digest.py` in mctl-gitops, run against the reviewed commit and proposal directory.
- IF the digest is missing THEN THE SYSTEM SHALL document the 400 `approval_content_unbound` refusal; IF malformed, 400 `approval_content_digest_malformed`.
- THE SYSTEM SHALL state that the approval grant path (`mctl_approve_dev_loop`) is unchanged and that refusals are audited.

## Out of scope
- Digest algorithm internals; legacy relay (#571) history.
