<!-- Target: docs/guides/gitops-workflows.md, approval section (append) -->

### Approving with a content digest

`mctl_trigger_approve` (and the `mctl-agents-approve` operation behind it) requires `expected_content_digest`: the digest of the proposal content you reviewed. The approval is refused if the proposal no longer hashes to that value, so you can only approve what you actually read.

Compute it from the reviewed commit of `mctl-gitops`:

```bash
scripts/proposal-content-digest.py --rev <commit> \
  platform-gitops/agents-state/<service>/proposals/<slug>
```

The result has the form `sha256:<64 lowercase hex characters>`. Pass it unchanged:

```json
{
  "service": "mctl-api",
  "slug": "issue-42-fix-foo",
  "expected_content_digest": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

| Refusal | Meaning |
|---|---|
| `400 approval_content_unbound` | No digest was sent. |
| `400 approval_content_digest_malformed` | The value is not `sha256:` followed by 64 lowercase hex characters. |

Both refusals happen before anything is submitted, and each is recorded in the audit log as a denied approve (the refused value is not echoed or stored). Approval through a bound `aar_` grant (`mctl_approve_dev_loop`) is unchanged.

<!-- Target: docs/mcp/tools-reference.md, mctl_trigger_approve parameters -->

| Parameter | Required | Description |
|---|---|---|
| `service` | yes | Service owning the proposal. |
| `slug` | yes | Proposal directory name. |
| `expected_content_digest` | yes | `sha256:<64 hex>` digest of the reviewed content. |
| `approver` | no | Defaults to the authenticated caller. |
