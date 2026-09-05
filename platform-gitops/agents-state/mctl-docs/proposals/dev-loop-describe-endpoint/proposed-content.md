# Proposed content: dev-loop-describe-endpoint

> **Apply to:** `mctl-docs/docs/api/index.md` (UPDATE)
> **Source:** `mctl-api@d6aca27`
> **Version-status:** unverified exact REST contract — this proposal marks the HTTP
> method, path, and response shape as `<TODO: confirm with author of d6aca27>`. The
> feature itself is confirmed shipped (mctl-api 4.37.0, same release window as the
> `platform-operations-approval-flow` commits).

## Before (illustrative — exact surrounding heading may differ; `docs/api/index.md`
currently has no DevLoop section at all)

```markdown
## Authentication

All REST endpoints require a bearer token — see [Authentication](/security/authentication).

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/agent-runs` | List recent mctl-agents pipeline runs |
| ... | ... | ... |

## Rate limits
```

## After (insert a "DevLoop" subsection before the existing "Rate limits" heading, or
as a new row group in the endpoints table if the page uses a single flat table)

```markdown
## Authentication

All REST endpoints require a bearer token — see [Authentication](/security/authentication).

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/agent-runs` | List recent mctl-agents pipeline runs |
| ... | ... | ... |

## DevLoop

::: tip Admin-only diagnostics
DevLoop endpoints are used to inspect the lifecycle of `mctl-agents` DevLoopWorkflow
executions. They require the same admin-level authentication as other platform
diagnostics endpoints.
:::

### Check workflow liveness — `describe`

Reports whether a DevLoop workflow execution is still alive. Useful before deciding
whether to approve a proposal via the durable
[`mctl_approve_dev_loop` Temporal-signal path](/guides/gitops-workflows#approving-agent-proposals)
(only effective while the workflow is live) or the direct `mctl-agents-approve`
operation (works regardless of liveness).

**Method / path:** `<TODO: confirm with author of d6aca27 — exact HTTP method and
REST path, e.g. GET /api/v1/dev-loop/{id}/describe>`

**Auth:** admin-only.

**Response:** `<TODO: confirm with author of d6aca27 — exact response field names,
e.g. a boolean liveness flag and workflow/run identifier>`

```bash
curl -sS \
  -H "Authorization: Bearer $MCTL_TOKEN" \
  "https://api.mctl.ai/<TODO: confirm with author of d6aca27>" | jq .
```

## Rate limits
```

---

> **Note for implementer:** confirm the exact method/path/response shape against
> `mctl-api` source for commit `d6aca27` before publishing, and replace both
> `<TODO: confirm with author of d6aca27>` markers with the real values. Do not guess
> the REST path — the existing endpoints table in `docs/api/index.md` should be used
> as the pattern to match (versioned `/api/v1/...` prefix, per the pre-existing
> `/api/v1/agent-runs` entry noted in the `mcp-agents-tools` proposal).
