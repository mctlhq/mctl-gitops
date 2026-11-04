# Spike 2286: OpenTelemetry eBPF Instrumentation (OBI) evaluation

STATUS: PENDING_EXPERIMENT

Step A of mctlhq/mctl-gitops#2286: a default-off sandbox
(`obiSpike.enabled: false` in `platform-gitops/bootstrap/values.yaml`,
`platform-gitops/bootstrap/templates/observability/obi-spike.yaml`). Nothing
here enables the flag, loads BPF or measures anything. That is
mctlhq/mctl-gitops#2303. This document holds no measured value and no outcome.

"Not observed" means no read-only source was available when this was written.
It never means "absent".

## 1. Preconditions (read-only)

| Fact | Value | Command or source |
|---|---|---|
| Worker kernel version and `osImage` | not observed | `kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo}'` (no cluster read access in this run) |
| BTF on `worker-cx43-fsn1` | not observed | `ls /sys/kernel/btf/vmlinux` on the worker, or the MicroOS kernel config |
| Kernel lockdown mode on `worker-cx43-fsn1` | not observed | `cat /sys/kernel/security/lockdown` on the worker |
| Node layout | `control-plane-fsn1` (cx33, count 1, `taints = []`); `worker-cx43-fsn1` (cx43, count 3, `taints = []`); `automatically_upgrade_os = false` | `infrastructure/k3s-preview/kube.tf` |
| Fixture tenant A | `labs` (20 Synced base-service services; no multi-team `teams:` seen) | `tenants/labs/values.yaml`; proposal investigation history |
| Fixture tenant B | `mctl` (owner `mashkovd`, no workloads, quota `pods: 1`, `requests.memory: 128Mi`, `requests.cpu: 100m`) | `mctl_get_tenant mctl` |
| Platform workload | `mctl-api/mctl-api` (Argo app `admins-mctl-api`, Healthy and Synced); whether it already emits spans is not observed | `mctl_get_service_status admins/mctl-api`; `bootstrap/templates/mctl-platform/mctl-api-*.yaml` |
| Expected namespace labels | `labs` -> `mctl.me/tenant=labs`; `mctl` -> `mctl.me/tenant=mctl`; `mctl-api` and `observability-obi-spike` carry none. Live namespace labels: not observed | `tenant.labels` / `tenant.teamLabels` in `platform-gitops/helm-charts/tenant/templates/_helpers.tpl` |
| Selected OBI feature subset | application traces and metrics; no network metrics, no TC context propagation, no k8s cache | `obiSpike.features` |
| Current Tempo span rate, VMSingle series baseline | not observed | to be read in #2303 |

### Explicit `otel:` coverage (overlap-map skeleton)

`helm-charts/base-service` has a default-off `otel:` block
(`tests/test_base_service_otel_env.py`). In the committed gitops only
`admins/mctl-agents-worker`, `admins/mctl-agents-worker-exec`,
`admins/mctl-agents-worker-implement` and `admins/mctl-support` set it. All
other services, including every `labs` service, are not explicitly
instrumented. #2303 fills the overlap map from this list.

### Tenant identity today (finding)

The production `k8sattributes` processor (`otel-collector.yaml`) maps the pod
labels `mctl.ai/team` -> `mctl.team` and `mctl.ai/component` ->
`mctl.component`, with the default pod association (connection-IP fallback).
`base-service` does not set `mctl.ai/team`, and its `podLabels` are
tenant-controlled through `update-config`. `mctl.team` is therefore forgeable:
evidence, not authority.

The platform-controlled key is the namespace label `mctl.me/tenant`, written
onto every tenant namespace by the tenant chart, and already used as identity
by `infra-components/observability/otel-collector/networkpolicy.yaml`. The
spike collector resolves `mctl.tenant` from that label only (association on
`k8s.pod.uid`, no IP fallback) and never reads `mctl.team`.

## 2. Provisional privilege set

Source: OpenTelemetry documentation, "OBI security, permissions, and
capabilities", https://opentelemetry.io/docs/zero-code/obi/security/ ,
fetched 2026-10-31. The page states no revision; it references OBI v0.12.0
and v0.14.0 behaviour. Image: `ghcr.io/open-telemetry/opentelemetry-ebpf-instrumentation/ebpf-instrument`
at v1.0.0 (published 2026-10-30), index digest
`sha256:a68d70e934260f72540f157ccf4fb4adfa38f11de060d7d905696dad6a3fca02`
(read from ghcr.io on 2026-10-31). The page does not state `hostPID`; it is
taken from OBI's process-discovery requirement and is to be proven in #2303.

Added (`securityContext.capabilities.add`), each with the security-doc usage:

| Capability | Security doc usage |
|---|---|
| `BPF` | general BPF functionality, and socket filter programs for network flows |
| `PERFMON` | application observability (probe loading, pointer arithmetic), context propagation, flow monitoring |
| `SYS_PTRACE` | access to `/proc/<pid>/exe` and executable modules to scan symbols and instrument programs |
| `DAC_READ_SEARCH` | reads `/proc/self/mem` to determine the kernel version |
| `CHECKPOINT_RESTORE` | access to `/proc` symlinks for process and system information |

Mounts: `/sys/fs/cgroup` read-only (container id -> pod resolution; this repo's
choice, not a security-doc entry). The security doc's only mount is
`/sys/kernel/tracing`, needed solely for context propagation, which is off, so
it is not mounted.

Withheld, with the condition under which each would be needed:

| Capability | Condition (security doc) |
|---|---|
| `SYS_ADMIN` | `bpf_probe_write_user()` features (Go library-level context propagation) and BTF access for the BPF metrics exporter; only via `allowPrivileged`, a #2303 decision |
| `NET_ADMIN` | TC (`SCHED_CLS`) programs for flow capture and trace context propagation; both are off |
| `NET_RAW` | `AF_PACKET` raw sockets for network-flow socket filters; network metrics are off |
| `SYS_RESOURCE` | raising locked memory on kernels < 5.11 only. The worker kernel is not observed (section 1), so it is left out |

`obiSpike.securityContext` and `obiSpike.mounts` match these tables;
`tests/test_obi_spike_render.py` pins them and `scripts/validate-obi-spike.py`
rejects any other capability while the spike is enabled. The OBI configuration
is rendered in OBI's v1 shape; moving to Config v2 is #2303's.

## 3. Pre-registered thresholds (frozen at merge)

| Dimension | Threshold | Breach effect |
|---|---|---|
| False / cross-tenant attribution | 0 across all fixture requests | `NO_FIT` unless fixed and the full set re-run clean |
| Platform/unlabelled fixtures unattributed | 100% | `NO_FIT` |
| Fixture span coverage | >= 95% of generated requests produce a server span | caps at `PILOT_SELECTED_WORKLOADS` |
| Privilege | no `privileged`, no `SYS_ADMIN`; `NET_ADMIN` only if propagation is selected | caps at `PILOT_SELECTED_WORKLOADS` |
| Node CPU overhead p95 (OBI container) | <= 3% of node allocatable (<= 240m on cx43) | caps at `PILOT_SELECTED_WORKLOADS` |
| OBI RSS per node p95 | <= 300Mi | caps at `PILOT_SELECTED_WORKLOADS` |
| Application latency p95 delta (on vs off) | <= max(5%, 2 ms) | caps at `PILOT_SELECTED_WORKLOADS` |
| API load from OBI service accounts (steady state, after initial sync) | LIST <= 0.1 req/s aggregate; WATCH streams <= 6 per OBI pod | evaluate `k8sCache`; if still breached, caps at `PILOT_SELECTED_WORKLOADS` |
| Series cardinality delta in VMSingle | <= 5,000 new series for the allowlist | caps at `PILOT_SELECTED_WORKLOADS` |
| Span volume delta | <= 50 spans/s at the #2303 load mix | caps at `PILOT_SELECTED_WORKLOADS` |

## 4. Decision rule

`ADOPT_BOUNDED_OBI_LAYER` requires every row within its threshold, plus
coverage that the explicit `otel:` path does not already give. Any attribution
breach that is not fixed gives `NO_FIT`. Everything else gives
`PILOT_SELECTED_WORKLOADS`.

## 5. Sidecar vs DaemonSet

Assessed on paper only. A sidecar would place the same BPF capabilities and
`shareProcessNamespace` inside tenant pods, which violates PSA `baseline` and
requires editing tenant `values.yaml`. Not operationally plausible here, so
not built.

## 6. Results (filled in by #2303)

### Overlap map

_Empty._

### Coverage matrix

_Empty._

### Measurements

_Empty._

### Failure behaviour

_Empty._

### Outcome

_Empty. No outcome is recorded while `STATUS: PENDING_EXPERIMENT`._
