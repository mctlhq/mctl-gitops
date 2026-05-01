# Design: nodejs-heap-cap-labs

## Current state
All three tenants (`labs`, `admins`, `ovk`) run openclaw 2026.3.14 on Node.js without an explicit
JavaScript heap ceiling (see `context/current-version.md` and `context/architecture.md`). The V8
heap grows opportunistically up to a platform-determined default (roughly 1.5 GB on 64-bit systems),
bounded only by the Kubernetes container memory limit. For the `admins` and `ovk` tenants this is
acceptable; for `labs` it is a live risk because the tenant is explicitly flagged as close to its
memory limit (`context/architecture.md`: "Close to the memory limit — any footprint increase
requires justification"). When memory pressure causes the kernel OOM killer to fire, the pod is
evicted without a clean shutdown. On restart, the restore-state readiness probe (ADR-0002) must
rehydrate all channel auth tokens from S3 before the pod is marked ready, causing observable
downtime for labs users.

Node.js 24.15.0 LTS, released 2026-04-15, promotes the V8 flag `--max-heap-size=<MB>` to a stable
CLI option. Prior to this release the flag was experimental and its promotion to stable is the
trigger that makes this proposal viable without taking on experimental-API risk.

## Proposed solution

### Mechanism
Add `--max-heap-size=<N>` to the Node.js invocation for the `labs` pod only, where N (in MB) is
determined by the mandatory profiling step described below. The flag instructs V8 to treat N MB as
the ceiling of the JavaScript heap. When the heap approaches that ceiling V8 performs aggressive
compacting GC. If GC cannot reclaim enough, V8 raises a `RangeError: JavaScript heap out of memory`
— a catchable, process-fatal JS error — rather than the pod being OOMKilled by the kernel. The
process then exits with a non-zero code, Kubernetes restarts it, and the restore-state probe
executes the standard S3 rehydration path (ADR-0002). This turns a silent kernel kill into a
structured, observable restart.

### Where the flag is set
The flag is added to the labs-specific helm overlay in the mctl-gitops repository. Two equivalent
injection points are available; the preferred approach is:

**Option A (preferred): `NODE_OPTIONS` environment variable in the labs helm values overlay**

```yaml
# helm/labs/values.yaml  (labs-specific overlay, not shared with admins or ovk)
env:
  NODE_OPTIONS: "--max-heap-size=<N>"
```

`NODE_OPTIONS` is the standard Node.js mechanism for injecting CLI flags without changing the
container entrypoint, and it is already the conventional place for runtime tuning in the openclaw
Docker image. This keeps the container image unchanged and makes the cap visible as a plain
key-value in the helm values diff.

**Option B (fallback): container command args in the labs Deployment/StatefulSet**

```yaml
command: ["node", "--max-heap-size=<N>", "dist/index.js"]
```

Use this only if `NODE_OPTIONS` is not honoured by the container entrypoint (e.g., if openclaw
uses an entrypoint script that overrides the environment). Confirm during profiling/testing.

### Determining the cap value N
1. Run the labs pod in its normal steady state and record heap usage over a representative window
   (at least 24 h, covering peak channel activity) using the existing mctl MCP metrics.
2. Identify the observed peak JS heap in MB (call it `P`).
3. Set N = floor(P / 0.8) — equivalently, N is the value such that `P` is at most 80% of `N`.
   This gives a 20% buffer above the observed peak before V8 escalates to aggressive GC.
4. Validate that N is comfortably below the difference between the container memory limit and the
   expected RSS overhead from native allocations and buffers (to avoid accidentally constraining
   the cap so low that RSS pressure still causes an OOMKill before V8 can act).
5. Document the baseline, peak, and chosen N in the PR description and in a comment in the labs
   helm overlay.

### Scope guard
The `--max-heap-size` flag MUST appear only in the labs-specific overlay file. The shared
`values.yaml` (if any) and the `admins` and `ovk` overlay files are not touched. ArgoCD diff
review in the PR is the enforcement mechanism.

### Rollout order
Per ADR-0001, changes are validated in `labs` before promotion to `admins` and `ovk`. Because this
proposal is labs-only and intentionally not promoted to the other tenants, the rollout is a single
step: apply the labs overlay, observe for at least 48 h, and close the task list.

## Alternatives

### Alternative 1: Increase the labs container memory limit
The most direct fix for OOMKill pressure is to raise the Kubernetes memory limit for the labs pod.
This was explicitly rejected: the architecture note and ADR constraints make any memory increase in
`labs` a risk requiring justification, and increasing the limit does nothing to improve the quality
of restarts (it still results in OOMKill at a higher threshold rather than a catchable JS OOM). The
heap cap achieves the graceful-restart goal without touching the memory limit at all.

### Alternative 2: Add a liveness probe that restarts the pod before OOM
A liveness probe that watches RSS or heap usage via a sidecar or a custom HTTP endpoint could
restart the pod preemptively. This approach requires additional infrastructure (sidecar container or
an instrumented health endpoint in openclaw), increases complexity, and adds RSS overhead — the
opposite of what `labs` needs. The `--max-heap-size` flag achieves the same preemptive effect
entirely within the existing Node.js runtime with no additional components.

### Alternative 3: Wait for the nodejs-runtime-upgrade proposal and tune there
The `nodejs-runtime-upgrade` proposal handles a future Node.js major bump. `--max-heap-size` was
promoted to stable in Node.js 24.15.0 LTS, the version already running in all three tenants
(inferred from the current openclaw version and the LTS release date of 2026-04-15). There is no
need to wait; the feature is available now. Deferring leaves the live OOMKill risk unmitigated for
the duration of the upgrade cycle, which is unnecessary given the low effort of this change.

## Platform impact

### Migrations
None. The change is a single line in the labs helm values overlay. No schema changes, no new
dependencies, no S3 changes.

### Backward compatibility
`--max-heap-size` is a stable V8/Node.js flag as of Node.js 24.15.0 LTS. If the labs Node.js
runtime is ever rolled back below 24.15.0 the flag was previously experimental (not absent), so it
will still be accepted, but its stability guarantees differ. The rollback procedure covers this.

### Resource impact for `labs`
- Memory: `--max-heap-size` caps the JS heap downward; it does not increase RSS. Net impact on
  the container memory limit: zero increase. This satisfies the `labs` constraint.
- CPU: If the chosen cap is too close to the normal operating heap, V8 GC runs more frequently,
  increasing CPU usage. The profiling step and the 20% buffer are the mitigations. Monitor CPU
  metrics for the first 48 h after the cap is applied.

### Risks and mitigations
| Risk | Mitigation |
|---|---|
| Cap set too low → GC thrashing degrades throughput | Mandatory profiling step before any deployment; 20% headroom above observed peak |
| Cap set too low → process OOMs under burst load that exceeds the profiled peak | Monitor heap and CPU metrics for 48 h post-deploy; if heap-OOM restarts occur, raise N by 10% and redeploy |
| `NODE_OPTIONS` not honoured by entrypoint → flag silently ignored | Verify during task 3 (integration test) by reading `/proc/<pid>/cmdline` or `process.execArgv` inside the running pod |
| Change accidentally applied to `admins` or `ovk` | ArgoCD PR diff review; test in task 3 checks that the flag is absent in admins/ovk manifests |
| Node.js downgrade below 24.15.0 | Rollback procedure removes the overlay line; flag was experimental (not removed) in earlier 24.x releases |
