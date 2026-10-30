<!-- Target: docs/platform/tenants.md, new section -->

## Workspace profiles

`mctl_create_tenant` accepts `workspace_profile`:

| Profile | Use | Resources |
|---|---|---|
| `standard` | Administrator or pilot provisioning | Quotas from arguments (defaults: 500m CPU / 1280Mi memory requests, 3 CPU / 4Gi memory limits, 10 pods). |
| `starter` | Funded invited customers (required) | Fixed: 512Mi production and 256Mi preview memory requests, one production PVC up to 10Gi, no persistent preview disk, CPU limit 2, memory limit 1Gi. |

For `starter`, the CPU and memory limit arguments are ignored because the profile fixes them.

<!-- Target: docs/mcp/tools-reference.md, new subsection "Signup administration (admin)" -->

### Signup administration (admin)

These tools require a direct human platform administrator. Mutations need `confirm: "yes"`.

| Tool | Purpose |
|---|---|
| `mctl_signup_capacity` | Without `slots`, reads funded slots, used reservations and availability. With `slots` plus a resource-assessment `reason`, sets the funded slot count. |
| `mctl_list_signup_requests` | Reads a page of invitation requests and saved decisions. Follow `cursor` until `traversal_complete` is true. `complete=false` or `observation=partial` means some records were unreadable; it is never a clean empty queue. |
| `mctl_decide_signup_request` | Saves an immutable `approved` or `rejected` decision and emails the applicant. `reason` is included in the email. |

How slots work:

- The default is **0** funded slots. Review production and preview resources and headroom before raising it; setting slots does not resize Kubernetes or compute physical capacity.
- Approval verifies the applicant's public GitHub numeric identity and reserves one slot. With zero capacity the request is refused without granting access.
- An unused approval expires after seven days.
- Slots cannot be reduced below live reservations.

```text
mctl_signup_capacity            # read capacity first
mctl_list_signup_requests       # review the request
mctl_decide_signup_request      # decide, with an applicant-facing reason
```
