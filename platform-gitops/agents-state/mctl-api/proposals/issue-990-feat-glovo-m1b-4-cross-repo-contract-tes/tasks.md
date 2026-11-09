# Tasks: issue-990-feat-glovo-m1b-4-cross-repo-contract-tes

- [ ] 0. Gate: confirm #988, #989, #985, #986 and mctlhq/mctl-telegram#1262 are merged, and record the exported fence, order-status and read-extension constructors in `docs/glovo-p1-contract.md` — DoD: the doc lists the merged commit SHAs and the symbols the suite binds to.
- [ ] 1. Create `internal/glovo/contract/` with the PG helper (reusing the `TEST_DATABASE_URL` skip pattern from `internal/bridge/store_pg_test.go:pgStore`), per-test tenant/principal factories, and scoped cleanup (depends on 0) — DoD: an empty `TestPGGlovoContractHarness` passes locally and in CI, and touches only its own rows.
- [ ] 2. Add the golden fixtures `testdata/p1/*.json`, `testdata/PROVENANCE` (sha256 per file, plus peer references) and `TestGlovoContractFixturesMatchProvenance`. Validate the command and result fixtures against `internal/bridge/schema/*.schema.json` (depends on 1) — DoD: editing one byte of any fixture fails the test.
- [ ] 3. Implement the loopback-only fake provider with idempotent writes keyed by `command_id`, read-back, a write counter, fault knobs (`AmbiguousEffect`, `DropResultPost`, `CrashAfterPermit`, `DuplicateResultPost`) and a non-loopback dial guard (depends on 1) — DoD: its own unit tests cover each knob, and dialing a non-loopback address fails.
- [ ] 4. `TestPGGlovoContractHappyPath`: the full flow history -> preview -> basket -> prepare -> aar_ approval -> dispatch -> effect -> order status, using the real #954 fence, with every hop compared to its fixture (depends on 2, 3) — DoD: one write, `effect_state=succeeded`, order status matches the fixture.
- [ ] 5. `TestPGGlovoContractRevokeWins` and `TestPGGlovoContractWriteWins`, ordered by lock waits observed in `pg_stat_activity` (depends on 4) — DoD: revoke wins gives 0 writes, `write_fence_refused` and `effect_state=none`; write wins gives 1 audited write and every retry denied. Both pass under `-count=20`.
- [ ] 6. `TestPGGlovoContractUnknownAmbiguous`, `...UnknownWorkerRestart`, `...UnknownLostResult` and `...StaleHolder` (depends on 4) — DoD: `effect_state=unknown`, no second permit, write count is 1 or 0 as specified.
- [ ] 7. `TestPGGlovoContractExactlyOnce` with concurrent claimers, duplicate and conflicting result posts, and a re-enqueue (depends on 4) — DoD: exactly one effect per approved intent, with `replayed:true` and `result_conflict` asserted.
- [ ] 8. `TestPGGlovoContractIsolation`, a tenant x principal x path table that includes the #986 expired, revoked and wrong-digest refusals (depends on 4) — DoD: every foreign access is not-found with no field leaked, and every #986 refusal case passes.
- [ ] 9. Audit and metrics assertions shared by tasks 4-8 (capture sink plus a fresh `prometheus.Registry`) (depends on 4) — DoD: redacted effect id, principal/tenant, hashed intent, receipt id and outcome are present; no `lt_` token, raw effect id or foreign tenant appears in records or label values.
- [ ] 10. Add the "glovo P1 contract tests (fail-closed evidence)" step to `.github/workflows/validate.yml`: fail on SKIP, require PASS for every test of tasks 2 and 4-8, and upload the log as an artifact (depends on 2-9) — DoD: CI is green, and removing or skipping any listed test turns it red.
- [ ] 11. Write `docs/glovo-p1-contract.md` with the evidence map (acceptance criterion to test name) and the peer vendoring procedure. Open companion PRs that vendor the fixtures in mctl-agents#1044, mctl-telegram#1262 and #1264 (depends on 2, 10) — DoD: every peer PR has a provenance test that passes on the identical sha256 set.

## Tests
- [ ] T1. `TestGlovoContractFixturesMatchProvenance`: sha256 pin of every fixture.
- [ ] T2. `TestPGGlovoContractHappyPath`: full flow, exactly one effect.
- [ ] T3. `TestPGGlovoContractRevokeWins`: zero writes.
- [ ] T4. `TestPGGlovoContractWriteWins`: one audited write, retries denied.
- [ ] T5. `TestPGGlovoContractUnknownAmbiguous`, `...UnknownWorkerRestart`, `...UnknownLostResult`, `...StaleHolder`: unknown, no retry, no second write.
- [ ] T6. `TestPGGlovoContractExactlyOnce`: one effect under concurrent claims and duplicate posts.
- [ ] T7. `TestPGGlovoContractIsolation`: no cross-tenant or cross-principal leak, plus the #986 refusals.
- [ ] T8. The fake provider's own tests, including the non-loopback dial guard.
- [ ] T9. The suite run with `-count=20` before merge, with no flake.

## Rollback
The change is test-only and docs-only. Revert the PR to remove `internal/glovo/contract/`, the CI step and the doc. No runtime, schema or deployment state changes, so nothing needs to be undone in any environment. If only the CI step proves flaky, drop it from `validate.yml` while the tests are fixed. Note that P1 acceptance evidence is then missing until it is restored.
