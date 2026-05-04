# Design: loki-ruler-path-traversal

## Current state
`grafana/loki` is listed as a tracked dependency in `context/architecture.md`. Loki is used for log aggregation across the platform. The current deployed version predates v3.7.1 and is therefore affected by CVE-2026-21726: the Loki Ruler API endpoint `/loki/api/v1/rules/{namespace}` does not sanitize double-URL-encoded path traversal sequences in the `namespace` parameter. An unauthenticated caller who can reach the Ruler API port can read any file accessible to the Loki process, including Kubernetes Secret volumes mounted at standard paths and service account token files under `/var/run/secrets/`.

Loki is deployed as a Kubernetes workload and its service configuration is managed via Helm values in the GitOps repository (under `platform-gitops/services/<tenant>/loki/` or equivalent). The Loki deployment serves both `admins` and `labs` tenants for log ingestion and querying.

## Proposed solution
Pin the Loki Helm chart image tag to v3.7.1 in the Helm values file that controls the Loki deployment. The v3.7.1 release is a maintenance release on the 3.7.x branch that upgrades Go and gRPC versions, which is the surface on which this CVE is fixed. No Loki schema migrations, compactor rule changes, or CRD modifications are required for this patch-level version bump within the 3.7.x line.

Steps:
1. Update the `loki.image.tag` (or equivalent) value to `v3.7.1` in the relevant Helm values file in the GitOps repository.
2. Optionally pin the image digest for supply-chain integrity.
3. Commit and push. ArgoCD detects the diff and triggers a rolling upgrade of the Loki pods.
4. Verify that log ingestion and query functionality are healthy after rollout.
5. If the Loki Ruler component is separately deployed (e.g., `loki-ruler` subchart or separate Deployment), update its image tag in the same commit.

The rolling update strategy on the Loki Deployment (or StatefulSet for distributed mode) will ensure at most one pod is unavailable at a time, preserving log ingestion continuity during the upgrade.

## Alternatives

### Option A: Disable the Loki Ruler API via configuration
Setting `ruler.enabled: false` in the Loki configuration would prevent the vulnerable endpoint from being served. However, this disables alerting rule evaluation which may be in use for platform alert rules. Additionally, it does not fix the underlying vulnerability — if Ruler is re-enabled in future, the risk returns. Dropped in favour of patching.

### Option B: Block the Ruler API port via Kubernetes NetworkPolicy
A NetworkPolicy denying ingress to the Loki Ruler port from outside the cluster (or from all non-authorised sources) would reduce exploitability without a version upgrade. However, network policies require careful scoping to avoid breaking legitimate rule management traffic, and they leave a known-vulnerable binary in production. This is a valid defence-in-depth measure for a follow-up proposal but not a primary remediation. Dropped as the sole fix.

### Option C: Upgrade to a newer Loki minor version (e.g., v3.8.x or v3.9.x)
A minor-version upgrade could introduce compactor schema changes, storage format changes, or query API changes that require broader testing and potentially storage migration steps. The v3.7.1 patch release is the minimal-risk remediation on the current minor track. A minor-version upgrade can be planned separately. Dropped to minimise blast radius.

## Platform impact

### Migrations
None. v3.7.1 is a patch release within the 3.7.x line; no Loki chunk schema or index schema migrations are required.

### Backward compatibility
Full backward compatibility. Existing Loki query clients, Grafana data sources, and alert rule configurations continue to function without changes. The gRPC and Go library upgrades in v3.7.1 are internal to the Loki binary.

### Resource impact
The v3.7.1 release upgrades Go and gRPC versions; these changes do not materially alter Loki's runtime memory footprint. However, if Loki runs in the `labs` tenant (which is near its memory limit), the operator should confirm that the new image does not introduce memory overhead by monitoring pod memory after rollout. Any sustained increase beyond the existing resource limits would require a separate capacity proposal. This proposal flags the `labs` memory situation as a monitoring point but does not itself increase resource requests or limits.

### Risks and mitigations
- **Risk:** Loki StatefulSet rolling update leaves the log pipeline in a partially degraded state if a pod fails to restart cleanly.
  - **Mitigation:** Monitor Loki pod readiness during rollout. The previous image tag is known; revert in one commit if pods do not become ready within the rollout deadline.
- **Risk:** The updated gRPC library in v3.7.1 introduces a subtle incompatibility with existing Grafana or Prometheus Remote Write integrations.
  - **Mitigation:** Verify Grafana data source connectivity and run a test query against the Loki API immediately after rollout. Roll back if queries fail.
- **Risk:** If Loki runs in the `labs` tenant, the new image could push memory usage over the limit, triggering OOMKill.
  - **Mitigation:** Review current `labs` Loki pod memory usage before applying. If usage is already above 80% of the limit, escalate to a capacity review before proceeding.
