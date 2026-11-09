# Lock down Argo CD repo-server (NetworkPolicy and Kustomize-Helm config)

## Context
The 2026-11-07 inbox reports two critical Argo CD repo-server issues from third-party aggregators: CVE-2026-15416 (unauthenticated code execution via the repo-server gRPC interface, possibly through the Redis cache) and CVE-2026-113709 (CVSS 9.9; a repo-controlled Kustomize Helm config home can run commands when `--enable-helm` is on for kustomize builds). Argo CD is the sync engine for the whole platform and this repo is its source, so a repo-server compromise has the widest possible blast radius.

Both issues have config-only mitigations: a NetworkPolicy limiting repo-server gRPC and Redis access to Argo CD components, and disabling Helm for kustomize builds (or pinning `helmGlobals.configHome` outside the repo). No version bump is needed. The CVE IDs and the affected version ranges are NOT yet verified against NVD or the Argo CD GHSA, and the running Argo CD version is not recorded in `context/`. The mitigations are cheap and sensible regardless of the verification outcome. Note: earlier proposals (for example `argocd-repo-server-rce-network-isolation`) overlap with the NetworkPolicy part; the implementer must reconcile with them rather than duplicate.

## User stories
- AS a platform operator I WANT repo-server reachable only by Argo CD components SO THAT an in-cluster attacker cannot reach its gRPC interface or the Redis cache.
- AS a platform operator I WANT kustomize-with-Helm disabled or confined SO THAT a malicious repo cannot execute commands in repo-server.
- AS a security reviewer I WANT the CVE IDs and affected ranges verified against vendor advisories SO THAT we do not cite or act on bogus identifiers.

## Acceptance criteria (EARS)
- WHEN the proposal is started THE SYSTEM SHALL record the running Argo CD version (via mctl or the cluster) and compare it with the verified affected ranges.
- WHEN CVE-2026-15416 and CVE-2026-113709 are checked THE SYSTEM SHALL confirm each ID, affected range and fixed version against NVD and the Argo CD GHSA before any ID is cited in a commit or ADR.
- IF a CVE ID cannot be verified THEN THE SYSTEM SHALL still apply the mitigations but mark the ID as "unverified" in all documents.
- WHEN the NetworkPolicy is applied THE SYSTEM SHALL allow ingress to the repo-server gRPC port (8081) and to Redis only from the Argo CD application-controller, server, applicationset-controller and notifications pods (plus metrics scrapers on the metrics ports).
- WHEN a pod outside the allowed set connects to repo-server gRPC or Redis THE SYSTEM SHALL drop the connection.
- WHEN the kustomize Helm setting is changed THE SYSTEM SHALL first list every App that uses `kustomize.buildOptions` containing `--enable-helm` or a `helmCharts` entry in a kustomization, and none SHALL break after the change.
- IF any App depends on kustomize-with-Helm THEN THE SYSTEM SHALL pin `helmGlobals.configHome` outside the repo checkout for it instead of disabling Helm globally.
- WHILE the change is rolling out THE SYSTEM SHALL keep all ApplicationSet-generated Apps Synced/Healthy, with no new OutOfSync or Unknown states.
- WHILE the change is in effect THE SYSTEM SHALL NOT add pods or raise memory requests/limits in `labs`.

## Out of scope
- Any Argo CD version bump (see `argocd-patch-serversidediff-fix`).
- Migrating away from Argo CD or adding approval gates on ApplicationSets.
- Network policies for other namespaces or services.
