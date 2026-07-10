---
name: mctl-platform
description: MCTL platform operations, troubleshooting, and MCP OAuth recovery. Use for deploying or inspecting mctl services, platform incidents, workflow verification, and MCP startup, handshake, or authorization failures.
---

# MCTL Platform

Use this skill for MCTL platform operations and troubleshooting through the
`mctl` MCP server at `https://api.mctl.ai/mcp`.

## Operating Model

- Treat MCTL as a GitOps platform: write operations trigger Argo Workflows and
  usually produce Git commits consumed by ArgoCD.
- Prefer `mctl_*` tools for platform state and operations.
- Confirm before retiring a service, deleting a tenant, or changing shared
  infrastructure.
- For every write operation that returns `workflow_name`, check its final status
  before reporting success.
- Stay within the user's tenant and team scope.

## MCP OAuth Startup Failure

Apply this procedure when MCP startup or initialization contains all or part of:

```text
MCP client for `mctl` failed to start
handshaking with MCP server failed
Auth error: OAuth authorization required
```

Treat this first as missing or stale OAuth credentials in the local Codex
client. The server reached the initialize request and requested authorization;
do not initially diagnose this as a Kubernetes, network, transport, or
`mctl-api` outage.

1. Confirm the registered endpoint:

   ```bash
   codex mcp get mctl
   ```

   Require an enabled server with URL `https://api.mctl.ai/mcp`. Do not add a
   bearer-token environment variable, custom authorization header, or manually
   copied access token for the normal OAuth flow.

2. Start OAuth and keep the command running:

   ```bash
   codex mcp login mctl
   ```

3. Open the printed authorization URL in the user's browser and approve access.
   The CLI listens on a temporary localhost callback. Never expose, log, or
   persist the authorization code or OAuth tokens manually.

4. Require the definitive CLI result:

   ```text
   Successfully logged in to MCP server 'mctl'.
   ```

5. Restart Codex or open a new Codex session. A session whose MCP startup already
   failed may not hot-reload credentials; MCP initialization must run again.

6. Verify the fresh session with a read-only call such as `mctl_whoami`.
   `codex mcp list` may still show `Auth: Unsupported` for a streamable HTTP
   server after a successful OAuth login, so do not treat that label alone as a
   failure.

If a fresh session still receives `OAuth authorization required`, refresh the
local credentials once:

```bash
codex mcp logout mctl
codex mcp login mctl
```

Only after a fresh login and fresh Codex session still fail, inspect the
server-side OAuth discovery and client-registration configuration plus
`mctl-api` logs. Include the exact initialize error, but never credential files,
tokens, or authorization codes.

## Platform Troubleshooting

- For an unhealthy service, inspect status, recent logs, resource usage, and the
  workflow that last changed it.
- For ArgoCD sync, health, rollout, or stale-drift incidents, use the
  `argocd-health-remediation` platform skill.
- Prefer the smallest reversible GitOps fix over imperative live-state changes.
