# Spike: Cloudflare Private Origins as the MCTL private connectivity plane

## Context

Issue mctlhq/.github#292 asks for a build-vs-integrate decision. The question is
whether Cloudflare Private Origins can carry governed agent traffic from MCTL to
tenant-private MCP servers, internal APIs and tools that have no public ingress.
Private Origins means a proxied public hostname that terminates at a private IP,
reached over Cloudflare One connectivity: Tunnel, IPsec, GRE, CNI or Mesh. If it
can, MCTL would not have to build or run its own VPN or overlay. The issue's
split is: Cloudflare owns private connectivity and network or application
security; MCTL owns delegated authority, policy, approvals, budgets, audit and
governed execution.

MCTL already runs Cloudflare as code. It runs one outbound-only Cloudflare
Tunnel behind an Access service-token application (`events-valkey.mctl.ai`), and
it fronts six MCP upstreams through the Cloudflare MCP Portal. An mctl-owned MCP
gateway is also being designed (`docs/plans/mcp-gateway.md`). The spike must
place Private Origins against these existing mechanisms. The deliverable is a
spike report, a `SpikeDefinition` manifest and a bounded POC design. Nothing
changes in production.

## User stories

- AS the platform owner I WANT a documented verdict (ADOPT / POC / COMPLEMENTARY / NO_GO) on Cloudflare Private Origins SO THAT I can decide not to build an MCTL-owned VPN or overlay.
- AS a tenant operator with a private MCP server I WANT a documented onboarding flow that needs no public ingress SO THAT I can expose a tool to governed MCTL agents without opening my network.
- AS a security reviewer I WANT the trust boundaries, fail-closed behaviour, isolation, identity propagation and revocation stated explicitly SO THAT Cloudflare is never mistaken for a policy authority.
- AS the implementer of the next slice I WANT a minimal POC design with cost estimates and concrete follow-up issues SO THAT the experiment is bounded and reversible.

## Acceptance criteria (EARS)

- WHEN the spike is delivered THE SYSTEM SHALL contain `docs/spikes/cloudflare-private-origins.md`, `roadmap/spikes/cloudflare-private-origins.yaml` and an `AGENTS.md` "Spikes" entry linking the report.
- WHEN `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` runs THE SYSTEM SHALL accept the new manifest. The manifest has `kind: SpikeDefinition`, `lifecycle: proposed`, issue `mctlhq/.github#292`, outcomes `ADOPT`, `POC`, `COMPLEMENTARY`, `NO_GO`, and `evidence.report` pointing at the report.
- WHEN the report states a verdict THE SYSTEM SHALL label it "proposed". The owner's decision is not recorded by the agent, and the manifest stays `lifecycle: proposed`.
- WHEN the report makes a claim THE SYSTEM SHALL tag it `[CODE]` (read at a pinned commit), `[DEPLOYED]` (observed through mctl tools or gitops), `[DOC]` (Cloudflare or issue text, with URL) or `unknown (not observed)`. An unobserved fact is never reported as absent.
- THE SYSTEM SHALL answer each of the issue's ten investigation points in its own numbered section:
  1. capabilities, availability, prerequisites, pricing and connectivity modes;
  2. overlap and gaps with today's MCTL connectivity;
  3. a tenant-private MCP server without public ingress;
  4. onboarding, bootstrap and trust boundaries;
  5. fail-closed behaviour;
  6. isolation, identity propagation, audit correlation and revocation;
  7. alternatives;
  8. what MCTL still owns;
  9. private-to-private;
  10. POC design and cost.
- THE SYSTEM SHALL include a responsibility table with two sides: networking responsibilities MCTL can avoid owning, and responsibilities that stay with MCTL. The table names the MCTL component that keeps each retained one (for example mctl-api, the planned MCP gateway, mctl-gitops OpenTofu).
- THE SYSTEM SHALL compare at least four connectivity options, each with prerequisites, tenant-side footprint, MCTL-side footprint, isolation unit and lock-in:
  - Private Origins in MCTL's Cloudflare account;
  - Private Origins in the tenant's own Cloudflare account;
  - plain Cloudflare Tunnel with a public hostname and Access, as already used by `infrastructure/cloudflare/account/events-tunnel.tf`;
  - an MCTL-owned overlay (VPN or WireGuard).
- IF a fact cannot be verified, such as pricing, whether the MCTL account has the entitlement, or Unified Routing status, THEN THE SYSTEM SHALL record it as `unknown (not observed)` and list it under the report's open questions. It is not assumed.
- WHILE any Cloudflare component (Access, tunnel connector, Private Origins routing) is unavailable or misconfigured THE SYSTEM SHALL keep the designed outcome a failed call. It is never an unauthenticated or unpolicied call, and never a fallback path. The report shows this case by case for:
  - Cloudflare edge down;
  - connector down;
  - missing return route;
  - Access policy deleted;
  - service token revoked;
  - MCTL policy endpoint down;
  - tenant origin down.
- THE SYSTEM SHALL state that Cloudflare Access is a network admission gate only. Per-principal, per-tenant tool authority, approvals, budgets and audit stay in MCTL (mctl-api and the planned MCP gateway), consistent with `docs/plans/mcp-gateway.md`.
- WHEN the verdict is ADOPT, POC or COMPLEMENTARY THE SYSTEM SHALL list concrete follow-up issues (repository, title, dependency, priority) in a table in the style of `docs/spikes/mcp-gateway-g0.md`. The spike does not create them.
- THE SYSTEM SHALL include a POC design for one existing MCTL MCP endpoint. It names the hostname pattern, tunnel or Private Origins record, Access application and policy, the caller, the audit correlation fields, the success and failure checks, and estimated engineering and recurring cost.

## Out of scope

- Implementing any VPN, overlay network, worker fleet, tunnel, Access application, DNS record or production integration.
- Applying any OpenTofu change in `mctlhq/mctl-gitops`, or requesting the Private Origins entitlement from Cloudflare.
- Building the MCP gateway (owned by the `mcp-gateway` epic) or changing the MCP Portal.
- Creating the follow-up GitHub issues. The report lists them and the owner files them.
- Recording the owner's decision in the manifest.

## Open questions

- Pricing and plan tier for Private Origins are not published in the announcement post. Whether the MCTL Cloudflare account holds the entitlement, Cloudflare One connectivity or Unified Routing is not observable from the repositories. The report records these as unknown and the owner must ask the account team.
- Which account hosts the tenant connectivity: MCTL's (MCTL issues the connector token) or the tenant's own (MCTL holds only an Access service token)? The proposal evaluates both and recommends a default. The owner may prefer one for commercial or liability reasons.
- No current MCTL tenant is known to run a private-network MCP server. The POC therefore simulates the tenant-private origin with an existing MCTL endpoint reached only through a tunnel. Whether a real tenant is available for a second POC stage is unknown.
- Private-to-private is announced for a closed beta in early 2027 with no published API. The spike can only state the conditions under which it would reduce MCTL's scope.
