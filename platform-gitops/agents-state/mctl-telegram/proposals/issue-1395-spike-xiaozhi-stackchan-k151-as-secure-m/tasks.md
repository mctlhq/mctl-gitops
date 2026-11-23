# Tasks: issue-1395-spike-xiaozhi-stackchan-k151-as-secure-m

Research and specification tasks only. A **separate owner-limited B1 GO** has been recorded in #1409 for a test-only branch / draft PR #1410. That is not a #1395 Temporal approval and does not authorize production implementation, deployment, device enrollment, firmware flashing, credential issue or procurement. Review disposition: `evidence/review-disposition.md`. Each barrier marked **[OWNER GO]** needs a separate, recorded owner decision.

- [ ] 1. X1 protocol evidence: re-verify the claims in design.md "Upstream evidence" at the four pinned SHAs. Add file:line citations for each message type and for the v1/v2/v3 framing. Read `main/protocols/mqtt_protocol.cc`, `main/mcp_server.cc`, `main/application.cc` (listen, abort, interrupt) and the community server's auth, OTA and plugin egress. Answer the open questions on `ws://` acceptance and TLS pinning, factory-firmware URL configurability, and the licenses of `m5stack/StackChan` `app/` and `remote/`. — DoD: `evidence/x1-protocol.md` with every row marked verified-at-SHA or doc-only; G-TLS, G-VENDOR and G-LIC each resolved or restated with evidence.
- [ ] 2. X2 architecture and security (depends on 1): finalize the A/B/C matrix with the X1 facts. Draft an ADR addendum to ADR 0011 for I2 (paired-device principal source), T6 (voice disclosure), T13 (new `desk-voice-data-flow/v1` consent) and device revocation fencing. — DoD: draft addendum text in the proposal directory for review, not merged into `docs/adr`; an invariant-delta table covering I1-I10 and T11-T13; G-ID and G-DISC residuals stated for owner acceptance or refusal.
- [ ] 3. X3 simulator specification (depends on 1): **PARTIAL:** draft CI-only code at mctl-telegram#1410 passed 17/17 local Python tests; CI and pin-level upstream interoperability are not yet accepted. Corrected optional server hello, v1/v2/v3 length validation and modern/legacy MCP shape tests.  turn design.md "Harness design" into a test plan. Cover fixture manifest format, assertion ids S-H1..S-X1, `report.json` JSON Schema with no free-text fields, the credential-refusal precondition and the loopback dialer guard. — DoD: `evidence/x3-harness-spec.md` plus the schema; a reviewer can implement it without reading upstream again.
- [ ] 4. X4 product validation (depends on 2 and 3): fix the U1/U2 scripts, the 50-turn fixture set, the measurement method for each target, and the cost model per 100 turns for at least two Russian-capable ASR/TTS options. — DoD: `evidence/x4-validation.md` with targets labelled "proposed", and go/no-go criteria for harness, one-K151 purchase and productization.
- [ ] 5. Decision package (depends on 1-4): restate the recommendation (`GO_FOR_HARNESS_ONLY` / `DEFER` / `NO_GO`) with the P1/P2/P3 gate table updated. — DoD: a single summary comment on #1395 linking this proposal, with status still `proposed`.

Barriers (not tasks in this proposal):
- **[OWNER GO]** B1: owner has authorized **only** the isolated `mctl-telegram/test/xiaozhi-sim/` CI-only loopback-only draft in #1409/#1410. No merge without further owner GO. Existing #1395 Temporal approve is explicitly excluded; do not signal it.
- **[OWNER GO]** B2: buy one K151 and do a bench bring-up with self-hosted OTA, no vendor cloud and synthetic data only.
- **[OWNER GO]** B3: merge the ADR 0011 addendum, then and only then design any link to the PA runtime.
- **[OWNER GO]** B4: any private data, write tool or spoken disclosure, which requires its own threat model.

## Tests

- [ ] T1. Evidence check: every protocol claim in X1 cites a path at a pinned 40-character SHA, and a reviewer spot-checks five at random with `gh api repos/<r>/contents/<path>?ref=<sha>`.
- [ ] T2. Consistency: requirements.md, design.md, tasks.md and the X1-X4 outputs give the same recommendation and the same gate set.
- [ ] T3. Harness specification review: **the 17 local harness tests are not a K151 interoperability certification.**  each assertion S-H1..S-X1 has a fixture, an expected outcome and a failure message. None needs a network credential, a vendor endpoint or a real Telegram identifier.
- [ ] T4. Fixture hygiene: `git grep` over the spec shows only the personas `Alice`, `Bob`, `Carol` and `Dana`, locally administered MACs and existing synthetic ids.
- [ ] T5. Report-safety review: the `report.json` schema has no string field that can carry a transcript, a token or audio. Allowed fields are labels and enums, counts, durations and SHAs.

## Rollback

Nothing is deployed or changed, so there is nothing to roll back in any service. To abandon the spike, close the proposal as rejected and delete its `evidence/` drafts; no repo, flag, credential or device state exists to clean up. If a later barrier (B1-B4) is approved and then abandoned, its own proposal carries its rollback: flags off, socket closed, device tokens revoked and pairing rows revoked.
