# Approving a proposal: the content digest

`cwft-mctl-agents-approve` flips a proposal from `proposed` to `accepted` only
when the caller passes `expected_content_digest`, the digest of the proposal
files that were reviewed (mctl-gitops#1979). Without it the flip refuses with
`approval_content_unbound`; a value that is not `sha256:<64 hex>` refuses with
`approval_content_digest_malformed`; files that no longer hash to it refuse
before anything is written. The refusal is printed on stderr and set as the
step's `refusal_code` output.

The digest covers `requirements.md`, `design.md`, `tasks.md` and
`proposed-content.md`, framed exactly as the CWFT and mctl-agents
`proposal_state.proposal_content_digest` frame them.
`scripts/proposal-content-digest.py --selftest` checks that the helper and the
CWFT still agree.

## Which path to use

Who may put the digest in the request body depends on the caller. A human
admin supplies it themselves; a service principal may not, because only a
grant carries a human's decision, so mctl-api takes the digest from the grant.

| Caller and path | Where the digest comes from | Action needed |
|-----------------|-----------------------------|---------------|
| DevLoop approve (`mctl_approve_dev_loop`, `POST /api/v1/agents/dev-loop/<id>/approve`) | mctl-api, from the exercised action-approval grant | none: preferred path |
| Human admin, direct REST call | the human, in the request body | compute it, see below |
| Human admin, `mctl_trigger_approve` MCP tool | nowhere yet: the tool has no digest parameter | use the REST call until mctlhq/mctl-api#722 adds it |
| Service or agent principal, no grant | not accepted: mctl-api refuses a body digest from a service principal (only a grant may carry one) | not supported; this caller's legacy relay is already refused in production |

## Manual fallback: direct approve by a human

Use this only when no DevLoopWorkflow is running for the proposal (check with
`mctl_get_dev_loop` first: signalling a live loop is the right path, and a
direct flip races it).

1. Compute the digest of the content you reviewed. Pin it to the commit you
   read, not to whatever is on disk now:

   ```bash
   git fetch origin
   scripts/proposal-content-digest.py --rev <reviewed-commit> \
     platform-gitops/agents-state/<service>/proposals/<slug>
   ```

   Without `--rev` it hashes the working tree, which is only correct if the
   checkout is exactly the reviewed commit.

2. Call the operation with your own token (the approver is taken from the
   authenticated caller):

   ```bash
   curl -sS -X POST https://api.mctl.ai/api/v1/operations/mctl-agents-approve/execute \
     -H "Authorization: Bearer $MCTL_TOKEN" -H 'Content-Type: application/json' \
     -d '{"service":"<service>","slug":"<slug>","expected_content_digest":"sha256:<64 hex>"}'
   ```

3. Confirm the commit `chore(agents): approve <slug> (<you>)` on main and that
   `.status.yaml` records `approval.content_digest` equal to the value you sent.

If the flip refuses with a mismatch, the proposal changed after you reviewed it:
review the new content and repeat with its digest. Never hand-edit
`approval.content_digest` or `approval.approved_by`; to re-approve changed
content, return the proposal to `proposed` in a PR (dropping the stale
`approval` block) and approve again.
