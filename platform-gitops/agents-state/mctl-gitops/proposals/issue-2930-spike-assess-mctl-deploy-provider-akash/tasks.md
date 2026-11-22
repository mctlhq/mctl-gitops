# Tasks: issue-2930-spike-assess-mctl-deploy-provider-akash

Recommendation: DEFER. Tasks 1-6 are the offline Phase 0 harness that the
owner may authorize after accepting this proposal's content digest. They add
documents and a local script only: no change under `cli/mctl/`, no network
call beyond downloading the pinned `akt` release, no keys, no chain
transactions. Task 7 is the decision gate.

- [ ] 1. Pin the validator: pick one official `akt` release, record version,
  download URL, SHA-256 checksum and the date in
  `docs/spikes/akash/TOOLING.md`; resolve the `uact` vs `uakt` question by
  running the pinned `akt sdl validate` on both. — DoD: version and checksum
  pinned from an official source, denom behaviour recorded; if no official
  pinnable release exists, stop and record a no-go (design "Hard stop").
- [ ] 2. Fixture image (depends on 1): define a public, stateless,
  no-secret HTTP echo container (one port, no outbound calls, no PII) and
  record its `@sha256:` digest. — DoD: digest published in
  `docs/spikes/akash/fixture/README.md`; image pulls anonymously.
- [ ] 3. Fixture SDL (depends on 2): `docs/spikes/akash/fixture/deploy.yaml`
  matching the sample in design.md with the real digest, `version: "2.0"`,
  0.5 CPU / 512Mi / 1Gi ephemeral, one global HTTP port, region and
  `signedBy` placeholders documented. — DoD: pinned `akt sdl validate`
  exits 0.
- [ ] 4. Negative cases (depends on 3): one SDL each under
  `docs/spikes/akash/negative/` for invalid CPU, invalid memory, invalid
  storage, `persistent: true`, globally exposed database port (5432), tag-
  only image, malformed denom/amount, secret-looking env value. — DoD: a
  table records which the pinned `akt` rejects and which need an MCTL-side
  check (to be the future adapter's only added value).
- [ ] 5. Harness script (depends on 1, 3, 4):
  `docs/spikes/akash/validate.sh` runs the pinned `akt sdl validate` under
  `env -i PATH=<tooldir>` with no `HOME` keyring, over the fixture and every
  negative case, and fails if any output contains a value from a planted
  canary secret. — DoD: script deterministic across two runs and makes no
  network calls (verified by running with networking disabled).
- [ ] 6. Estimate format and cost pins (depends on 3): write the estimate
  output for the fixture using the S2 formula; pin Hetzner `cx33`/`cx43`
  prices from the plan pages with date; re-check Akash GPU averages and any
  public CPU price with date. — DoD: every number labelled
  observed-public / model-arithmetic / not-observed.
- [ ] 7. Decision gate (depends on 4, 5, 6): owner chooses C (thin
  `mctl akash sdl render|validate|estimate`) only if task 4 shows checks
  `akt` lacks; otherwise D (documentation only). — DoD: decision recorded on
  issue #2930; any implementation gets a new proposal and digest acceptance.

## Tests

- [ ] T1. Fixture SDL validates with pinned `akt sdl validate` (exit 0).
- [ ] T2. Each negative SDL from task 4 is rejected by `akt` or flagged as
  "needs MCTL check" in the results table; none is silently accepted
  without being recorded.
- [ ] T3. Canary test: a planted fake secret in an `env` entry never appears
  in harness stdout, stderr or any written file.
- [ ] T4. Offline test: harness passes with networking disabled and with no
  `MCTL_TOKEN`, `VAULT_TOKEN`, `GITHUB_TOKEN` or Akash key present.
- [ ] T5. Flag-mapping table in design.md covers all 13 flags defined in
  `cli/mctl/cmd/deploy.go` `init()` (checked by review).
- [ ] T6. Estimate output contains the "NOT an MCTL governed deployment"
  banner, the cap comparison, and no provider/bid claims.

## Rollback

Nothing is deployed or signed. Rolling back means deleting
`docs/spikes/akash/` (if Phase 0 ran) and closing this proposal as
rejected. No cluster, tenant, Vault path, chain state or CLI behaviour is
changed by this proposal or by tasks 1-6.
