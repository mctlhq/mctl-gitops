# Glovo M1: fake multi-tenant Glovo MCP (P0 package, P1/P2 gates)

Source: mctlhq/mctl-gitops#2470, plan #2457, epic mctlhq/.github#324.
Staged manifests: `deploy/staged/glovo-m1/` (not reconciled).
Validator: `scripts/validate-glovo-m1-staging.py` (CI job `glovo-m1`).

## Why it is inert

The `apps` ApplicationSet syncs every `platform-gitops/services/*/*` with
prune and selfHeal, and `*.mctl.ai` has a proxied wildcard DNS record, so any
values file or Ingress for `glovo.mctl.ai` in a reconciled path is public
within about 30 seconds. P0 therefore keeps everything under `deploy/`, and CI
refuses Glovo references in `platform-gitops/**` (excluding `agents-state/`).

`gate.yaml` is informational. It is editable by the PR author, so neither CI
nor reviewers treat it as approval. Activating P1 or P2 needs a trusted owner
grant, bound to phase, environment, manifest digest and image digest, verified
outside PR-modifiable content, plus its own PR that changes the CI policy. Until
such a verifier exists, P1/P2 stay BLOCKED.

## Phase map and evidence

| #2470 acceptance area | Phase | Evidence slot |
| --- | --- | --- |
| Manifests render and pass kubeconform | P0 | CI `glovo-m1` job |
| Nothing deployed, no new Application or Temporal namespace | P0 | comment on #2470 after merge |
| Provider has no Ingress/LB/NodePort | P0 | validator selftest |
| Kill switch, empty allowlist, team fallback off | P0 | validator selftest |
| Digests, SBOMs, source commits | P1 | `provenance.yaml` filled, verified by P1 policy |
| Temporal identities and namespaces | P1 | #2469 live evidence |
| Runtime canary | P1 | kuptsi and DevLoop canary green |
| DNS, TLS, OAuth, allowlist | P2 | P2 activation GO |
| Real Glovo provider | P3 | out of scope |

## P1 checklist

- #2469 live evidence filled (Temporal client authentication proven).
- JWT, TLS and authorizer slices merged and verified.
- mctl-agents#1043 bridge verified.
- Digests and SBOMs present for facade, provider and control images.
- kuptsi and mctl-agents DevLoop canary green before and after.
- Labs quota headroom checked; the provider tenant has its own quota.
- Separate P1 issue with explicit owner approval and the trusted grant.

## P2 checklist

- `glovo.mctl.ai: [labs]` added to `reservedPlatformHosts` in the same PR as
  the Ingress (`docs/runbooks/reserved-hosts.md`). Consider adding
  `glovo.mctl.ai: []` earlier as separate hardening.
- Certificate `glovo-mcp-tls` issued by `letsencrypt-prod`.
- Pilot allowlist and one explicit team tenant named. Personal scope is
  unsupported. Labs is a hosting workspace only.
- MCP portal entry: decide yes or no.
- Separate P2 activation GO.

## Negative test matrix (run in P1/P2, not in P0)

- Two tenants with distinct users cannot see each other.
- Foreign connection and order access is denied.
- Missing or wrong audience, and an expired JWT, are rejected.
- A revoked install is rejected.
- A replayed `aar_` is rejected.
- The provider cannot call control or DevLoop.
- Fake basket idempotency holds.

## MCP client smoke test (P2)

Connect a real MCP client to `https://glovo.mctl.ai/mcp`, complete OAuth with
an allowlisted user of the pilot team, list tools, create and read a fake
basket. Repeat with a non-allowlisted user and expect denial.

## OTel signals

Use the base-service `otel` block. Expect request count and latency per tool,
auth failures by reason, kill-switch denials, per-team rate-limit hits and
cost-cap hits. Alert on a rise in auth failures and on any request from a
non-allowlisted user that is not denied.

## Budgets and canary

See `deploy/staged/glovo-m1/budgets.yaml`: rate limits, cost cap, one team,
a few users.

## Kill switch

1. Set `GLOVO_ENABLED: "false"` in the facade values (fail closed), or clear
   `GLOVO_ALLOWLIST`.
2. If needed set `ingress.enabled: false`.

## Rollback

P0: revert the P0 PR; there is no cluster state. P1/P2: flip the kill switch
first, then revert the activation PR so Argo CD prunes. Check that the
Temporal namespaces and DNS records added by the phase are removed by their
own PRs.
