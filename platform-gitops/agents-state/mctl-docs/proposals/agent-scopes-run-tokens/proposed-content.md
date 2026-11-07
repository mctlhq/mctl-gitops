# Proposed content: agent-scopes-run-tokens

> **Apply to:** `mctl-docs/docs/security/authorization.md` (UPDATE - append new section; place after the existing role/permission content)
> **Source:** mctl-api@352f9f5, 48578a0, 0196447, df43377
> **version-status:** unverified, see commit SHA

---

After (new section to append):

```markdown
## Agent scopes and run tokens

Agents run by the platform call the API with a short-lived **run token** instead of a static service token. A run's pod exchanges its projected ServiceAccount token at `POST /api/v1/agent-run-tokens/exchange`; the exchange template decides the agent and its **scope**. <TODO: confirm with author of 352f9f5 - request/response shape of the exchange>

A scope is an allow-list of routes. Two rules apply to every scope:

- **Intents are always denied.** Scoped agent tokens of every scope are refused the work-item intents route.
- **Approvals need a scoped token.** Action-approval routes are available only to a scoped run token bound to an execution. An unscoped token that happens to be bound to an execution gets no approval access.

### The `implement` scope

Used by the `mctl-agents-implement` template (agent `implementer`). It shares the read routes of the `investigate` scope and adds four action-approval routes:

| Route | Purpose |
|---|---|
| `POST /api/v1/action-approvals` | request an approval for the run's own execution |
| `GET /api/v1/action-approvals/{id}` | read an approval of its own execution, or that execution's DevLoop grant |
| `POST /api/v1/action-approvals/{id}/consume` | spend its own approval |
| `POST /api/v1/action-approvals/{id}/execute` | mark its own approval (or the execution's DevLoop grant) executed |

The human `.../decision` route, the approval list, and all other writes are not part of the scope.

::: warning Execution required
The `mctl-agents-implement` template does not allow runs without an execution. A run submitted without an `execution_id` is refused at exchange with `workflow_without_execution`.
:::

See [Action approvals](/api/#action-approvals) for the exact per-route rules.
```

<TODO: confirm with author of 352f9f5 that `/api/#action-approvals` anchor matches the section added by proposal `action-approvals-execution-bound`.>

---
