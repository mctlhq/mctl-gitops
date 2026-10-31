## Support

### `mctl_ask_support`

Ask the tenant support agent a question about your tenant. You must be a member of the tenant. The call spends the tenant's model budget.

| Parameter | Required | Description |
|---|---|---|
| `tenant` | yes | Workspace name, for example `billing` |
| `question` | yes | The question for the support agent |
| `context_id` | no | `context_id` of an earlier answer, to continue that conversation |

The call waits up to a bounded time (default 60 seconds) for the answer. If the answer is not ready, the result carries a task id; continue with `mctl_get_support_task`.

### `mctl_get_support_task`

Read one support task by `id` (the `task_id` returned by `mctl_ask_support`): its state and, once completed, the answer.

::: info Credentials
The support agent never receives your API token. mctl-api mints a short-lived token for your principal, valid only for the support agent. If it cannot be minted, the call fails instead of falling back.
:::

```text
> mctl_ask_support(tenant="billing", question="Why is my deploy pending?")
{ "task_id": "…", "state": "working" }
> mctl_get_support_task(id="…")
{ "state": "completed", "answer": "…" }
```
