# Proposed content: mcp-stats-app

> **Apply to:** `mctl-docs/docs/mcp/stats-app.md` (CREATE)
> **Source:** mctl-api@db5757f, 39a0453, e8f7898, 8308e83, 77dd77e, 754b897
> **version-status:** unverified, see commit SHA

---

```md
---
title: Statistics MCP App
---

# Statistics MCP App

The statistics MCP App is a **read-only** dashboard delivered through MCP resources. It lets an MCP client that supports MCP Apps display platform statistics without calling individual tools.

## What it shows

<TODO: confirm with author of db5757f: list of panels/metrics>

## Scoping

Statistics are scoped to the teams you belong to. <TODO: confirm with author of 39a0453: how multiple teams are combined or selected>

## How numbers are computed

- Closed incidents are counted by resolver and by resolution day. <TODO: confirm exact wording with author of 754b897/77dd77e>
- Memory quantities support decimal values (e.g. fractional units) and are displayed accordingly. <TODO: confirm with author of the decimal-quantity fix>

## Opening the app

<TODO: confirm with author of db5757f: resource URI and client steps>

The app is read-only: it cannot change platform state.

## Related
- [MCP overview](/mcp/overview)
- [MCP tools reference](/mcp/tools-reference)
```

---

## Patch: `docs/mcp/overview.md` (UPDATE)

Before: no mention of MCP Apps.

After (append a section):
```md
## MCP Apps
- [Statistics app](/mcp/stats-app) — read-only statistics dashboard.
```
