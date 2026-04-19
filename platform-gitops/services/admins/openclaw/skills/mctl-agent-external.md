---
name: mctl-agent-external
description: Handle mctl-agent webhook remediation sessions. Use for claim-first incident runs and exactly-one callback result discipline.
---

# MCTL Agent External

- This skill applies to webhook sessions from `mctl-agent`.
- Never auto-claim `ticket.created`.
- For `ticket.fix_failed` and `ticket.escalated`, claim first via `mctl_agent_external`.
- Before claim succeeds, do not read workspace files or do broad exploration.
- After claim, gather evidence with `mctl_*` tools first.
- Send exactly one callback result after a successful claim.
- Use `pr_created` only when a real PR exists with a concrete PR URL; otherwise return `needs_human` or `failed`.
