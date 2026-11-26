# Tasks: issue-2930-spike-assess-mctl-deploy-provider-akash

Recommendation: DEFER. Tasks 1-6 are a **possible**, bounded offline
Phase 0 harness, **not authorized by this review**. Proposal approval in
an active Temporal DevLoop may start an implementer; do **not** send an
approval signal until the revised proposal is merged, its new content
digest is reviewed, and the owner separately grants `GO_OFFLINE_HARNESS`.
Networked preparation to obtain release archives/checksums and a public
fixture image digest is separate from **network-disabled validation**.
No code under `cli/mctl/`, funded accounts, keys or transactions.
Task 7 is the decision gate.

- [ ] 1. **Networked preparation, separate from offline test:** candidate
  upstream `akt` release **v1.1.2**; independently fetch official archive
  and published SHA-256 checksum; record URL, artifact name, expected vs
  computed SHA-256, platform/architecture, binary-reported version, date
  and provenance in `docs/spikes/akash/TOOLING.md`. No `latest` resolver
  during tests. If no verifiable artifact exists, STOP. Do not assume the
  GitHub release page proves we have downloaded or validated the binary.
- [ ] 2. Fixture image (networked preparation; depends on 1): select a
  small public, stateless, no-secret HTTP echo image with an independently
  verified `@sha256:` digest. Do not create/publish a new image unless
  separately approved. — DoD: exact public image/digest, provenance and
  known behavior documented; if possible, verify no application-initiated
  egress in isolation, without asserting a third-party runtime cannot egress.
- [ ] 3. Minimal SDL (depends on 2):
  `docs/spikes/akash/fixture/deploy.yaml` with real digest, version 2.0,
  0.5 CPU / 512Mi / 1Gi ephemeral, one global HTTP port and `uact` price;
  **no placeholders for signedBy, provider or region**. Compare with output
  from `akt sdl init web` to catch schema drift. — DoD: pinned
  `akt sdl validate` exits 0 **and** the separate MCTL preflight policy
  passes.
- [ ] 4. Negative cases (depends on 3): under
  `docs/spikes/akash/negative/` create **non-sensitive** variants for
  invalid CPU/memory/storage, `persistent: true`, global 5432, an image
  with an explicit tag but **without digest**, `uakt`, malformed price,
  private registry `credentials`, and forbidden env key. — DoD: a matrix
  distinguishes native-validator FAIL/WARN/PASS from **MCTL preflight
  PASS/FAIL**; no unsafe SDL is silently accepted because `akt` returned
  0. Use only benign literal values in committed fixtures.
- [ ] 5. Harness script (depends on 1, 3, 4):
  `docs/spikes/akash/validate.sh` runs MCTL preflight **before** `akt`;
  only valid/preflight-safe cases reach pinned `akt sdl validate`. Scrub
  subprocess environment including MCTL/Vault/GitHub/Akash tokens; use
  disposable empty HOME, XDG and AKT_HOME with read-only inputs. Create
  a fake secret canary **in memory only** and assert that rejection occurs
  before rendering/subprocess and that stdout/stderr/files never contain
  it. — DoD: two deterministic runs inside a network-disabled sandbox;
  no wallet/keys read, no canary committed/written and no network access.
- [ ] 6. Estimate and costs (depends on 3): calculate the hypothetical
  fixture ceiling in `uact`/ACT (not `uakt`/AKT), document 1:1 USD nominal
  accounting from upstream `akt` docs, keep actual rate/fees as unknown,
  and label the offline max-monthly cap **advisory, not enforceable**.
  Distinguish keyring escrow+gas from Console credits. Pin comparable
  Hetzner `cx33`/`cx43` prices and Akash CPU (if actually observable),
  published GPU averages with dates and regions. — DoD: every figure
  labelled observed-public/model-arithmetic/not-observed and **no live bid
  claims or unsupported cost savings**.
- [ ] 7. Decision gate (depends on 4, 5, 6): independent reviewer records
  PASS/HOLD and any P1/P2/P3. The owner then chooses C (thin local SDL
  adapter) **only if** additional preflight policy brings clear value; else
  D (document official `akt`). — DoD: evidence and decision recorded on
  #2930. Any CLI adapter or funded deployment needs **another proposal and
  owner approval**; this harness is never itself a deployment GO.

## Tests

- [ ] T1. Fixture SDL validates with pinned `akt sdl validate` (exit 0).
- [ ] T2. Every negative SDL reports separate native-validator result and
  MCTL-policy result; explicit-tag-without-digest and `uakt` fail policy
  even if upstream validator passes/warns.
- [ ] T3. Runtime-only fake canary is rejected before render/subprocess and
  absent from stdout, stderr, input fixtures, tempfiles and repo history.
- [ ] T4. Offline test: harness passes with network access denied, scrubbed
  env and disposable empty HOME/XDG/AKT_HOME, no mounted
  `MCTL_TOKEN`, `VAULT_TOKEN`, `GITHUB_TOKEN` or Akash keys.
- [ ] T5. Flag-mapping table in design.md covers all 13 flags defined in
  `cli/mctl/cmd/deploy.go` `init()` (checked by review).
- [ ] T6. Estimate contains "NOT an MCTL governed deployment", advisory
  cap, correctly labelled uact/ACT, two funding paths, and no provider/bid
  claims. No use of AKT spot price to value ACT.
- [ ] T7. Owner gate: Temporal DevLoop remains unapproved until post-merge
  digest and explicit `GO_OFFLINE_HARNESS`; no implementer under this PR.

## Rollback

Nothing is deployed or signed. Rolling back means deleting
`docs/spikes/akash/` (if Phase 0 ran) and closing this proposal as
rejected. No cluster, tenant, Vault path, chain state or CLI behaviour is
changed by this proposal or by tasks 1-6.
