# Glovo M1 staged deployment package (P0, inert)

Everything under `deploy/staged/glovo-m1/` is **not reconciled**. No Argo CD
ApplicationSet, Application or `manifest-generate-paths` matches `deploy/`.
Nothing here deploys, routes, authenticates or creates a Temporal namespace.
`*.mctl.ai` has a proxied wildcard DNS record, so any Ingress for
`glovo.mctl.ai` in a reconciled path would be public at once; that is why the
manifests stay here until P2.

Target: a multi-tenant, OAuth-protected, allowlisted fake Glovo MCP at
`https://glovo.mctl.ai/mcp`, built from three images (facade, provider worker,
control worker). Labs is a hosting workspace only, not a Glovo tenant.

## Phases

| Phase | What | Approval |
| --- | --- | --- |
| P0 | This package, runbook, render-only CI, leak guard | mctlhq/mctl-gitops#2470 |
| P1 | Runtime deployment (workers, Temporal identities, netpols) | a separate P1 issue and owner approval |
| P2 | DNS/TLS/OAuth/allowlist activation, Ingress on | a separate P2 activation GO |
| P3 | Real Glovo provider | out of scope |

`gate.yaml` is informational. It is never proof of approval and CI ignores it
as an unlock: the leak guard refuses Glovo resources in reconciled paths
regardless of its content.

## Links

- mctlhq/mctl-gitops#2457 (plan), #2470 (this slice)
- mctlhq/.github#324 (owner epic)
- mctlhq/mctl-gitops#2469 (Temporal client RBAC spike)
- mctlhq/mctl-api#968 (bridge, `docs/bridge.md`); mctlhq/mctl-agents#1043 is
  the earlier bridge spike, kept as history
- mctlhq/mctl-api#953, #954
- mctlhq/mctl-telegram#1048

Contract and readiness crosswalk: [`CROSSWALK.md`](CROSSWALK.md) (slice
map, mismatches, ordered gates to P1; informational, not an approval).

ZITADEL client of the basket approval page (mctlhq/mctl-api#1006):
[`zitadel-client.patch.md`](zitadel-client.patch.md), text only; it lands in
zitadel-iac, which applies to production on merge, only at activation.

## Obsolete staged artifacts (bridge-only provider)

Since the provider worker became a #968 bridge client (mctlhq/mctl-telegram#1262)
it holds no Temporal credential. Until a P1 prep PR replaces them:

- `netpol/worker-to-temporal.yaml` is obsolete: the provider needs egress to
  the mctl-api bridge only.
- The provider namespace part of `temporal-namespaces.patch.md` is obsolete;
  the control worker namespace stays.
- `GLOVO_TEAM_FALLBACK` in `compatibility.yaml` is obsolete: the joint
  contract has one kill switch, `GLOVO_ENABLED`, and no team fallback.

See CROSSWALK.md M14-M16.

Runbook: `docs/runbooks/glovo-m1.md`. Validator:
`scripts/validate-glovo-m1-staging.py`.
