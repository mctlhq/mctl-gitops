# Proposed content: mcp-portal-tool-exposure

> **Source:** mctl-api@f95ce9b, mctl-api@3b68ce3

This proposal touches two locations. Each block below states its own
**Apply to** target and mode.

---

## Block 1

> **Apply to:** `mctl-docs/docs/mcp/overview.md` (UPDATE)
> **Source:** mctl-api@3b68ce3

**Before** (excerpt):

```markdown
## How Access Works

Authentication follows a three-step model:

1. **Token validated per request** — your GitHub token or OAuth credential is checked on every MCP call. The server never stores tokens.
2. **Team-scoped access** — access is limited to workspaces resolved from your GitHub team memberships in the GitOps repo. Admins can operate on all tenants.
3. **Full audit trail** — every write operation submits an Argo Workflow that produces a git commit. All changes are traceable and reversible.

For detailed auth information, see [Authentication](/security/authentication).

## Tool Annotations
```

**After:**

```markdown
## How Access Works

Authentication follows a three-step model:

1. **Token validated per request** — your GitHub token or OAuth credential is checked on every MCP call. The server never stores tokens.
2. **Team-scoped access** — access is limited to workspaces resolved from your GitHub team memberships in the GitOps repo. Admins can operate on all tenants.
3. **Full audit trail** — every write operation submits an Argo Workflow that produces a git commit. All changes are traceable and reversible.

For detailed auth information, see [Authentication](/security/authentication).

## Connecting Directly vs. Through the Portal

There are two ways to reach MCTL's MCP tools:

- **Direct connection** — an MCP client (Claude Code, Cursor, VS Code, etc.)
  connects straight to `https://api.mctl.ai/mcp`, as described on
  [Connecting](/mcp/connecting).
- **Shared MCP portal** — a Cloudflare-fronted aggregate that re-exposes
  tools from multiple upstream MCP servers (including `mctl-api`) behind
  one endpoint, used by portal-connected surfaces such as the Backstage
  developer portal.

As of 2026-09-12, the portal aggregate exposes **every** `mctl-api` tool —
not a curated read-only subset as it did previously. Widening what's
*visible* through the portal does not widen what's *permitted*: `mctl-api`'s
own authentication, team-scope, and role checks (the same three steps
above) decide whether a call actually succeeds, regardless of which path it
arrived through. Seeing a tool listed through the portal is not the same as
being authorized to call it successfully.

## Tool Annotations
```

---

## Block 2

> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE)
> **Source:** mctl-api@f95ce9b

Insert a new section directly after the existing `## Repositories` section
and before `## Agent Registry` (a natural home: a narrow, admin-only,
single-tool section, matching the size and placement style of the other
small sections on this page).

**Before** (excerpt):

```markdown
### `POST /api/v1/repos/sync`
```

(the `mctl_sync_repos` row in the existing `## Repositories` table is
immediately followed by `## Agent Registry`)

**After** — insert this new section between `## Repositories` and
`## Agent Registry`:

```markdown
## MCP Portal Administration

| Tool | Description | Type |
|------|-------------|------|
| `mctl_trigger_portal_server_auth_apply` | Dispatch the workflow that applies the committed OAuth registration for the Cloudflare MCP portal's upstream servers | Write |

### `mctl_trigger_portal_server_auth_apply`

Dispatches `mctl-gitops`' `portal-server-auth-apply.yml`: applies the OAuth
registration (issuer/authorization/token/revocation endpoints, client
registration, and requested scope) already committed at
`infrastructure/cloudflare/portal/mcp-portal-server-auth.json` in
`mctl-gitops`, for the Cloudflare MCP portal's upstream servers.

**This call writes nothing to Cloudflare.** It only starts a GitHub Actions
run:

1. The run's **plan** job reads the live Cloudflare registration and
   publishes a per-field comparison against the committed file.
2. The run's **apply** job then waits for a required reviewer on the
   `cloudflare-apply` GitHub Actions environment, and refuses to proceed if
   the live registration changed after approval.

Use it when the committed registration file has changed (a scope was
widened or narrowed) or when a drift check reports the live registration no
longer matches it. To change *what* gets applied, open a pull request
against the committed file in `mctl-gitops` — this tool only applies what
is already on `main`.

After an approved apply, any upstream session must be signed out and back
into the portal — a token refresh is intersected with the session's
original grant, so a widened scope does not reach an already-live session.

**Parameters:** none.

**Returns:**

```json
{
  "repo": "mctlhq/mctl-gitops",
  "workflow": "portal-server-auth-apply.yml",
  "ref": "main",
  "runs_url": "https://github.com/mctlhq/mctl-gitops/actions/workflows/portal-server-auth-apply.yml",
  "message": "Dispatched portal-server-auth-apply.yml on main. Nothing has been written to Cloudflare yet: the run's plan job publishes the live-vs-committed comparison, and the apply job waits for a required reviewer on the cloudflare-apply environment. Open the run to read the plan and approve it. After an apply, the upstream must be signed out and back in in the portal — a refresh cannot widen an existing grant."
}
```

No run id is returned — the dispatch API itself doesn't provide one at
call time — so `runs_url` (the workflow's run list) is the link to follow
to find and approve the new run.

Admin-only. Annotated **non-destructive**: what the tool *starts* is
gated behind human approval, even though what the underlying workflow
*can eventually do* (rewrite the portal's live OAuth registration) is
infrastructure-affecting.

**Example:**

```
mctl_trigger_portal_server_auth_apply()
# → { "repo": "mctlhq/mctl-gitops", "workflow": "portal-server-auth-apply.yml",
#     "ref": "main", "runs_url": "https://github.com/mctlhq/mctl-gitops/actions/workflows/portal-server-auth-apply.yml",
#     "message": "Dispatched portal-server-auth-apply.yml on main. ..." }
```
```

Also update the tool-count banner at the top of the page:

**Before:**

```markdown
The MCTL MCP server exposes 70 tools for managing your infrastructure. Each tool is annotated as **read-only**, **write**, or **destructive**.
```

**After** (coordinate this exact number with `proposals/lifecycle-ownership/`
— both add one tool this cycle; bump once for both):

```markdown
The MCTL MCP server exposes 72 tools for managing your infrastructure. Each tool is annotated as **read-only**, **write**, or **destructive**.
```

<!-- <TODO: confirm the exact new read-only/write/destructive split with
     the mctl-api maintainer before publishing — this proposal adds one
     write tool (mctl_trigger_portal_server_auth_apply); the sibling
     lifecycle-ownership proposal adds one read-only tool
     (mctl_get_lifecycle_ownership); the banner on docs/mcp/overview.md
     ("70 (32 read-only, 26 write, 12 destructive)") needs both counted.> -->

---
