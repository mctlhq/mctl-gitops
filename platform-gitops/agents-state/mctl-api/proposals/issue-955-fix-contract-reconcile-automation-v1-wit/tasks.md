# Tasks: issue-955-fix-contract-reconcile-automation-v1-wit

- [ ] 1. Replace the occurrence derivation in `internal/automation/contract/occurrence.go`:
  - domain-separated, length-prefixed `OccurrenceKey(auID, kind, OccurrenceSource)`;
  - `ScheduledSource`, `EventSource` and `ManualSource` constructors that reject empty parts;
  - no definition version in the key;
  - `ExternalKey` and `FireIdempotencyKey` unchanged.

  DoD: the old `strconv.Itoa(definitionVersion)` input is gone and the package builds.
- [ ] 2. Add `automation_occurrence_conflict` (409) to `schema.go` `httpStatus` and to
  `schema/v1/automation-error.schema.json`, and keep `automation_occurrence_duplicate`.

  DoD: `TestErrorVocabularyMatchesSchema` passes.
- [ ] 3. (depends on 1, 2) Add `claim.go` with the `ClaimStore` isolated model:
  - unique `(tenant, au_id, occurrence_key)`;
  - `wi_id`, `admitted_version`, `status` and `request_hash` stored per claim;
  - identical replay returns `replayed=true`, a conflict returns typed 409, an unavailable store
    fails closed;
  - `Close`, `Cleanup` (tombstone plus horizon) and `Reconcile` (never mints).

  Remove `OccurrenceSet`.

  DoD: the model compiles, and its doc comment states `isolated-model` with no production caller.
- [ ] 4. (depends on 2) Add `UsageAuthority` to `Inputs` in `authority.go`. `Decide` denies
  `automation_authority_unavailable` unless the value is `UsageAuthorityVerifiedMetering`.

  DoD: Commerce payment authority is never sufficient, and `liveInputs()` in tests is updated.
- [ ] 5. Split `templates.go` into `registry` and `enabledTemplates`, and add `TemplateEnabled`.
  Add `CheckSupportFire` and `SupportTokenMaxTTL = time.Hour`, citing
  `internal/auth/agent_scope.go` `AgentScopeSupport.MaxTTL`, to `support.go`.

  DoD: Support stays registered but disabled, and existing fixtures keep their codes.
- [ ] 6. (depends on 1, 2) Add `schema/v1/automation-manual-run-request.schema.json`,
  `ValidateManualRunRequest`, the server-owned prepass fields (`occurrence_key`, `principal`,
  `au_id`), and the `ManualRequests` isolated model scoped by `(principal, tenant, au_id, key)`.
  `ManualRunEnabled = false`.

  DoD: `run-bad-key.json` is `kind: "manual-run"` in `testdata/manifest.json`, and new valid and
  invalid fixtures are present.
- [ ] 7. Extend the offset-only zone rejection in `trigger.go` to `Etc/GMT[+-]N` and the GMT0
  aliases, keeping `UTC` and `Etc/UTC` allowed. Add `testdata/invalid/offset-zone-etc.json`.

  DoD: the fixture returns `automation_invalid`.
- [ ] 8. (depends on 1-7) Rewrite `docs/automation-contract.md`:
  - section 1: the contract-only, not-enforcement statement and the forbidden-artifact list;
  - section 2: the new key, replay and conflict rules, plus a new section 2.1 on the durable
    claim, tombstone and reconciliation;
  - section 3: the `run` row references the manual-run schema, and create idempotency is scoped
    by principal and tenant;
  - section 5: registry versus enabled allowlist;
  - section 7: 403 before lookup, the byte-identical 404, and usage authority `unknown`, distinct
    from Commerce payment;
  - section 8: per-fire consent plus a fresh token at most 1h, no self-mint, no `auth_ref` by
    presence, mctl-api#901 not assumed;
  - section 9: stable producer event ID;
  - section 11: the crosswalk;
  - section 12: `automation-api-store` hard-gated on section 2.1, and this issue does not approve
    it.

  DoD: every changed statement carries a claim class.
- [ ] 9. (depends on 8) In the PR description:
  - a section-by-section comparison of the final doc against mctl-gitops#2452 and merged #950;
  - a note that #2452 was not part of the #948 approval;
  - the toolchain reproduction result for the Agy `FAIL:P2` (not reproduced) and the P3 fix.

  DoD: an independent review of the new PR has been requested.

## Tests

All tests go in `internal/automation/contract/contract_test.go` or new `*_test.go` files in the
package.

- [ ] T1. Replay across definition version: the same `au_`, kind and instant give the same key,
  and the claim with admitted versions 1 then 2 gives `replayed=true` with the original `wi_` and
  admitted version 1.
- [ ] T2. Transport IDs: two deliveries with different delivery IDs and the same `(producer, type,
  stable id)` give one key.
- [ ] T3. Disambiguation:
  - different producers or event types with the same stable ID give different keys;
  - length-prefix collision cases (for example `("a|b","c")` versus `("a","b|c")`) differ;
  - the key for event `x` differs from the key for manual `x`.
- [ ] T4. Terminal plus tombstone: `Close` then `Cleanup`, then replay gives `replayed=true`, the
  same `wi_`, and `mint` is not called. After the horizon, the behaviour is documented and tested.
- [ ] T5. Crash recovery: a `claimed` row with no `wi_`. `Reconcile` with a found external key
  resolves to that `wi_`. With none found it marks `failed`. With an error it returns
  `automation_authority_unavailable`. `mint` is never called.
- [ ] T6. Conflict: the same key with a different tenant, `au_` or hash returns
  `automation_occurrence_conflict` (409), with no second `wi_`.
- [ ] T7. Parallel claim under `-race`: N goroutines claim the same key, `mint` runs exactly once,
  and the others see `replayed=true`.
- [ ] T8. Manual request:
  - identical replay gives `replayed`;
  - a different body gives `automation_idempotency_key_reused`;
  - the same key from another principal, tenant or `au_` gives a different occurrence;
  - execution gives `automation_trigger_unsupported`;
  - a spoofed `occurrence_key` gives `automation_server_owned_field`.
- [ ] T9. Support fire:
  - expired token, token TTL > 1h, `TokenMintedBy=self`, token not minted for this fire, consent
    not live, consent not independently verified, `auth_ref` present but not live: each gives
    `automation_support_constraint`;
  - a 24h definition with a valid 1h token passes `CheckSupportFire` while the template is still
    not enabled.
- [ ] T10. Support disabled: a schema-valid Support create gives `automation_trigger_unsupported`,
  `LookupTemplate` finds it, and `TemplateEnabled` is false.
- [ ] T11. Unknown budget source: `UsageAuthorityUnknown` and `UsageAuthorityCommercePayment` give
  `automation_authority_unavailable` even with ample headroom.
- [ ] T12. 403/404 anti-oracle:
  - an unlinked caller gets 403 for every combination of `TargetExists`, `OwnerMatches` and
    `TenantAccessible`;
  - absent, foreign-owner and foreign-tenant give an identical `ErrorBody` and 404.
- [ ] T13. Toolchain: `time.Parse(time.RFC3339, ...)` accepts `.123456789Z` and `.5+02:00` (fixture
  `valid/reminder-at-instant-fractional.json`), and a closure-capture loop asserts per-iteration
  semantics.
- [ ] T14. Zones: `Etc/GMT+5`, `Etc/GMT-14`, `Etc/GMT0` and `GMT+0` give `automation_invalid`;
  `UTC`, `Etc/UTC` and `America/New_York` are accepted.
- [ ] T15. `go test -race ./internal/automation/...`, `go vet ./...` and `golangci-lint run` pass,
  and `grep -rn "internal/automation/contract" --include=*.go` shows no non-test importer outside
  the package.

## Rollback

This is a docs and isolated-model change with no runtime caller. Roll back by reverting the
implementation PR's merge commit, which restores the #950 contract. No data, migration or
deployment to undo.
