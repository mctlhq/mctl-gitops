### Tenant-bound agent tokens

An agent token can be bound to a single tenant. A tenant-bound token can act only on that tenant. Call `mctl_whoami` to see which tenant a token is bound to, and pass that tenant as `team` or `tenant` to other tools.

`mctl_whoami` returns your user ID, team memberships, admin status, accessible namespaces and, for a tenant-bound agent token, the bound tenant.
