# Design: issue-272-spike-edge-config-workers-kv-instant-vs

## Current state

### This repository (mctlhq/.github, clone at `e5b88650776811067ca22da6d064653e249176a3`)

- Spikes are recorded in two places:
  - a report under `docs/spikes/<name>.md`, for example
    `docs/spikes/agent-ui-ag-ui.md`, which has a "Non-claims and evidence tags"
    section (`[CODE]`, `[DEPLOYED]`, `[DOC]`, `unknown (not observed)`) and an
    "Evidence pins" table;
  - a `SpikeDefinition` manifest under `roadmap/spikes/<name>.yaml`, for example
    `roadmap/spikes/agent-ui-ag-ui.yaml` and
    `roadmap/spikes/hetzner-inference-benchmark.yaml`.
- `roadmap/schemas/spike-definition.schema.json` requires `title`, `question`,
  `lifecycle` (`proposed|parked|active|decided|archived`), `github.issue` and
  `outcomes` (at least 2). `timebox.decisionBy` is needed for `active` and
  `decision` only for `decided`; the rules are in `spike_semantic_errors` in
  `roadmap/scripts/validate.py` and tested in
  `roadmap/tests/test_validate_spike.py`. `evidence.report` must be a relative
  path inside the repo. One issue may be bound to only one SpikeDefinition.
- `AGENTS.md` lists each spike report under `# Spikes`.
- `events/README.md` defines the Valkey Streams event contract: "producer
  (mctl-telegram, mctl-api) -> Valkey Streams (platform-events) -> ... running
  Claude session". The event is disposable and the source is canonical.
- `roadmap/epics/cloudflare-iac.yaml` owns Cloudflare-as-code, including the
  `worker-routes` item (mctlhq/mctl-gitops#1179) and `mcp-portal-iac`.
- `roadmap/spikes/` has no edge-config or issue 272 manifest yet. A grep for
  `272` and `edge-config` under `roadmap/` found nothing.

### Valkey as deployed: an event bus, not a config store

- `platform-gitops/infra-components/data/valkey/statefulset.yaml`:
  `replicas: 1`, image `valkey/valkey:8.1.10-alpine`, requests `25m`/`64Mi`,
  limits `500m`/`300Mi`, plus a `redis_exporter` sidecar checking
  `mctl:events:*` streams.
- `.../valkey/configmap.yaml`: namespace `platform-events`, AOF
  `appendfsync everysec`, `maxmemory 200mb`, `maxmemory-policy noeviction`. The
  comments say streams are trimmed by producers.
- `.../valkey/externalsecret.yaml` (ACL): `default off`. The producers
  (`telegram-producer`, `github-producer`, `synthetic-producer`) may only
  `XADD`. `claude-remote` gets stream-consume commands and plain
  `get/set/...` on `~mctl:events:state:*` only. `events-observer` gets
  read-only access to the audit stream. No ACL user can read a configuration
  key namespace.
- `.../valkey/networkpolicy.yaml`: ingress only from selected `labs` pods and
  `monitoring` (exporter port). Valkey cannot be reached from outside the
  cluster, and so not from Cloudflare.
- Clients: `services/labs/claude-remote/values.yaml`
  (`MCTL_EVENTS_VALKEY_URL`), `services/labs/mctl-telegram-preview/values.yaml`
  (`EVENTS_VALKEY_URL`) and `bootstrap/templates/mctl-platform/mctl-api.yaml`
  (`EVENTS_VALKEY_URL`, `github-producer`). All of them are event producers or
  consumers.

### How runtime configuration is actually delivered today

- Kill switches and feature flags are GitOps env vars on in-cluster pods:
  `AGENT_KILL_SWITCH: "false"`, `AGENT_ENABLED`, `HUMAN_INPUT_ENABLED` in
  `services/labs/mctl-telegram-preview/values.yaml`, and the `otel.enabled`
  kill switch in `services/admins/mctl-agents-worker-exec/values.yaml`. A
  change propagates through an ArgoCD sync and a pod rollout.
- The event-wake policy is the `mctl-events-policy` ConfigMap
  (`services/labs/claude-remote/values.yaml`), mounted as
  `/etc/mctl-events/policy.json`.
- Tenant/domain to backend routing goes through Kubernetes ingress hosts in
  service `values.yaml` and Cloudflare zone configuration under
  `infrastructure/cloudflare/zones/`. Both are managed through Git and OpenTofu.
  Neither is a runtime key-value read.

### Cloudflare edge code MCTL runs

- One Worker, `mctl-landing-form`. Its routes are in
  `infrastructure/cloudflare/zones/mctl-me/workers.tf` (`mctl.me/*`,
  `*.mctl.me/*`) and the mctl-ai and mctl-ru zone files (README decision 9:
  five routes). The script and secrets stay in Wrangler (`mctlhq/mctl-web`,
  `cloudflare-worker/`). The comments say it does bot filtering and redirects
  "from the host and path it is routed".
- `infrastructure/cloudflare/account/workers-kv.tf`: ordinary Workers KV
  namespaces `mctl-web-sessions[-dev]` (sign-in sessions, TTL at most 8h) and
  `mctl-web-access-requests[-dev]`. Both hold session or request state, which
  the issue's invariant 2 bars from any config projection.
- The Cloudflare MCP portal (`infrastructure/cloudflare/portal/`, allowlists
  `*.json`) is configured by OpenTofu apply. Cloudflare itself consumes it, not
  a Worker read path.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/infra-components/data/valkey/{statefulset,configmap,externalsecret,networkpolicy}.yaml`
  (mctl-gitops `9462f41743a5be5620f3b843bc068c22ade610cb`): single-replica
  Streams bus with the ACL and network scope described above.
- `$MCTL_GITOPS_ROOT/services/labs/claude-remote/values.yaml`,
  `services/labs/mctl-telegram-preview/values.yaml`,
  `bootstrap/templates/mctl-platform/mctl-api.yaml`: the only Valkey clients,
  all on the events contract.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml` and
  `services/admins/mctl-agents-worker-exec/values.yaml`: kill switches as env
  vars and values.
- `infrastructure/cloudflare/account/workers-kv.tf`,
  `infrastructure/cloudflare/zones/mctl-me/workers.tf`,
  `infrastructure/cloudflare/README.md` (decision 9): the single Worker and its
  KV namespaces.
- `mctl_list_services(team=admins)`: `mctl-web` 7.15.2 served in-cluster for
  hosts `mctl.ai`, `mctl.ru`. No admins service is an edge runtime. No other
  tenant was listed.
- Not observed: the `mctl-landing-form` Worker source, request rates from
  metrics, Valkey command latency, the Cloudflare account's KV Instant beta
  status, and current KV Instant pricing. All are recorded under Open
  questions in requirements.md and must be `unknown (not observed)` in the
  report unless the implementer observes them.

## Proposed solution

Run the spike as a documentation-and-manifest change in this repository. Stop
at the first gate unless the evidence contradicts the investigation above.

1. **Report `docs/spikes/edge-config-kv-instant.md`**, in the same form as
   `docs/spikes/agent-ui-ag-ui.md`:
   - Non-claims (no production change, KV Instant is never canonical) and
     evidence tags.
   - Evidence pins: this repo, mctl-gitops, and mctl-web for the Worker source,
     each at a 40-hex commit.
   - **Candidate inventory**, using the issue's exact columns, one row per
     candidate:
     - model/provider/router policy: in-cluster workers, `unknown` at the edge;
     - kill switches and feature flags: env and values, in-cluster;
     - `mctl-events-policy`: ConfigMap, in-cluster;
     - tenant/domain routing: ingress and Cloudflare zone config, applied by
       OpenTofu or ArgoCD, with no runtime read;
     - capability and gateway eligibility: in-cluster mctl-api, and the
       Cloudflare portal allowlists applied by OpenTofu;
     - `mctl-landing-form` Worker: edge, but reads only code constants and
       session or request KV, if confirmed from the pinned source.
     Every candidate marks its sensitivity, and session and token data are
     excluded by invariant 2.
   - **Gate result**: no consumer reads shared runtime configuration at the
     edge on a hot path, and every config consumer is in-cluster and already
     served by env, ConfigMap or the local network. The edge round-trip
     argument therefore does not apply.
   - **Comparison table** with the issue's 11 rows. The Valkey column records
     what exists, a Streams bus with no config read path. For example, consumer
     locality is in-cluster only (NetworkPolicy) and operational ownership is
     `platform-events` infra-components. The KV Instant column holds only
     dated, private-beta-labelled limits and pricing read at run time, with no
     latency figures.
   - **Cost note**: the Valkey envelope already paid (resource requests and
     limits above) against the KV Instant cost for a hypothetical 1-snapshot
     plus pointer workload. It is shown only as a formula over size, writes and
     reads, because no workload was measured, and it carries no adoption
     recommendation.
   - **Re-open triggers**: what would turn this into `HYBRID_EDGE_CONFIG`. For
     example, a Worker or edge MCP entry point that must reject or route by
     tenant or kill switch before reaching the origin, or KV Instant reaching
     GA. Each trigger carries the issue's invariants as preconditions: a
     versioned snapshot plus `current` pointer, a narrow-only, fail-closed
     fallback, and Git-reviewed config as the source.
   - **Verdict**: `KEEP_VALKEY`, with the explicit reading that the existing
     in-cluster path is kept and nothing is added at the edge. If the Worker
     source review finds a runtime-updatable rule set, the implementer
     re-evaluates the gate. Without beta access that gives
     `DEFER_PRIVATE_BETA`, and no latency figures are invented.
2. **Manifest `roadmap/spikes/edge-config-kv-instant.yaml`**: `SpikeDefinition`,
   `metadata.owner: mctlhq/.github`, `github.issue: mctlhq/.github#272`,
   `outcomes: [KEEP_VALKEY, HYBRID_EDGE_CONFIG, ADOPT_KV_INSTANT_EDGE_CONFIG,
   DEFER_PRIVATE_BETA]`, `lifecycle: proposed` (as the issue states),
   `execution.devloop: true`, and `evidence.report` pointing at the report. No
   `decision` block: the owner records it later, as in
   `hetzner-inference-benchmark.yaml` (`decidedBy: mashkovd`).
3. **`AGENTS.md`**: add one bullet under `# Spikes` linking the report.

The report proposes the verdict, and the manifest records the decision only
after the owner makes it. This keeps the agent from recording its own approval.

## Alternatives

- **Run the full KV Instant experiment anyway** (create a namespace, Worker and
  fixture, then benchmark). Dropped: the issue makes the experiment conditional
  on a real edge candidate and on beta access. With neither shown, it would
  create Cloudflare resources and a token scope in the `cloudflare-iac`-managed
  account for a measurement nobody consumes. It would also need write access
  that this DevLoop does not hold.
- **Benchmark in-cluster Valkey `GET` latency as the "baseline"**. Dropped as a
  required step: no configuration read goes through Valkey, and the ACL has no
  user allowed to read config keys. A measurement would need a new ACL user, a
  change to deployed state that the spike forbids, and would describe a path
  nobody uses. It is kept as an optional open question.
- **Record the verdict directly as `lifecycle: decided`**. Dropped: every
  decided spike in `roadmap/spikes/` carries the owner's `decidedBy`, and the
  issue states `Lifecycle: proposed`.

## Platform impact

- Migrations: none. Only three files change in mctlhq/.github: a new report, a
  new manifest and one line in `AGENTS.md`.
- Backward compatibility: the new manifest must pass `roadmap/scripts/validate.py`.
  The corpus test `test_committed_corpus` in
  `roadmap/tests/test_validate_spike.py` validates every committed spike, and
  issue #272 must not already be bound (checked: it is not).
- Resource impact: none. No Cloudflare, Valkey or Kubernetes object is created
  or changed.
- Risks and mitigations:
  - The verdict could rest on an unobserved Worker behaviour. Mitigation: the
    report pins and cites the `mctl-web` Worker source and the gate-reopen rule
    above.
  - Stale beta pricing could be quoted as fact. Mitigation: every KV Instant
    figure is dated, sourced and labelled private-beta.
  - The verdict name `KEEP_VALKEY` could be misread as "Valkey is the config
    store". Mitigation: the report states the actual configuration path
    explicitly.
  - Invariant drift in a future follow-up. Mitigation: the report carries the
    seven invariants as preconditions for any re-open.
