# Roll out cert-manager v1.21.3, Vault v2.2.1 and Argo Rollouts v1.10.2 for the eMudhra CA distrust

## Context
Three core components shipped coordinated fixes related to the compromised eMudhra CA: cert-manager v1.21.3 (removes trust in the CA, fixes an ACME ARI renewal loop and a Secret private-key copy issue, Go 1.26.10), Vault v2.2.1 (distrusts eMudhra intermediate chains, rejects policy aliases that resolve to the root policy) and Argo Rollouts v1.10.2 (fix for CVE-2026-111943 on eMudhra private keys, Go 1.26.10). The CVE ID CVE-2026-111943 has an unusual six-digit form and has not been verified against NVD or vendor advisories.

Impact is limited because the platform likely does not chain to eMudhra, so this is mostly trust-store hygiene plus the extra cert-manager and Vault fixes. Vault holds all platform secrets via the `vault-backend` ClusterSecretStore, so it needs the most care. `labs` is close to its memory limit and the Go 1.26.10 toolchain bump may shift controller memory slightly; this is a risk flag.

## User stories
- AS a platform operator I WANT the three components on versions that distrust the eMudhra CA SO THAT the trust stores are clean.
- AS a platform operator I WANT staged rollout with Vault last SO THAT secret access is protected if something fails.
- AS a security reviewer I WANT the CVE ID and our actual eMudhra exposure verified SO THAT the work is justified and accurately documented.

## Acceptance criteria (EARS)
- WHEN the proposal is started THE SYSTEM SHALL verify CVE-2026-111943 and the eMudhra distrust notes against NVD and the vendor release advisories, and mark the ID unverified if it cannot be confirmed.
- WHEN versions are checked THE SYSTEM SHALL record the current cert-manager, Vault and Argo Rollouts versions and confirm each is behind its target release.
- WHEN exposure is assessed THE SYSTEM SHALL check whether any issued or trusted certificate in the platform chains to eMudhra and record the result.
- WHEN rollout begins THE SYSTEM SHALL proceed in the order cert-manager, then Argo Rollouts, then Vault, with a soak period between each.
- WHILE any component is being upgraded THE SYSTEM SHALL keep certificate issuance/renewal, rollouts and ExternalSecrets sync working.
- BEFORE the Vault upgrade THE SYSTEM SHALL take and verify a Raft/storage snapshot and document a Vault-specific rollback.
- BEFORE each rollout THE SYSTEM SHALL capture controller memory in `labs` as a baseline, use a canary, and compare memory after the rollout.
- IF `labs` memory rises enough to threaten its limit THEN THE SYSTEM SHALL stop the rollout and roll back that component.
- WHEN Vault is upgraded THE SYSTEM SHALL verify that no existing policy depends on aliases resolving to the root policy, and that the `vault-backend` ClusterSecretStore stays Ready.
- WHILE the rollout is in progress THE SYSTEM SHALL NOT enable the Vault SPIFFE auto-auth method or other unrelated new features.

## Out of scope
- Vault SPIFFE auto-auth adoption.
- Argo CD, Argo Workflows, Helm or External Secrets upgrades.
- Major or minor line changes beyond the named target versions without a separate review or ADR.
