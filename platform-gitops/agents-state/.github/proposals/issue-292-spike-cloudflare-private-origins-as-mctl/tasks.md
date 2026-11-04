# Tasks: issue-292-spike-cloudflare-private-origins-as-mctl

- [ ] 1. Pin evidence. Record the 40-hex commits of `mctlhq/.github` and `mctlhq/mctl-gitops` that were read. Re-fetch https://blog.cloudflare.com/private-origins-public-to-private/ and the Cloudflare Private Origins developer docs (limitations, prerequisites), noting fetch dates. — DoD: an evidence pins table exists in the report draft; every external fact has a URL and date.
- [ ] 2. Write sections 1 to 3 of `docs/spikes/cloudflare-private-origins.md` (depends on 1):
  1. capabilities, availability, prerequisites and modes, with pricing and entitlement marked `unknown (not observed)`;
  2. overlap with `infrastructure/cloudflare/account/events-tunnel.tf`, `platform-gitops/infra-components/data/valkey/cloudflared.yaml`, the MCP Portal (`infrastructure/cloudflare/portal/mcp-servers.tf`) and `docs/plans/mcp-gateway.md`;
  3. tenant-private MCP feasibility.

  — DoD: every claim carries an evidence tag; the overlap section shows explicitly that Tunnel already gives public-hostname-to-private-origin.
- [ ] 3. Write sections 4 to 6 (depends on 2):
  4. onboarding in MCTL-account mode and tenant-account mode, with a trust-boundary diagram;
  5. the fail-closed matrix, covering at least: edge down, connector down, missing return route, Access app or policy deleted, service token revoked or expired, MCTL policy endpoint down, tenant origin down;
  6. isolation unit, identity propagation, audit correlation (`Cf-Ray` plus gateway ids) and three independent revocation levers.

  — DoD: every matrix row ends in "call fails" or names the gap and its mitigation.
- [ ] 4. Write sections 7 to 9 (depends on 3):
  7. the alternatives matrix: Private Origins in MCTL's account, Private Origins in the tenant's account, plain Tunnel with Access, MCTL-owned overlay; each with prerequisites, tenant and MCTL footprint, isolation unit and lock-in;
  8. the responsibility table (avoid-owning vs still-owned, with the owning component);
  9. private-to-private as a re-open trigger.

  — DoD: the table answers the issue's "which networking responsibilities MCTL can avoid owning, which remain".
- [ ] 5. Write section 10, the POC design (depends on 4). Target `labs/coolify-mcp` through a dedicated tunnel and Access service-token app (hostname, ingress with 404 catch-all, connector manifest outline, caller, checks), plus an optional stage 2 with a Private Origins record. Add the cost estimate (engineering days, connector resources from `cloudflared.yaml`, Cloudflare cost or unknown). — DoD: the POC is fully reversible by reverting one mctl-gitops PR, and success and failure checks are listed.
- [ ] 6. Write the proposed verdict (`COMPLEMENTARY` unless the evidence in tasks 2 to 5 overturns it), re-open triggers, open questions and the follow-up issue table (repository, title, dependency, priority) (depends on 5). — DoD: the verdict is labelled "proposed, owner decides"; the follow-up table is non-empty for ADOPT, POC or COMPLEMENTARY.
- [ ] 7. Add `roadmap/spikes/cloudflare-private-origins.yaml` with these fields (depends on 6):
  - `apiVersion: roadmap.mctl.ai/v1alpha1`
  - `kind: SpikeDefinition`
  - `metadata.name: cloudflare-private-origins`
  - `metadata.owner: mctlhq/.github`
  - `lifecycle: proposed`
  - `github.issue: mctlhq/.github#292`
  - `outcomes: [ADOPT, POC, COMPLEMENTARY, NO_GO]`
  - `execution.devloop: true`
  - `evidence.report: docs/spikes/cloudflare-private-origins.md`
  - a header comment that the verdict lives only in the report

  — DoD: the file validates against `roadmap/schemas/spike-definition.schema.json`.
- [ ] 8. Add a "Spikes" bullet in `AGENTS.md` linking the report with "proposed verdict COMPLEMENTARY", or whatever task 6 concluded (depends on 6). — DoD: the link resolves and the wording matches the report.

## Tests

- [ ] T1. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` exits 0.
- [ ] T2. `python -m pytest roadmap/tests` passes, in particular `test_validate_spike.py`.
- [ ] T3. `grep -rn "number: 292" roadmap/` shows only the `mctlhq/mctl-agents` binding in `devloop-pr-adoption.yaml` plus the new spike. No duplicate `.github#292` binding.
- [ ] T4. Manual review: the report has ten numbered investigation sections, the responsibility table, the fail-closed matrix and the follow-up table. It contains no secret values, token ids beyond those already public in mctl-gitops, or invented hostnames presented as deployed.
- [ ] T5. The verdict string is the same in the report, the `AGENTS.md` entry and the PR description.

## Rollback

The change is documentation and one manifest in `mctlhq/.github`. To roll back,
revert the PR. No infrastructure, DNS, tunnel or Access object is created by this
spike, so nothing outside the repository needs undoing.
