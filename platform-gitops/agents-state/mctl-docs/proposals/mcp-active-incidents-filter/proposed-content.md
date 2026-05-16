# Proposed content: mcp-active-incidents-filter

> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE)
> **Source:** mctl-api@a8cdba5
> **version-status:** unverified — mctl-api 4.18.4 confirmed shipped via mctl-gitops a61f047 2026-05-13; mcp__mctl__* tools unavailable.

Apply mode is UPDATE. Two targeted additions to an existing page. The implementer
must read the current file first and locate the relevant tool entries before
applying either diff.

---

## Change 1: Update the incidents / alerts listing tool — `status` parameter

Locate the tool entry for the incidents / alerts listing MCP tool.
<TODO: confirm exact tool name with author of mctl-api:a8cdba5 — likely
`mctl_list_incidents` or `mctl_list_alerts`>

### Before (assumed — locate the `status` parameter row or add it if absent)

```markdown
| `status` | string | optional | Filter incidents by status. |
```

_(If no `status` parameter row exists at all, insert the After block as a new row.)_

### After

```markdown
| `status` | string | optional | Filter incidents by status. Accepted values: `active` (default — all non-terminal states), plus any specific terminal or state values supported by the server. When omitted, defaults to `active`. |
```

Additionally, add the following note immediately after the parameter table for
this tool:

```markdown
> **`status=active` (default, mctl-api 4.18.4+)**
>
> The `active` value is a virtual filter that matches all non-terminal incident
> states (open, acknowledged, escalated, and any other states that are not
> resolved or closed). It is the server-side default when you omit the `status`
> parameter entirely.
>
> To list only incidents in a specific state, supply that state value explicitly.
> To list all incidents regardless of state, <TODO: confirm whether an explicit
> "all" value exists or whether the caller must make multiple filtered calls —
> confirm with author of mctl-api:a8cdba5>.
```

And add an example call after the note:

```markdown
**Example — list all active incidents (explicit):**

```json
{
  "tool": "mctl_list_incidents",
  "arguments": {
    "status": "active"
  }
}
```

**Example — same result, relying on the default:**

```json
{
  "tool": "mctl_list_incidents",
  "arguments": {}
}
```
```

---

## Change 2: Add audit `env_vars` redaction note to the workflow retrieval tool

Locate the tool entry for the workflow retrieval MCP tool.
<TODO: confirm exact tool name with author of mctl-api:a8cdba5 — the REST handler
is `GetWorkflow`; the MCP tool name may be `mctl_get_workflow` or similar>

Find the section describing the response shape or the audit entries returned by
this tool. Add the following callout immediately before or after the response
field descriptions:

### After (add this callout)

```markdown
> **Security: `env_vars` fields are redacted (mctl-api 4.18.4+)**
>
> Audit entries returned by this tool have their `env_vars` fields redacted
> before being sent to the caller. The field will be present in the response
> but will not contain raw environment variable values. This is a deliberate
> security measure to prevent secrets from leaking through the audit trail.
>
> If your automation previously read secret values from `env_vars` audit fields,
> it must be updated — those values are no longer available via this endpoint.
```

---
