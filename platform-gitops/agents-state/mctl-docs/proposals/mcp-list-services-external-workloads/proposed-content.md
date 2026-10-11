### `mctl_list_services`

Lists catalogue services and every ArgoCD application deployed into a team's namespace. Optional `team` filter.

Each row has `managed`:

| Value | Meaning |
|---|---|
| `catalogue` | Onboarded through mctl. Deploy, rollback and scale apply. |
| `external` | Deployed by the team's own ArgoCD project. Read-only here. |
| `platform` | Deployed by the platform into the team namespace. Read-only here. |

Rows carry sync status, health, hosts and images.

::: warning Incomplete is not empty
If `complete` is `false`, ArgoCD could not be read. Only catalogue rows are listed, and sync, health and hosts are unknown. A `warning` field says so.
:::

The manifest source of `platform` rows is hidden from non-admins.
