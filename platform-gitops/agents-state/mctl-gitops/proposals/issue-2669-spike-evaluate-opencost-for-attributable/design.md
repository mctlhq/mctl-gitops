# Design: issue-2669-spike-evaluate-opencost-for-attributable

## Current state

### Cluster and priced assets (from Git only)

- `infrastructure/k3s-preview/kube.tf` defines the only provisioned cluster,
  `mctl-preprod`, in `network_region = "eu-central"`:
  - `control_plane_nodepools`: `control-plane-fsn1`, `server_type = "cx33"`,
    `count = 1`, `taints = []`. Workloads can therefore schedule on the
    control plane, which means control-plane cost is not purely fixed
    overhead.
  - `agent_nodepools`: `worker-cx43-fsn1`, `server_type = "cx43"`, `count = 3`.
  - `load_balancer_type = "lb11"` in `fsn1`.
  - `enable_longhorn = false`.
  - etcd snapshots go to Cloudflare R2 (an external, non-Hetzner cost).
- `infrastructure/k3s-prod/README.md` is a TODO. No production cluster is
  defined, so "by cluster" means one cluster today.
- Storage: platform data uses the `hcloud-volumes` StorageClass
  (`bootstrap/templates/core-infra/vault.yaml`,
  `bootstrap/templates/data/forgejo.yaml`). Opted-in workflow scratch uses
  `local-path` (`bootstrap/templates/core-infra/local-path-provisioner.yaml`,
  `argo-workflows/config/local-workdir-quota.yaml`). Node-local disk is part of
  the server price. Hetzner volumes are billed separately.
- No Hetzner price, invoice or currency appears anywhere in the repo. The
  `kube.tf` comments record R2 sizes but no prices.

### Metrics already available

- `platform-gitops/bootstrap/templates/observability/monitoring.yaml` deploys
  `victoria-metrics-k8s-stack` `0.72.5` with VMSingle (`retentionPeriod: "28d"`
  on a 25Gi volume, with a documented ~8.4G at 28d), `kube-state-metrics`
  (`instance` pinned to a constant, and `uid|container_id|image_id`
  labeldropped), `kubelet` (apiserver_/etcd_ series dropped), and
  `nodeExporter: enabled`. Together these supply everything a requests/usage
  allocation needs:
  - `kube_pod_container_resource_requests`
  - `container_cpu_usage_seconds_total`
  - `container_memory_working_set_bytes`
  - `kube_node_status_allocatable`
  - `kube_persistentvolume_capacity_bytes` / `kube_persistentvolume_info`
  - `kube_namespace_labels` (if label allowlisting is configured; not
    verified)
  - `node_network_transmit_bytes_total`
- Existing cost-adjacent dashboard:
  `infra-components/observability/grafana-dashboards/mctl-finops-storage-dashboard-configmap.yaml`
  ("mctl — Storage & FinOps"). It shows quota saturation, Hetzner CSI churn,
  node filesystem headroom, egress rate against "20 TB included quota", PVCs
  by namespace and PV capacity by StorageClass. It carries no prices and does
  no allocation. `k8s-views-global-patched-configmap.yaml` and
  `erpact-tenant-dashboard-configmap.yaml` already query request and usage
  series.
- A search for `opencost|kubecost` across the repo returned no matches. No
  OpenCost or Kubecost configuration is committed.

### Tenant identity

- `helm-charts/tenant/templates/_helpers.tpl` (`tenant.labels`,
  `tenant.teamLabels`) writes `mctl.me/tenant: <tenant.name>` onto every tenant
  namespace, and `tenant.namespaces` derives `{tenant}` or `{tenant}-{team}`.
  This label is platform-controlled. `docs/spikes/2286-obi-evaluation.md`
  ("Tenant identity today") established that the pod label `mctl.ai/team` and
  OTLP `mctl.team` are tenant-controlled, and therefore forgeable evidence
  rather than authority.
- Authoritative tenant set: the directories under `platform-gitops/tenants/`,
  which are `admins`, `commerce-proof`, `erpact`, `karabu`, `labs`, `mctl` and
  `namax66`.
- Platform and system namespaces excluded from tenancy are enumerated in
  `argo-workflows/cluster-templates/wft-create-tenant.yaml` (reserved-name
  regex including `local-path-storage|system-upgrade|observability-eval|tracing|...`).

### Related ledgers (no-duplicate inputs)

- Model and token spend: mctlhq/.github#48 (Agent FinOps ledger),
  mctlhq/mctl-api#651. It is surfaced as `mctl_get_usage_summary`, which
  separates `provider_reported_cost`, `calculated_cost` and
  `invoice_reconciled_cost` and never adds them together. This proposal
  mirrors that vocabulary.
- OTel Collector boundary: mctlhq/mctl-gitops#902 (`docs/runbooks/otel-collector.md`).

### Deployed state checked

- `mctl_whoami`: `agent:issue-investigator`, non-admin, no teams. Cluster and
  namespace reads were therefore not available.
- `mctl_list_tenants`: refused ("requires admin access"). The live tenant list
  was not observed. Git `tenants/` was used instead.
- `mctl_get_resource_usage labs`: allocated `requests.cpu 4`,
  `requests.memory 7Gi`, `requests.storage 20Gi`. Used `requests.cpu 2300m`,
  `requests.memory 4608Mi`, `pods 19`, `persistentvolumeclaims 0`. This shows
  quota and requests are readable per tenant through the API, but it is a
  point-in-time value and not a monthly integral.
- `$MCTL_GITOPS_ROOT/tenants/*/values.yaml`: seven tenants, matching the
  clone.
- Not observed: live node allocatable capacity, live namespace labels, VMSingle
  active-series count, Hetzner inventory and prices. These are recorded under
  Open questions in requirements.md. A failed or unavailable read is not
  treated as absence.
- OpenCost docs (fetched 2026-11-15):
  - The specification states that workload cost is max(request, usage) at
    container level, that idle is asset cost not attributed to workloads, and
    that shared cost may be distributed uniformly, proportionally or by a
    custom metric.
  - The configuration page lists the providers alibaba, aws, azure, gcp,
    oracle, ovh and `default` (on-prem). Hetzner is not a native provider, so
    custom pricing goes through the `default` provider's `costModel`
    (`CPU`, `RAM`, `storage`). The page does not say whether pricing can
    differ per node type.

## Proposed solution

The deliverable is documentation plus an offline, stdlib-only calculation. It
contains nothing deployable.

1. **Decision memo** `docs/spikes/2669-opencost-infra-cost-attribution.md`,
   following the format of `docs/spikes/2286-obi-evaluation.md`. Every fact
   carries a source and command, and anything unobserved is marked
   "not observed". Sections:
   - **Cost attribution boundary** (a table of in-cluster vs external lines):
     - worker servers;
     - control-plane server (shared, but schedulable);
     - lb11 (fixed platform);
     - `hcloud-volumes` (allocated to the PVC's namespace);
     - node-local disk (included in the server price);
     - primary IPs, egress above the included quota, snapshots and backups;
     - R2 and Cloudflare (external, not allocated);
     - VAT, discounts and currency (invoice-level only, never allocated);
     - model and token spend (the #48 ledger, a separate column).
   - **No-duplicates map**: the existing Storage & FinOps dashboard; the
     k8s-views and erpact request/usage panels; the #48 model ledger; the
     #902 OTel boundary; `mctl_get_resource_usage`; and the "nothing
     committed" result for OpenCost/Kubecost.
   - **Tenant mapping authority**: the namespace label `mctl.me/tenant`, valid
     only if the value names a directory in `platform-gitops/tenants/`.
     Namespaces matching the reserved-name list are classed `platform`. The
     `admins` tenant is classed `platform` pending the owner's decision. Any
     other value goes to `unattributed`.
   - **Comparison**: OpenCost against a VictoriaMetrics-native report, on
     footprint, cardinality, pricing fidelity, reconciliation effort,
     failure modes and multi-tenancy risk. See Alternatives for the expected
     findings. All unmeasured numbers are marked "not observed".
   - **Recommendation**: **REUSE_EXISTING_METRICS** for the allocation
     mechanics, with live € figures held as `unknown`
     (DEFER_PRICING_UNVERIFIABLE applies to pricing) until the owner
     commits a dated price catalog with invoice provenance. The smallest safe
     follow-up is a separate issue for read-only VM recording rules
     (namespace × resource request/usage core-hours and GiB-hours) and a
     monthly report. Any OpenCost pilot needs its own issue and an
     independent owner GO.

2. **Allocation rule v1** (in the memo, versioned `infra-alloc-rule/v1`):
   - Cluster total C = the sum of priced assets from the catalog for the
     month.
   - Fixed platform overhead is lb11, the control-plane share not consumed by
     requests (optional: rule v1 treats the CP node as fixed overhead), and
     non-allocatable lines.
   - The worker compute pool is split into a CPU pool and a RAM pool by a
     declared ratio (v1: 50/50). Unit rates are CPU pool / allocatable
     core-hours and RAM pool / allocatable GiB-hours.
   - Direct allocation per namespace is requested core-hours × CPU rate plus
     requested GiB-hours × RAM rate. Usage is reported alongside it as an
     efficiency column only. max(request, usage) is a documented v2 option.
   - Idle is the pool minus the sum of direct allocations, and is kept as its
     own line.
   - Storage: a PV's price × its capacity × hours is charged to the PVC's
     namespace. Unbound PVs are classed platform.
   - Fully-loaded view (optional): platform overhead and idle are distributed
     to verified tenants in proportion to their direct allocation, never to
     `unattributed`.
   - Rounding: all arithmetic is in integer cents using `Decimal`, and the
     residual is distributed by largest remainder. The output must sum exactly
     to C.
   - Every figure carries an evidence class: `booked_invoiced` (invoice
     line), `calculated` (catalog price × quantity), `allocated` (rule-derived
     share) or `unknown`. Model-ledger cost may sit beside these only as a
     separate column joined on canonical tenant or execution id, and is never
     summed with them.

3. **Price catalog schema** `docs/spikes/2669-fixtures/price-catalog.synthetic.json`:
   `{catalog_version, effective_from, currency, provenance:
   "synthetic"|"list_price"|"invoice", items: [{sku, unit, unit_price_cents}]}`.
   Only a `synthetic` instance is committed by this spike.

4. **Offline fixture and allocator**:
   - `docs/spikes/2669-fixtures/cluster-month.synthetic.json` holds three cases
     (worked numbers are in the memo and are illustrative, not Hetzner
     prices):
     - CP 10.00 + lb 5.00 + volumes 2.00 + 3 workers × 20.00 = C = 77.00 EUR
       (synthetic).
     - Allocatable 24 cores and 48 GiB, giving 1.25/core-month and
       0.625/GiB-month.
     - platform namespaces: 4c/8Gi → 10.00.
     - `tenant-a`: 6c/12Gi → 15.00.
     - `tenant-b`: 2c/2Gi requested but 0.5c used → 3.75 (low efficiency
       reported, not reallocated).
     - namespace labelled `mctl.me/tenant=tenant-c` with no tenants entry,
       plus a pod label `mctl.ai/team=tenant-a` (spoof): 1c/2Gi → 2.50,
       `unattributed`.
     - idle → 28.75.
     - Check: 15 + 2 + 10 + 15 + 3.75 + 2.50 + 28.75 = 77.00.
     - Fully loaded: shared 55.75 is split 80/20, giving tenant-a 59.60,
       tenant-b 14.90 and unattributed 2.50, which sums to 77.00.
   - `scripts/infra-cost-allocate.py` is a pure-stdlib allocator: no network,
     no cluster client, input from files only.
   - `tests/test_infra_cost_allocation_fixture.py` asserts the exact
     reconciliation, the unattributed handling, the absence of distribution
     to unattributed, and the evidence-class tags.

Why this shape: it answers every research question with reproducible
artefacts. It reuses the repo's existing spike convention and pytest suite. It
adds zero running components, which the issue's authority section requires.

## Alternatives

- **Deploy OpenCost now (BOUNDED_OPENCOST_PILOT).** Dropped because it
  violates the issue's no-deployment authority. It would also add a
  Deployment, its exporter series and UI ingress to a VMSingle that has
  already been OOM-tuned (requests and limits raised three times in 2026-10 in
  `monitoring.yaml`). Hetzner is not a native provider, so pricing would be a
  hand-entered `default` `costModel` anyway, which is the same catalog this
  proposal writes. OpenCost's namespace aggregation would also need the
  `mctl.me/tenant` label mapping and the unknown-tenant guard re-implemented
  on top.
- **OPENCOST_OFFLINE_MODEL (adopt the OpenCost spec formulas as the model,
  with no binary).** Partly adopted: rule v1 borrows OpenCost's idle and
  shared-distribution concepts and documents max(request, usage) as v2. It was
  not chosen as the headline outcome because the computation runs on
  existing VictoriaMetrics series, with nothing OpenCost-specific remaining.
- **Extend the existing Storage & FinOps Grafana dashboard with price
  constants.** Dropped. It would show € values without a dated catalog or
  evidence class, which is exactly the "list price silently treated as
  invoice" failure the issue forbids, and Grafana panels give no
  reconciliation guarantee.

## Platform impact

- No cluster, ArgoCD, Helm or Terraform change. The new files are
  docs, fixtures, one stdlib script and one pytest file. ArgoCD ignores
  `docs/`, `scripts/` and `tests/`.
- Resource impact: none at runtime. The CI test cost is negligible.
- Risks and mitigations:
  - Synthetic euros could be mistaken for real prices. Every synthetic value
    carries `provenance: synthetic`, and a test fails if a non-synthetic
    catalog is present in the fixtures directory.
  - Tenant spoofing could misattribute cost. Only the platform-written
    namespace label, validated against `tenants/`, is authority, and anything
    else goes to `unattributed` (covered by a test).
  - Infrastructure allocation could be double counted with model cost. The
    two are kept in separate columns with distinct evidence classes, and the
    allocator refuses to sum them (covered by a test).
  - Memo claims could be read as measurements. Unmeasured facts are marked
    "not observed", following the 2286 spike convention.
