# Tasks: issue-2669-spike-evaluate-opencost-for-attributable

Research-only. No task deploys, installs, queries production or billing, or
changes cluster state.

- [ ] 1. Write the cost attribution boundary and the no-duplicates map in
  `docs/spikes/2669-opencost-infra-cost-attribution.md`.
  - Boundary sources: `infrastructure/k3s-preview/kube.tf` (cx33 ×1 CP,
    cx43 ×3 workers, lb11, R2 etcd snapshots), and the `hcloud-volumes` /
    `local-path` StorageClasses.
  - No-duplicates sources: `mctl-finops-storage-dashboard-configmap.yaml`, the
    k8s-views and erpact dashboards, the mctlhq/.github#48 ledger,
    mctlhq/mctl-gitops#902, `mctl_get_resource_usage`, and the "no
    OpenCost/Kubecost committed" result.
  - DoD: every line is classed in-cluster-allocatable, fixed-platform,
    external or invoice-only, and every fact has a source or the marker
    "not observed".
- [ ] 2. Document the tenant mapping authority (depends on 1).
  - Authority is `mctl.me/tenant` from `helm-charts/tenant/templates/_helpers.tpl`,
    validated against `platform-gitops/tenants/<t>/`.
  - Platform namespaces come from the reserved list in
    `wft-create-tenant.yaml`. `admins` is classed platform, pending the owner.
  - Pod labels, `mctl.ai/team` and OTLP `mctl.team` are evidence only.
  - DoD: the memo has a decision table covering label to class.
- [ ] 3. Define `infra-alloc-rule/v1` and the price catalog schema (depends on 1).
  - Rule v1: requests basis, usage as an efficiency column, a 50/50 CPU/RAM
    split, idle as its own line, PV cost to the PVC's namespace, a
    fully-loaded distribution to verified tenants only, integer cents with a
    largest-remainder residual, and evidence classes
    booked_invoiced/calculated/allocated/unknown.
  - Commit `docs/spikes/2669-fixtures/price-catalog.synthetic.json` with
    `provenance: synthetic` and an `effective_from` date.
  - DoD: the rule and schema are versioned in the memo, and v2
    (max(request, usage)) is listed as an option.
- [ ] 4. Add the offline fixture `docs/spikes/2669-fixtures/cluster-month.synthetic.json`
  (depends on 3).
  - Fixture contents: platform overhead (CP 10.00, lb 5.00, volumes 2.00,
    platform ns 4c/8Gi), tenant-a 6c/12Gi, tenant-b 2c/2Gi with 0.5c used, a
    spoofed `tenant-c` namespace with the pod label `mctl.ai/team=tenant-a`,
    and 3 workers × 20.00 over 24c/48Gi.
  - DoD: the expected output is embedded:
    - direct view: platform 27.00, tenant-a 15.00, tenant-b 3.75,
      unattributed 2.50, idle 28.75, total 77.00;
    - fully loaded: tenant-a 59.60, tenant-b 14.90, unattributed 2.50.
- [ ] 5. Implement `scripts/infra-cost-allocate.py` (depends on 3, 4).
  - Stdlib only (`json`, `decimal`, `argparse`), with file inputs, no network
    and no Kubernetes client.
  - The output tags every line with an evidence class.
  - It refuses a model-ledger join without a shared canonical tenant or
    execution id, and never sums the two.
  - DoD: `python3 -I scripts/infra-cost-allocate.py --catalog ... --usage ...`
    prints the expected tables.
- [ ] 6. Write the comparison section (depends on 1, 3).
  - Compare OpenCost and the VM-native report on added pods and resources,
    added VMSingle active series, pricing fidelity (Hetzner is not a native
    provider, so the `default` `costModel` is used), reconciliation hours per
    month, failure modes (exporter down, label drift, VM OOM, catalog
    staleness) and multi-tenancy risk.
  - DoD: unmeasured cells read "not observed", and the measurement commands
    are listed for a later authorised run.
- [ ] 7. Write the recommendation and the owner-review checklist (depends on 2-6).
  - Outcome: REUSE_EXISTING_METRICS, with live € = `unknown`
    (DEFER_PRICING_UNVERIFIABLE for pricing) until a dated invoice-provenance
    catalog exists.
  - Name the smallest safe follow-up issue (read-only VM recording rules plus
    a monthly report), and state that any OpenCost pilot needs a separate
    issue and an independent owner GO.
  - DoD: the memo ends with an explicit "no implementation grant" statement.

## Tests

- [ ] T1. `tests/test_infra_cost_allocation_fixture.py`: the direct-view lines
  sum to exactly 7700 cents and match the expected per-line values.
- [ ] T2. The spoofed `tenant-c` namespace, and the pod label claiming
  `tenant-a`, both land in `unattributed`, and tenant-a's direct cost stays
  1500 cents.
- [ ] T3. The fully-loaded view assigns 0 shared cost to `unattributed`, and
  tenant-a + tenant-b + unattributed = 7700 cents.
- [ ] T4. The rounding residual case: a fixture with a 3-way split of 1.00 EUR
  resolves by largest remainder to an exact total, and is deterministic
  across runs.
- [ ] T5. Every output line has exactly one evidence class, and any catalog
  under `docs/spikes/2669-fixtures/` with `provenance` other than `synthetic`
  fails the test.
- [ ] T6. A model-ledger join without a matching canonical id raises, and with
  a matching id the result has separate columns and no summed total.

## Rollback

All changes are docs, fixtures, one offline script and one test. Rollback is
`git revert` of the spike PR. No cluster, ArgoCD, Terraform or billing state is
touched, so there is nothing to undo at runtime.
