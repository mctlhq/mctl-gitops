# Design: emudhra-ca-distrust-bumps

## Current state
cert-manager handles TLS lifecycle, Argo Rollouts handles progressive delivery, and Vault (`secrets.mctl.ai`) holds all tenant and platform secrets through the `vault-backend` ClusterSecretStore used by External Secrets (see `/app/agents/mctl-gitops/context/architecture.md`). Current versions of all three are not in `context/` and must be read from the cluster. `labs` is near its memory limit.

## Proposed solution
A staged, one-component-at-a-time version bump, each as a git commit in this repo applied by ArgoCD:

0. Verification and exposure: confirm CVE-2026-111943 and the release claims against NVD and vendor advisories; confirm each current version is behind its target; check whether any certificate or trust bundle chains to eMudhra (likely none).
1. cert-manager to v1.21.3. Canary first (admins), soak, then the rest. Check the ACME ARI renewal behavior change and Secret private-key copy fix in release notes.
2. Argo Rollouts to v1.10.2, same canary and soak pattern.
3. Vault to v2.2.1 last. Take a verified snapshot first. Audit policies for aliases that resolve to the root policy, since v2.2.1 rejects them. Upgrade standbys first and the active node last, if HA. Do not enable the SPIFFE auto-auth feature.

Memory: for cert-manager and Argo Rollouts (Go 1.26.10), record `labs` controller memory baselines before and compare after each step; stop on regression. Each component keeps its own previous tag for rollback.

Why this way: Vault is the highest-risk item (all secrets depend on it) so it goes last, after the other two prove the process; impact is modest, so there is no need for a bundled rush.

## Alternatives
- Bundle all three in one change: rejected, harder to attribute failures and roll back.
- Do nothing since the platform likely does not chain to eMudhra: rejected, cheap hygiene and the extra cert-manager and Vault fixes have independent value, but priority stays low (impact 3).
- Upgrade Vault first because of its importance: rejected, riskiest component should follow the proven process.

## Platform impact
- Migrations: Vault policy audit for root-aliasing; check cert-manager CRD changes between current and target.
- Backward compatibility: Vault v2.2.1 rejects root-resolving policy aliases, which could break an existing config (mitigated by the audit). cert-manager's ARI fix changes renewal timing slightly.
- Resource impact: no new pods. Go 1.26.10 bump may shift controller memory slightly; RISK for `labs` (close to its memory limit). Mitigation: baseline, canary, compare, stop-and-rollback threshold.
- Risks and mitigations: Vault outage blocks ExternalSecrets (snapshot, standbys first, Vault-specific rollback); unverified CVE ID (flagged, work proceeds on release-note evidence); scope creep into SPIFFE (explicitly excluded).
