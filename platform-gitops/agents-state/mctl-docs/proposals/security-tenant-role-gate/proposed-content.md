## Tenant roles

Membership in a tenant lets you see it. Changing something also needs a minimum **role**, declared per operation:

| Role | Can |
|---|---|
| `viewer` | Read tenant resources |
| `developer` | Everything a viewer can, plus ordinary writes (deploy, domains, incidents) |
| `owner` | Everything a developer can, plus owner-only actions such as OpenClaw skills and identity files |

Platform admins pass every minimum.

The role comes from the tenant's `members[].role` in GitOps, matched on a GitHub login the platform has verified.

| Response | Meaning |
|---|---|
| `403` | Your role is below the minimum, or it is unknown or missing |
| `503` | Your role could not be read right now; retry later |

::: tip
If a write that used to work now returns `403`, ask a tenant owner to check your role.
:::
