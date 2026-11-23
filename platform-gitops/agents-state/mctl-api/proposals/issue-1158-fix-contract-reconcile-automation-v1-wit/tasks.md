# Tasks: issue-1158-fix-contract-reconcile-automation-v1-wit

Scope guard: only `docs/automation-contract.md` and `internal/automation/contract/**` change,
including schemas, fixtures and tests.

- [ ] 1. Rewrite the occurrence derivation in `internal/automation/contract/occurrence.go`.
  - Add `OccurrenceSource` with the constructors `ScheduledSource(time.Time)`,
    `EventSource(producer, eventType, stableID)` and `ManualSource(principal, tenant, callerKey)`.
    Each rejects an empty part with `automation_invalid`.
  - `OccurrenceKey(auID, triggerKind, src) (string, error)` hashes the domain tag
    `mctl.automation.occurrence.v1` followed by `uint32be(len)||bytes` fields. The output format
    stays `occ_ + 32 hex`.
  - Drop the definition version and `OccurrenceKeyAt`. Keep `ExternalKey` and
    `FireIdempotencyKey` as they are.

  DoD: `strconv.Itoa(definitionVersion)` is gone and the package builds.
- [ ] 2. Add `CodeOccurrenceConflict = "automation_occurrence_conflict"` (409) to `schema.go`
  `httpStatus` and to `schema/v1/automation-error.schema.json`. Keep `CodeOccurrenceDuplicate`,
  with its doc comment saying it is reserved and not emitted for an identical replay.

  DoD: `TestErrorVocabularyMatchesSchema` passes.
- [ ] 3. (depends on 1, 2) Add `claim.go` with the isolated model `ClaimStore`. Remove
  `OccurrenceSet`.
  - Mutex-guarded, unique on `(tenant, au_id, occurrence_key)`. Each claim stores `WorkItemID`,
    `AdmittedVersion`, `Status` (`claimed|bound|closed|tombstoned|failed`) and `RequestHash`.
  - `Claim(req, mint)`: an identical replay returns `Replayed=true` with the original `wi_` and
    admitted version. A different tenant, `au_` or hash returns `automation_occurrence_conflict`.
    `Unavailable` returns `automation_authority_unavailable`. `mint` is called at most once per
    key.
  - `Close(key, at)` and `Cleanup(now, horizon)` handle the tombstone. Add the constant
    `DefaultTombstoneHorizon = 30 * 24 * time.Hour`.
  - `Reconcile(key, lookup)` binds to a found `wi_`, marks `failed` when none is found, and
    returns unavailable on error. It never mints.

  DoD: the doc comment says `isolated-model` with no production caller.
- [ ] 4. (depends on 2) Add `UsageAuthority` (`Unknown` as the zero value, `CommercePayment`,
  `VerifiedMetering`) and `Inputs.UsageAuthority` in `authority.go`. Before the budget check,
  `Decide` denies with `automation_authority_unavailable` unless the value is `VerifiedMetering`.
  Update `liveInputs()` in the tests.

  DoD: Commerce payment authority alone is never sufficient.
- [ ] 5. Split the templates and add the Support fire check.
  - In `templates.go`, rename `templates` to `registry`. Add `enabledTemplates` (moved from
    `mvpTriggers` in `trigger.go`) and `TemplateEnabled(id, kind)`. `CheckTrigger` uses it.
  - In `support.go`, add `SupportTokenMaxTTL = time.Hour`, citing `internal/auth/agent_scope.go`
    `AgentScopeSupport.MaxTTL`. Add `SupportFireInputs` and `CheckSupportFire`, which checks live
    and independently verified consent, a token minted for this fire through the owner path (not
    self), TTL at most 1h, not expired, and no `auth_ref` by presence.

  DoD: Support is registered but not enabled, and every existing fixture keeps its code.
- [ ] 6. (depends on 1, 2) Add the manual-run request.
  - New `schema/v1/automation-manual-run-request.schema.json`.
  - New `manual.go` with `ValidateManualRunRequest`. Its server-owned prepass adds
    `occurrence_key`, `principal` and `au_id`.
  - Isolated model `ManualRequests`, keyed `(principal, tenant, au_id, key)` with a body hash.
  - `ManualRunEnabled = false`.
  - Add the manifest kind `manual-run` in `TestFixtures`, with valid and invalid fixtures.

  DoD: the fixtures pass with the expected codes.
- [ ] 7. In `trigger.go`, refuse GMT-family zones with a numeric suffix
  (`^(Etc/)?GMT[+-]?[0-9]+$`) with `automation_invalid`. Add
  `testdata/invalid/offset-zone-etc.json` to the manifest.

  DoD: `Etc/GMT+2` is refused, and `UTC`, `Etc/UTC`, `GMT` and `Etc/GMT` are accepted.
- [ ] 8. (depends on 1-7) Update `docs/automation-contract.md`.
  - Section 1: add a contract-only statement and the list of forbidden artifacts (route, MCP
    tool, table or migration, Schedule, worker, flag, GitOps release, Support enablement,
    downstream issue).
  - Section 2: the new key formula, replay (`replayed: true`) and conflict (409) rules, and the
    admitted version snapshotted separately.
  - New section 2.1: the durable claim, tombstone horizon and crash reconciliation.
  - Section 3: the `run` row references `automation-manual-run-request`, and create idempotency is
    scoped by principal and tenant.
  - Section 5: the registry is separate from the enabled allowlist.
  - Section 7: 403 before lookup, a byte-identical 404, and usage authority `unknown`, separate
    from Commerce payer/month payment.
  - Section 8: per-fire consent and a fresh token of at most 1h, no self-mint, no `auth_ref` by
    presence, and mctl-api#901 not assumed.
  - Section 9: stable producer event ID instead of delivery ID.
  - Section 12: `automation-api-store` is hard-gated on section 2.1, and this issue does not
    approve it.
  - Update the open questions.

  DoD: every changed statement carries a claim class.
- [ ] 9. (depends on 8) In the PR description, compare #950 with mctl-gitops#2452 section by
  section. State that #2452 was not part of the #948 approval. Record the toolchain reproduction:
  Agy `FAIL:P2` not reproduced on go 1.26.11, and the P3 zone fix.

  DoD: an independent review of the new PR has been requested.

## Tests

All tests go in `internal/automation/contract/*_test.go`.

- [ ] T1. Replay across definition version: the key is the same, and claims with admitted
  versions 1 then 2 return `replayed=true` with the original `wi_` and admitted version 1.
- [ ] T2. Two different transport or delivery IDs with the same `(producer, type, stable id)` give
  one key.
- [ ] T3. Disambiguation:
  - a different producer or a different type gives a different key;
  - length-prefix collision pairs (`("a|b","c")` against `("a","b|c")`) give different keys;
  - the event source `x` and the manual source `x` give different keys;
  - an empty part gives `automation_invalid`.
- [ ] T4. Terminal WorkItem plus tombstone:
  - `Close`, then `Cleanup` inside the horizon, then a replay returns `replayed=true` and `mint`
    is not called;
  - after the horizon, the behaviour is the documented one and is asserted.
- [ ] T5. Crash recovery: a `claimed` row without a `wi_` is reconciled in three cases (found,
  not found, lookup error), and `mint` is never called.
- [ ] T6. Conflicting reuse (different tenant, `au_` or hash) returns
  `automation_occurrence_conflict` (409), and no second `wi_` is minted.
- [ ] T7. Under `-race`, 32 goroutines claim one key. `mint` runs exactly once, and every other
  claim gets `replayed=true`.
- [ ] T8. Manual request:
  - a replay returns `replayed`;
  - a different body returns `automation_idempotency_key_reused`;
  - another principal, tenant or `au_` gives a different occurrence;
  - execution returns `automation_trigger_unsupported`;
  - a spoofed `occurrence_key` returns `automation_server_owned_field`.
- [ ] T9. Support fire:
  - each of these returns `automation_support_constraint`: expired token, token TTL over 1h,
    self-minted token, token not minted for this fire, consent not live, consent not verified,
    `auth_ref` not live;
  - a 24h definition with a valid 1h token passes `CheckSupportFire`.
- [ ] T10. A schema-valid Support create still returns `automation_trigger_unsupported`.
  `LookupTemplate` finds the template and `TemplateEnabled` is false.
- [ ] T11. With `UsageAuthorityUnknown` or `CommercePayment`, `Decide` returns
  `automation_authority_unavailable` even with ample headroom.
- [ ] T12. 403/404 anti-oracle:
  - an unlinked caller gets 403 for all 8 combinations of `TargetExists`, `OwnerMatches` and
    `TenantAccessible`;
  - absent, foreign-owner and foreign-tenant callers get a byte-identical `ErrorBody` with 404.
- [ ] T13. Toolchain:
  - `time.Parse(time.RFC3339, ...)` accepts `.5Z`, `.123456789+02:00` and `.1234567891Z`
    (truncated) on the repo toolchain;
  - new fixture `valid/reminder-at-instant-fractional.json`;
  - a closure-capture loop test asserts per-iteration loop variables.
- [ ] T14. Zones:
  - `Etc/GMT+5`, `Etc/GMT-14`, `Etc/GMT0` and `GMT+0` return `automation_invalid`;
  - `UTC`, `Etc/UTC`, `GMT`, `Etc/GMT` and `America/New_York` are accepted.
- [ ] T15. `go test -race ./internal/automation/...`, `go test -p 1 ./...`, `go vet ./...` and
  `golangci-lint run` pass. A grep shows no importer of `internal/automation/contract` outside the
  package, and the MCP tool count in `server_test.go` is unchanged.

## Rollback

This change is docs plus an isolated model, with no runtime caller, data, migration or deployment.
To roll back, revert the implementation PR's merge commit, which restores the #950 contract.
`automation-api-store` stays blocked either way.
