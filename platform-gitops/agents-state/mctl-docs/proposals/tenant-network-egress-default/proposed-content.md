# Proposed content: tenant-network-egress-default

> **Apply to:** `mctl-docs/docs/guides/tenants.md` (UPDATE)
> **Source:** mctl-api@6cc17bb

---

## Before

```markdown
### Via Self-Service Form

Visit [mctl.ai](https://mctl.ai) and use the tenant creation form. You'll need to authenticate with GitHub first.

## List Tenants
```

## After

```markdown
### Via Self-Service Form

Visit [mctl.ai](https://mctl.ai) and use the tenant creation form. You'll need to authenticate with GitHub first.

### Network Policy

New tenant namespaces **deny outbound internet egress by default**. Pods
inside your tenant can talk to each other and to other in-cluster
services, but cannot reach the public internet unless you opt in.

To allow it, set `allow_internet_egress` when creating the tenant:

```
"Create a new tenant called backend-team with internet egress allowed"
```

Or pass it explicitly to `mctl_create_tenant`:

| Parameter | Value | Effect |
|---|---|---|
| `allow_internet_egress` | `"false"` (default) | Tenant pods cannot reach the public internet |
| `allow_internet_egress` | `"true"` | Tenant pods can make outbound requests to external hosts/APIs |

This only affects your **application pods**. Argo Workflow pods (the ones
that build and deploy your services) always have internet access,
regardless of this setting — your builds and deploys are never blocked by
it.

If you created a tenant before this setting existed, or need to change it
after creation, ask a platform admin — there is currently no self-service
MCP tool to update the flag on an existing tenant.

## List Tenants
```

---
