# Tasks: emudhra-ca-distrust-bumps

- [ ] 1. Verify CVE-2026-111943 and the eMudhra distrust claims against NVD and the cert-manager, Vault and Argo Rollouts release advisories — DoD: ID marked verified/unverified with source links; release-note claims confirmed.
- [ ] 2. Record current cert-manager, Vault and Argo Rollouts versions and confirm each is behind its target (v1.21.3, v2.2.1, v1.10.2) — DoD: versions written down; any component already at or past target is dropped from scope.
- [ ] 3. Assess eMudhra exposure: scan issued certificates and trust bundles for eMudhra chains (depends on 2) — DoD: result recorded (exposed / not exposed).
- [ ] 4. Capture `labs` memory baselines for cert-manager and Argo Rollouts controllers (depends on 2) — DoD: baseline numbers stored in the PR; headroom to the labs limit stated.
- [ ] 5. Upgrade cert-manager to v1.21.3: canary on admins, soak 24h, then the rest (depends on 1, 3, 4) — DoD: all pods on target; certificate issuance and renewal work; labs memory within agreed threshold.
- [ ] 6. Upgrade Argo Rollouts to v1.10.2 with canary and soak (depends on 5) — DoD: controller Ready; a sample rollout completes; labs memory within threshold.
- [ ] 7. Audit Vault policies/aliases for root-policy resolution and write the Vault-specific rollback plan (depends on 2) — DoD: audit result recorded; no offending alias, or a fix plan exists.
- [ ] 8. Take and verify a Vault snapshot (depends on 6, 7) — DoD: snapshot restored successfully in a test or integrity-checked.
- [ ] 9. Upgrade Vault to v2.2.1, standbys first then active (depends on 8) — DoD: unsealed, healthy, `vault-backend` ClusterSecretStore Ready; SPIFFE feature not enabled.
- [ ] 10. Final memory comparison for `labs` and summary (depends on 9) — DoD: before/after memory report; any regression raised.

## Tests
- [ ] T1. Issue a test Certificate through cert-manager — DoD: Ready, ARI renewal loop absent.
- [ ] T2. Run a canary Rollout end to end — DoD: promotes and aborts correctly.
- [ ] T3. Force-sync an ExternalSecret that reads from Vault — DoD: SecretSynced.
- [ ] T4. Read a secret with an existing production policy — DoD: access unchanged.

## Rollback
Per component, revert the version commit to the previous tag and let ArgoCD sync (cert-manager, Rollouts). For Vault, revert the image tag; if storage format or data is affected, restore from the task 8 snapshot following the Vault-specific plan. Stop the sequence at the first failed step and do not proceed to later components.
