# Proposed content: mctl-agent-incident-status-lifecycle

> **Apply to:** `mctl-docs/docs/reference/troubleshooting.md` (UPDATE)
> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE)
> **Source:** mctl-agent@4ab7e7d, mctl-agent@106ef91, mctl-agent@60a9089, mctl-agent@937c7c1, mctl-agent@8c4bb92, mctl-agent@67c0cc9, mctl-agent@e04153e

---

## File 1: `docs/reference/troubleshooting.md`

### Before

```markdown
### Agent PR was not merged

Agent PRs require manual review and approval. Check:
- The PR in the `mctl-gitops` repository on GitHub
- Telegram notifications for operator approval requests
- The incident status via MCP: `"Show me details of incident INC-xxx"`

## Getting Help
```

### After

```markdown
### Agent PR was not merged

Agent PRs require manual review and approval. Check:
- The PR in the `mctl-gitops` repository on GitHub
- Telegram notifications for operator approval requests
- The incident status via MCP: `"Show me details of incident INC-xxx"`

### Incident Status Values

Incidents move through several statuses as the agent (and operators) work
them:

| Status | Meaning |
|---|---|
| `open` | New, not yet analyzed |
| `analyzing` | The agent is actively investigating |
| `escalated` | Diagnosed and handed to a human — the agent has stopped acting on it and is waiting for a decision |
| `fix_proposed` | A fix PR has been opened and is awaiting review |
| `resolved` | Closed, either automatically or by an operator |
| `suppressed` | Intentionally ignored (e.g. noisy meta-alerts) |
| `acknowledged` | A human has flagged that they're aware of it |

`escalated` and `fix_proposed` incidents that sit untouched for about a
week (7 days) auto-resolve — this keeps the incident list from
accumulating stale entries that nobody is going to act on. If an incident
you expected to still see is missing, check
[resolved incidents](/mcp/tools-reference) via `mctl_list_incidents` with
`status: resolved`.

## Getting Help
```

---

## File 2: `docs/mcp/tools-reference.md`

### Before

```markdown
## Incidents

| Tool | Description | Type |
|------|-------------|------|
| `mctl_list_incidents` | List incidents (AlertManager alerts, GitHub Actions failures, polling). Filter by team, service, status, severity | Read |
| `mctl_get_incident` | Get full incident details including evidence, analysis, and PR info. Accepts full ID or 8-char prefix | Read |
| `mctl_incident_summary` | Get aggregate counts of active incidents by status, severity, and type | Read |
| `mctl_acknowledge_incident` | Mark an incident as acknowledged. Records current user as acknowledger | Write |
| `mctl_resolve_incident` | Mark an incident as resolved with optional reason | Write |
| `mctl_trigger_incident_responder` | Run the incident responder on demand: diagnose generic incidents left in `analyzing` for over 30 minutes, write auto-accepted proposals for the Tier 2 implementer, then resolve. Same work as the scheduled run | Write |

## Domains
```

### After

```markdown
## Incidents

| Tool | Description | Type |
|------|-------------|------|
| `mctl_list_incidents` | List incidents (AlertManager alerts, GitHub Actions failures, polling). Filter by team, service, status, severity | Read |
| `mctl_get_incident` | Get full incident details including evidence, analysis, and PR info. Accepts full ID or 8-char prefix | Read |
| `mctl_incident_summary` | Get aggregate counts of active incidents by status, severity, and type | Read |
| `mctl_acknowledge_incident` | Mark an incident as acknowledged. Records current user as acknowledger | Write |
| `mctl_resolve_incident` | Mark an incident as resolved with optional reason | Write |
| `mctl_trigger_incident_responder` | Run the incident responder on demand: diagnose generic incidents left in `analyzing` for over 30 minutes, write auto-accepted proposals for the Tier 2 implementer, then resolve. Same work as the scheduled run | Write |

See [Incident Status Values](/reference/troubleshooting#incident-status-values)
for what each `status` filter value means.

## Domains
```

---
