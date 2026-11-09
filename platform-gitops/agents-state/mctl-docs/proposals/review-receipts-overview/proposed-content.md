# Proposed content: review-receipts-overview

> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE - add one entry in the appropriate write-tools group)
> **Source:** mctl-api@30ae621 (context: 857a2b8, 9435c0f)
> **version-status:** unverified, see commit SHA
> **FLAGGED: do not merge until prod availability and the argument schema are confirmed.**

---

After (new entry):

```markdown
### mctl_submit_review_assertion

Records a manual **advisory** review receipt against an open manual-mode review request. Admin only.

- Callers that are services, relayed, or surfaces are refused by the API; non-admins see the tool and get a refusal.
- A manual receipt is advisory: it never satisfies independent assurance.

<TODO: confirm with author of 30ae621 - prod availability and tool arguments>
```

---
