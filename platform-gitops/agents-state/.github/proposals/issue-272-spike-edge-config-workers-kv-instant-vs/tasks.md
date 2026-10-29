# Tasks: issue-272-spike-edge-config-workers-kv-instant-vs

- [ ] 1. Pin the evidence: record the 40-hex commits of mctlhq/.github,
  mctlhq/mctl-gitops and mctlhq/mctl-web (`cloudflare-worker/`) that were read.
  Read the `mctl-landing-form` Worker source and note whether it consumes any
  runtime-updatable rule or config, or only code constants and the session or
  access-request KV. — DoD: the pins table is in the report, and the Worker
  finding is tagged `[CODE]` with file paths, or marked
  `unknown (not observed)`.
- [ ] 2. Build the candidate inventory (depends on 1): one row for each of
  model/provider/router policy, kill switches and feature flags
  (`AGENT_KILL_SWITCH`, `otel.enabled`), `mctl-events-policy`, tenant/domain
  routing, capability and gateway eligibility (mctl-api and the portal
  allowlists), and the `mctl-landing-form` Worker. Use the issue's eight
  columns, and give every cell an evidence tag or `unknown (not observed)`.
  — DoD: the table is complete, no cell is guessed, and session or token data
  are marked excluded.
- [ ] 3. Write the Valkey current-state section from
  `infra-components/data/valkey/*` (depends on 1): replicas, memory policy,
  ACL users, NetworkPolicy scope, clients, and the statement that no config is
  read from Valkey. — DoD: every claim cites a gitops path at the pinned
  commit.
- [ ] 4. Take the KV Instant snapshot at run time: availability (private beta),
  namespace limits, and read, write and storage pricing, each with the source
  URL and read date, labelled not stable. Record whether the MCTL account has
  beta access, or `unknown`. — DoD: the section is dated, and no latency
  figure appears for KV Instant.
- [ ] 5. Write the 11-row comparison table and the cost note (depends on 3, 4):
  the Valkey resource envelope against a KV Instant cost formula over snapshot
  size, writes per month and reads per month. — DoD: no invented monetary or
  latency number, and unmeasured cells are marked.
- [ ] 6. Apply the first gate and write the verdict (depends on 2, 5):
  `KEEP_VALKEY` if no edge hot-path config consumer exists; otherwise
  `DEFER_PRIVATE_BETA` when beta access is unavailable. Add the re-open
  triggers and the seven governance invariants as preconditions. — DoD: exactly
  one verdict, with a reason that names the gate evidence.
- [ ] 7. Write `docs/spikes/edge-config-kv-instant.md` from tasks 1-6, in the
  structure of `docs/spikes/agent-ui-ag-ui.md`. — DoD: the file exists and
  contains no secrets, tokens or message bodies.
- [ ] 8. Add `roadmap/spikes/edge-config-kv-instant.yaml` (`SpikeDefinition`,
  owner `mctlhq/.github`, issue mctlhq/.github#272, the four outcomes,
  `lifecycle: proposed`, `execution.devloop: true`,
  `evidence.report: docs/spikes/edge-config-kv-instant.md`, no `decision`).
  — DoD: the schema and the semantic validator pass.
- [ ] 9. Add one bullet under `# Spikes` in `AGENTS.md` linking the report for
  mctlhq/.github#272. — DoD: the link resolves.

## Tests

- [ ] T1. `python roadmap/scripts/validate.py` passes on the default corpus
  (`roadmap/epics roadmap/spikes`), including the new manifest.
- [ ] T2. `python -m unittest discover roadmap/tests` passes, including
  `test_committed_corpus` in `roadmap/tests/test_validate_spike.py` and the duplicate issue
  binding checks.
- [ ] T3. Manual check: the manifest's `outcomes` equal the issue's four
  verdict strings exactly, and the report's verdict is one of them.
- [ ] T4. Manual check: a grep of the report for `password`, `token=`, `sess:`
  values and bearer strings finds no secret material, only path and key-pattern
  references.

## Rollback

Revert the single PR. It adds two files and one `AGENTS.md` line and changes no
deployed state, Cloudflare resource or Valkey object, so a revert restores the
previous state completely.
