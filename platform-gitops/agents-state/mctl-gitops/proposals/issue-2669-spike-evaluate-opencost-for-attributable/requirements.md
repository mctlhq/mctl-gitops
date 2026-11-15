# Spike: attributable Hetzner Kubernetes infrastructure cost (OpenCost vs VictoriaMetrics-native report)

## Context

Issue mctlhq/mctl-gitops#2669 asks whether MCTL can attribute the cost of its
K3s-on-Hetzner infrastructure. That cost covers nodes, the load balancer,
volumes, observability, Temporal and Argo workers. It must be attributed by
cluster, node, namespace, service and canonical tenant, using defensible custom
pricing, explicit shared and idle overhead, and an evidence-quality marker on
every number. The issue also asks whether OpenCost does this better than a
smaller report built on the existing VictoriaMetrics data (VMSingle,
kube-state-metrics, kubelet/cAdvisor, node-exporter) plus invoice
reconciliation. The issue is RESEARCH ONLY. It permits no deployment, no live
billing or tenant-data access, no cluster change and no implementation grant.

This matters for two reasons. First, the Agent FinOps ledger (mctlhq/.github#48)
already accounts for model and token spend, and it must not be conflated with
infrastructure allocation. Second, capacity and unit-economics decisions need
an estimate that is clearly labelled as one, and that never presents a list
price as an invoice. The deliverables are:

- a decision memo with a cost-attribution boundary;
- a no-duplicates map;
- a reproducible offline allocation over a synthetic three-case fixture;
- an owner-review recommendation that selects one of REUSE_EXISTING_METRICS,
  OPENCOST_OFFLINE_MODEL, BOUNDED_OPENCOST_PILOT or DEFER_PRICING_UNVERIFIABLE.

## User stories

- AS the platform owner I WANT a dated, versioned allocation rule and price
  catalog SO THAT any €/tenant figure can be traced to inputs and re-derived.
- AS the platform owner I WANT a side-by-side comparison of OpenCost and a
  VictoriaMetrics-native report SO THAT I only approve a new deployment if it
  is clearly better than what is already running.
- AS a FinOps consumer of the model-usage ledger I WANT infrastructure cost
  kept as a separate, differently labelled quantity SO THAT nobody adds
  estimated allocation to billed model charges.
- AS a tenant-isolation reviewer I WANT unknown or spoofed tenant attribution
  to stay in an explicit "unattributed" bucket SO THAT no tenant is charged for
  another party's workload.

## Acceptance criteria (EARS)

- WHEN the spike memo is delivered THE SYSTEM SHALL contain exactly one
  recommended outcome from {REUSE_EXISTING_METRICS, OPENCOST_OFFLINE_MODEL,
  BOUNDED_OPENCOST_PILOT, DEFER_PRICING_UNVERIFIABLE}, the smallest safe
  follow-up, and a statement that any live pilot needs a separate issue and an
  independent owner GO.
- WHEN the offline allocator runs over the committed three-case fixture THE
  SYSTEM SHALL produce lines for fixed platform overhead, platform compute,
  platform storage, tenant-a, tenant-b, unattributed and idle. Those lines SHALL
  sum, in integer euro cents, exactly to the fixture's declared cluster total.
- WHEN a namespace's `mctl.me/tenant` label names a tenant that has no
  `platform-gitops/tenants/<tenant>/values.yaml`, or a pod or OTLP attribute
  claims a tenant the namespace label does not confirm, THE SYSTEM SHALL assign
  that cost to `unattributed` and never to any tenant.
- WHEN the "fully loaded" view distributes shared and idle cost THE SYSTEM
  SHALL distribute it only across verified tenants, in proportion to their
  directly allocated cost, and SHALL never distribute it to `unattributed`.
- WHILE no owner-supplied price catalog with invoice provenance and an
  effective date exists THE SYSTEM SHALL mark every live €/cluster, €/namespace
  and €/tenant figure as `unknown`. Only the synthetic fixture may show euro
  values, and those values SHALL be labelled `synthetic`.
- WHILE any cost figure is displayed or serialised THE SYSTEM SHALL tag it with
  exactly one evidence class from {booked_invoiced, calculated, allocated,
  unknown}.
- IF rounding leaves a residual between the summed lines and the cluster total
  THEN THE SYSTEM SHALL resolve it with a deterministic largest-remainder rule
  and report the residual applied per line.
- IF the allocator is asked to combine infrastructure allocation with
  model-usage ledger cost THEN THE SYSTEM SHALL refuse unless both sides carry
  the same canonical tenant or execution identity. It SHALL report the two as
  separate columns and never as a single sum.
- WHEN the comparison section is written THE SYSTEM SHALL quantify, for both
  OpenCost and the VictoriaMetrics-native approach: added pods and their
  requests and limits, added active series in VMSingle, reconciliation effort
  per month, and named failure modes. Any figure that was not measured SHALL be
  marked "not observed" rather than estimated as fact.

## Out of scope

- Installing, rendering into ArgoCD, or enabling OpenCost, Kubecost or any new
  recording rule or dashboard in the cluster.
- Querying production VictoriaMetrics, the Hetzner Cloud API, Hetzner invoices
  or any billing system. Reading tenant workload data beyond what is already
  committed in Git.
- Changing the model-usage ledger (mctlhq/.github#48) or mctl-api usage
  endpoints (mctlhq/mctl-api#651).
- Starting an implementation DevLoop, approving or merging anything, or opening
  a new epic.
- Pricing for Cloudflare R2 (etcd snapshots, VM backups) beyond listing it in
  the boundary as an external, non-cluster cost line.

## Open questions

- Which Hetzner prices are contractual for this account (list price, any
  discount, VAT treatment, currency)? Pricing provenance cannot be inferred
  from Git. Until the owner supplies a dated catalog, live figures stay
  `unknown`, and that points toward DEFER_PRICING_UNVERIFIABLE for the € part.
- Allocation basis. OpenCost's spec charges max(request, usage). This proposal
  defaults rule v1 to requests, because requests are quota-aligned and
  deterministic from kube-state-metrics, and it reports usage as an efficiency
  column. Should the owner prefer max(request, usage)?
- CPU-to-RAM cost split of a node price. Hetzner sells whole instances, not
  separate core and GiB prices. Rule v1 uses a declared 50/50 split, which is a
  policy choice, not a measured fact.
- Classification of the `admins` tenant, whose workloads (mctl-agents-worker*,
  mctl-support, mctl-web, ...) are platform services. Rule v1 treats it as
  "platform" and not as a billable tenant. Owner confirmation is needed.
- Agent pods running in `argo-workflows`, and Temporal workers. They are
  platform-shared at the namespace level, and only an execution-identity join
  could attribute them per tenant. The memo leaves that join as a follow-up.
- Live namespace labels, node allocatable capacity and VMSingle series counts
  were not observed in this run (no cluster access; `mctl_list_tenants` was
  refused for this non-admin token).
