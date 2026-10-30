# Spike: Workers KV Instant vs Valkey for global runtime configuration (edge-config)

## Context

Issue mctlhq/.github#272 asks for a decision spike: does MCTL have a real,
globally distributed, read-hot runtime-configuration path where Cloudflare
Workers KV Instant (private beta, Quicksilver-backed, 1 MB / 10k keys per
namespace, expensive writes) materially beats the existing local Valkey path?
The spike must return exactly one verdict out of `KEEP_VALKEY`,
`HYBRID_EDGE_CONFIG`, `ADOPT_KV_INSTANT_EDGE_CONFIG` and `DEFER_PRIVATE_BETA`.
It is a decision spike, not a migration. A first gate requires proof of a real
edge consumer before any benchmark is run.

Investigation of the deployed state already shapes the expected result. The
platform Valkey (`platform-events/valkey`, one replica, `maxmemory 200mb`,
`noeviction`) is an event bus (Valkey Streams `mctl:events:*`) and not a
runtime-configuration store. Its ACL grants plain key reads only to
`claude-remote` on `mctl:events:state:*`. Runtime switches such as
`AGENT_KILL_SWITCH`, `AGENT_ENABLED` and the `mctl-events-policy` are delivered
as GitOps env vars or ConfigMaps to in-cluster pods. The only Cloudflare-edge
code MCTL runs is the `mctl-landing-form` Worker (routes on `mctl.ai/api/*`,
`mctl.me`, `mctl.ru`). It uses ordinary Workers KV for sign-in sessions and
access requests, and it reads no shared runtime policy. The spike therefore has
to record this inventory with evidence and, unless the inventory finds an edge
consumer that this investigation missed, stop at the first gate with
`KEEP_VALKEY`. It records the result as a report plus a `SpikeDefinition`
manifest in this repository, so the roadmap control plane can track the
decision.

## User stories

- AS the platform owner I WANT an evidence-backed inventory of every hot-path
  runtime-configuration read, with where its consumer runs, SO THAT I can see
  whether any consumer actually needs edge-local reads.
- AS the platform owner I WANT exactly one verdict with a cost and coupling
  rationale SO THAT KV Instant is adopted only when there is a real edge
  requirement and a bounded cost envelope.
- AS a roadmap reader I WANT the spike recorded as a validated
  `SpikeDefinition` in `roadmap/spikes/` SO THAT its lifecycle and verdict are
  machine-readable, like the other decided spikes.
- AS a security reviewer I WANT the governance invariants (projection only, no
  secrets or session state, fail-safe fallback, atomic snapshots) written down
  as preconditions SO THAT any future hybrid follow-up inherits them.

## Acceptance criteria (EARS)

- WHEN the spike report is written THE SYSTEM SHALL contain a candidate
  inventory table with the columns `consumer | current source | where consumer
  runs | read rate | write/change rate | consistency need | payload size |
  sensitivity`. It SHALL cover at least model/provider/router policy, feature
  flags and kill switches, tenant/domain to backend routing, capability and
  gateway eligibility, and the `mctl-landing-form` Worker.
- WHEN a cell in the inventory or the comparison table was not observed THE
  SYSTEM SHALL mark it `unknown (not observed)` and SHALL NOT treat it as
  absent or zero.
- WHEN every candidate consumer runs inside the MCTL cluster, or no edge
  consumer reads shared runtime configuration on a hot path, THE SYSTEM SHALL
  record the verdict `KEEP_VALKEY` and SHALL NOT run the KV Instant experiment.
- IF the inventory proves a real edge consumer AND KV Instant beta access is
  unavailable THEN THE SYSTEM SHALL record `DEFER_PRIVATE_BETA` and SHALL NOT
  publish latency figures for KV Instant.
- IF the inventory proves a real edge consumer AND beta access is available
  THEN THE SYSTEM SHALL require one immutable, versioned snapshot plus a
  `current` pointer, measured p50/p95/p99, cold read, propagation, origin-down
  and rollback behaviour, and a cost model from measured bytes and rates,
  before a `HYBRID_EDGE_CONFIG` or `ADOPT_KV_INSTANT_EDGE_CONFIG` verdict.
- WHEN the report cites KV Instant limits or pricing THE SYSTEM SHALL state the
  date and source of the reading and SHALL label them as private-beta and not
  stable.
- WHEN the report compares costs THE SYSTEM SHALL state the current Valkey cost
  as its in-cluster resource envelope (requests `25m` CPU / `64Mi`, limits
  `500m` / `300Mi`, single replica). It SHALL NOT invent a monetary figure that
  was not observed.
- WHILE the spike is open THE SYSTEM SHALL NOT change any deployed
  configuration, Cloudflare resource, Valkey resource or service.
- WHEN the manifest `roadmap/spikes/edge-config-kv-instant.yaml` is added THE
  SYSTEM SHALL pass `python roadmap/scripts/validate.py` and
  `python -m unittest discover roadmap/tests`. Its `outcomes` SHALL be exactly
  the four verdicts from the issue, and `evidence.report` SHALL point at the
  report.
- IF the owner has not yet recorded a decision THEN THE SYSTEM SHALL leave the
  manifest at `lifecycle: proposed` with no `decision` block. The proposed
  verdict lives in the report only.
- WHEN the report describes any future edge projection THE SYSTEM SHALL keep
  the issue's seven security and governance invariants as preconditions:
  projection only, no session, approval, audit, receipt, secret, token or
  message body content, safe fallback, narrow-only, atomic versioned snapshots,
  Valkey kept, and no production cutover.

## Out of scope

- Replacing, resizing or re-purposing the platform Valkey.
- Creating any Workers KV or KV Instant namespace, Worker, route or token.
- Moving any policy authority, session or approval state to Cloudflare.
- Redesigning model routing, the MCP gateway or the Cloudflare MCP portal.
- Production migration or traffic cutover.
- Changing the existing `mctl_web_sessions` or `mctl_web_access_requests`
  Workers KV namespaces.

## Open questions

- The issue's baseline assumes a "local Valkey path" for runtime configuration.
  None exists today: Valkey is a Streams bus and configuration arrives through
  env vars and ConfigMaps. The proposal reads `KEEP_VALKEY` as "keep the
  current in-cluster configuration path; add no edge store". The owner should
  confirm that reading of the verdict name.
- The `mctl-landing-form` Worker source (`mctlhq/mctl-web`,
  `cloudflare-worker/`) is not in this clone. Whether its bot filter or
  redirect logic reads any runtime-updatable rule set, rather than code
  constants, is `unknown (not observed)`. The implementer must read that source
  at a pinned commit. If it does read such a rule set, the first gate changes.
- Read and change rates (requests per second for each consumer, flips per month
  for each kill switch) were not observed. The report must either take them
  from metrics or mark them unknown. The first-gate verdict does not depend on
  them when no edge consumer exists.
- Whether the owner wants a measured in-cluster Valkey `GET` latency baseline
  anyway, even with no config consumer. The proposal treats it as optional.
- KV Instant beta access for the MCTL Cloudflare account is unknown. It does
  not matter for `KEEP_VALKEY`, but it would decide between
  `DEFER_PRIVATE_BETA` and the experiment if an edge consumer turns up.
