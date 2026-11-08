# Design: issue-955-fix-contract-reconcile-automation-v1-wit

## Current state

Merged by mctl-api#950. The package is `isolated-model` only and has no production caller.

- `docs/automation-contract.md`, section 2, defines:
  - `occurrence_key = "occ_" + hex(sha256(au_id | definition_version | trigger_kind |
    occurrence_instant_utc_or_event_delivery_id))[:32]`;
  - "a second delivery ... is `automation_occurrence_duplicate`";
  - durable dedupe after close as `assumed`.
- Section 7 says budgets per run, per day and per tenant use "the commerce ledger
  (`internal/commerce/budget.go`)".
- Section 9 keys event replay by "producer delivery id".
- `internal/automation/contract/occurrence.go`:
  - `OccurrenceKey(auID, definitionVersion int, triggerKind, instantOrDelivery)` joins the fields
    with `|`. This is neither length-prefixed nor domain-separated, so `"a|b"` and `"a","b"`
    collide.
  - `OccurrenceSet.Claim` returns `CodeOccurrenceDuplicate` on a second claim, and stores no
    `wi_` or version.
- `internal/automation/contract/authority.go` `Decide`:
  - Refusal order: unavailable 503, then identity 403, then not found 404, then policy drift,
    then budget (`HeadroomPerRun/PerDay/PerTenant`), then approval.
  - The budget source is not modelled. An absent headroom value is the zero value, not "unknown".
- `internal/automation/contract/support.go` `CheckSupport`:
  - Checks owner authorization, tenant binding, scope, TTL <= 24h (`SupportMaxTTL`), fires <= 3,
    no delegate or impersonation, and `auth_ref` liveness.
  - Has no token-lifetime or per-fire consent/mint facts.
  - `supportInputsFromBody` hard-codes `OwnerAuthorized: true`.
- `internal/automation/contract/templates.go`: one `templates` map serves as both registry and
  allowlist. `trigger.go` `mvpTriggers` is the de facto enabled gate
  (`{"reminder.v1": {"at"}}`).
- `internal/automation/contract/trigger.go`:
  - `offsetOnlyZone = ^(UTC|GMT)?[+-]?[0-9]` does not match `Etc/GMT+5`.
  - `CheckTrigger` uses `time.Parse(time.RFC3339, instant)`.
- `internal/automation/contract/schema.go`:
  - The `Code` vocabulary and `httpStatus` map (`CodeOccurrenceDuplicate: 409`).
  - `ValidateCreate`, `ValidatePatch`, `ValidateDefinition`, `ValidateRun` and `ErrorBody`.
  - Schemas are embedded from `schema/v1/*.schema.json`, and fixtures are driven by
    `testdata/manifest.json` through `TestFixtures`.
  - `run-bad-key.json` exists but there is no manual-run request schema.
- `internal/automation/contract/contract_test.go`:
  - `TestOccurrenceKeys` asserts that the second claim returns duplicate.
  - `TestNotFoundBodiesIdentical` checks only `ErrorBody`, not 403-before-lookup or
    foreign-versus-absent equivalence through `Decide`.
- Proved sources the contract cites:
  - `internal/workitems/store.go`: `work_items_tenant_external_key_open` is unique only `WHERE
    state IN ('active','waiting')`. `work_item_create_requests` is keyed `(tenant,
    idempotency_key)` with `work_item_id ... ON DELETE CASCADE`. Neither survives closure plus
    cleanup as a dedupe record.
  - `internal/commerce/budget.go`: `Budget{MonthlyLimitMinor, PerRequestMaxMinor}`, which is
    payer/month and per-request payment.
  - `internal/auth/agent_scope.go`: `AgentScopeSupport` has `DefaultTTL: 10 * time.Minute`,
    `MaxTTL: time.Hour`, `BoundTenant` and `MintByTenantMember`.
- Toolchain reproduction (`go 1.26.10`, scratch module outside the repo):
  - `time.Parse(time.RFC3339, ...)` accepts `2026-12-01T10:00:00.123456789Z`,
    `...00.5+02:00` and `...00,5Z`, and rejects lowercase `t`/`z`.
  - A closure-capture loop prints `012` (per-iteration variables).
  - `time.LoadLocation` accepts `Etc/GMT+5`, `Etc/GMT-14` and `Etc/GMT0`, and none of them match
    `offsetOnlyZone`.
  - Conclusion: the P2 does not reproduce, and the P3 is genuine.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-948-feat-automation-define-canonical-automat/.status.yaml`
  shows `status: merged`, `pr: .../pull/950`, `merge_commit: fca64ee...`, approval
  `aar_cd3746f1...` with `content_digest sha256:4a64221b...`. This confirms that the original
  proposal was approved and merged.
- `$MCTL_GITOPS_ROOT/services/` (tenants `admins`, `karabu`, `labs`, `namax66`) is not relevant:
  this change has no deployment surface. No service config was consulted, and none is changed.
- The local clone is shallow (HEAD `722d839`). The #950 merge commit `fca64ee` is not present as
  an object, so the full #950 diff was not read. The merged files at HEAD were read instead.
- PR mctl-gitops#2452 was not observable: it is unmerged and not in the checkout. It is recorded
  under Open questions.
- No mctl MCP tool calls were needed or made. A contract-only change has no runtime state to
  observe.

## Proposed solution

All changes are in `docs/automation-contract.md` and `internal/automation/contract/**`. Every new
symbol is `isolated-model` with no production caller.

1. **Occurrence identity** (`occurrence.go`)
   - Replace the derivation with `OccurrenceKey(auID string, kind TriggerKind, source
     OccurrenceSource) string`. It hashes `"mctl.automation.occurrence.v1"` followed by
     length-prefixed fields: a uvarint or fixed 8-byte big-endian length, then the bytes.
   - `OccurrenceSource` is a closed sum, one constructor per trigger kind:
     - `ScheduledSource(t time.Time)`: UTC, RFC 3339 nanosecond precision.
     - `EventSource(producer, eventType, stableEventID string)`: also used for `dependency`.
     - `ManualSource(principal, tenant, requestKey string)`.
   - The constructors reject empty components with `automation_invalid`.
   - `definitionVersion` is removed from the key. `OccurrenceKeyAt` keeps its name but drops the
     version parameter.
   - A transport or delivery ID is never an input. The docs say this explicitly, and section 9's
     "producer delivery id" becomes "stable producer event id".
2. **Claim model** (new `claim.go`)
   - `ClaimStore`, an in-memory isolated model guarded by a `sync.Mutex`. It is unique on
     `ClaimKey{Tenant, AuID, OccurrenceKey}` and records `Claim{WorkItemID, AdmittedVersion,
     Status, RequestHash}`.
   - `Status` values: `claimed`, `admitted`, `terminal`, `tombstoned`, `failed`.
   - `Claim(key, requestHash, admittedVersion, mint func() (string, error)) (Claim, replayed
     bool, error)`:
     - First claim: calls `mint` exactly once.
     - Identical replay: returns the stored claim with `replayed=true` and does not call `mint`.
     - Hash mismatch: returns `automation_occurrence_conflict` (new code, 409).
     - Store marked unavailable: returns `automation_authority_unavailable`.
   - `Close(key)` sets `terminal`. `Cleanup(key, now)` sets `tombstoned`, which keeps the key
     until `horizon` has passed and still answers a replay with `replayed=true` and the old
     `wi_`.
   - `Reconcile(key, lookup func(externalKey) (wiID string, found bool, err error))` resolves a
     crash-left `claimed` row to the found `wi_` or to `failed`. It never mints.
   - Docs: a new section 2.1, "Durable occurrence claim (required by automation-api-store)", gives
     the relation, the uniqueness, transactional or fail-closed semantics, the tombstone horizon
     and the reconciliation. Section 12 makes it a hard gate.
   - `OccurrenceSet` is removed. Its single test caller is rewritten.
3. **Usage authority** (`authority.go` and docs section 7)
   - Add `UsageAuthority` to `Inputs`, with values `UsageAuthorityUnknown` (zero),
     `UsageAuthorityVerifiedMetering` and `UsageAuthorityCommercePayment`.
   - `Decide` denies `automation_authority_unavailable` unless the value is `VerifiedMetering`.
     Commerce payment is never accepted as usage authority. Headroom checks run only after that.
   - Docs: separate Commerce payer/payment limits (`proved-source`) from inference/FinOps usage
     metering with idempotent reservation, settlement and release (`unknown`, unresolved).
   - The crosswalk row "budget | mctl-api commerce" becomes "usage metering | unknown".
4. **Support** (`support.go`, `templates.go`)
   - Add these per-fire facts to `SupportInputs`: `OwnerConsentLive bool`,
     `OwnerConsentVerifiedIndependently bool`, `TokenMintedForThisFire bool`, `TokenExpiresAt` and
     `FireAt time.Time`, `TokenMintedBy` (`tenant-owner-path` | `self` | `""`).
   - Add `CheckSupportFire(in)`. It refuses with `automation_support_constraint` in any of these
     cases:
     - consent is not live or not independently verified;
     - the token was not freshly minted for this fire, or `TokenExpiresAt <= FireAt`;
     - the token lifetime exceeds `SupportTokenMaxTTL = time.Hour` (mirroring
       `AgentScopeSupport.MaxTTL`, with a comment citing it; no import of `internal/auth` is
       needed);
     - the minter is `self`;
     - an `auth_ref` is present without live authorization.
   - `CheckSupport` (definition-time) is unchanged except for the docs.
   - Split `templates.go`:
     - `registry` holds every schema-defined template, and is what `LookupTemplate` reads.
     - `enabledTemplates` holds `{"reminder.v1"}`, read by `TemplateEnabled(id)`.
     - `mvpTriggers` in `trigger.go` keeps the kind gate.
   - Support stays registered but not enabled. Its existing fixture `support-followup-gated.json`
     keeps returning `automation_trigger_unsupported`.
5. **Manual run request**
   - New `schema/v1/automation-manual-run-request.schema.json` with `schema_version: "automation-manual-run-request.v1"`, `idempotency_key` (opaque, 1..256 chars) and optional `expected_version`. `additionalProperties: false`.
   - Server-owned prepass additions: `occurrence_key`, `principal` and `au_id`.
   - `ValidateManualRunRequest(raw)` validates the body.
   - `ManualRequests`, an isolated model, is scoped by `(principal, tenant, au_id, key)`. It
     derives `ManualSource(principal, tenant, key)` and stores the body hash. It returns:
     - `replayed` for an identical replay;
     - `automation_idempotency_key_reused` for a different body;
     - a distinct occurrence for a different principal, tenant or `au_`.
   - Execution: `ManualRunEnabled` stays `false`, and admission returns
     `automation_trigger_unsupported`.
   - `run-bad-key.json` moves to `kind: "manual-run"` in the manifest. New fixtures are added
     (valid, unknown field, spoofed `occurrence_key`).
   - The docs table row for `run` references the new schema.
6. **Authorization**
   - Add `CreateIdempotencyScope{Principal, Tenant, Key}` to `Decide`'s docs and model it in the
     manual and create replay tests.
   - Keep `Decide`'s order, and document it as "403 before any lookup". Tests assert that varying
     `TargetExists`, `OwnerMatches` and `TenantAccessible` under an unlinked caller always yields
     403, and that absent, foreign-owner and foreign-tenant all yield an identical `ErrorBody` and
     404.
7. **Error vocabulary** (`schema.go`, `automation-error.schema.json`)
   - Add `automation_occurrence_conflict` (409). Keep `automation_occurrence_duplicate`
     (append-only rule), documented as "not returned for identical replay".
   - `TestErrorVocabularyMatchesSchema` keeps the enum and map in sync.
8. **Zones** (`trigger.go`)
   - Extend the offset-only rejection to `^(Etc/)?(GMT|UTC)?[+-]?[0-9]` and the exact aliases
     `Etc/GMT0`, `Etc/GMT+0`, `Etc/GMT-0`, `GMT0`, `GMT+0`, `GMT-0`.
   - `UTC` and `Etc/UTC` stay allowed.
   - Add the fixture `invalid/offset-zone-etc.json`.
9. **Docs claim header**: a sentence in section 1 says that every authorization, claim, usage and
   consent model is contract-only, not live enforcement, and lists the forbidden artifacts (route,
   MCP tool, table, migration, Schedule, worker, flag, release, Support enablement, downstream
   issue). Section 12 says that this issue does not approve `automation-api-store`.

## Alternatives

- **Keep the definition version in the key and dedupe on `(au_id, instant)` in the store
  instead.** Dropped because it spreads the identity rule across two places, and a replay across
  an update still mints a new `external_key`.
- **Add the durable claim table now (migration in `internal/workitems`).** Dropped because the
  issue forbids storage in this slice. The isolated model plus the hard gate gives the store slice
  a tested target without a production write path.
- **Model Commerce `budgets` as the usage authority with new periods.** Dropped because
  `internal/commerce/budget.go` is payer/payment-scoped. Assuming it would silently create
  authority the owner has not approved. "Unknown denies" is the fail-closed choice.
- **Reuse `automation_idempotency_key_reused` for occurrence conflicts.** Viable, but it conflates
  a client-chosen key with a server-derived occurrence. It is kept as an open question, defaulting
  to a new code.

## Platform impact

- No migrations, routes, MCP tools, flags or Helm changes. The MCP tool count in `server_test.go`
  is unaffected. No production code imports `internal/automation/contract` (verify with
  `grep -rn automation/contract --include=*.go`).
- These are API-breaking changes inside an unused package: `OccurrenceKey`/`OccurrenceKeyAt`
  signatures change and `OccurrenceSet` is removed. There are no external callers.
- Risk: the docs drift from #2452 again. Mitigation: the implementation PR description includes a
  section-by-section diff against #2452, and the PR needs a fresh independent review.
- Risk: a race in the claim model. Mitigation: a mutex, plus a parallel claim test under `-race`
  that asserts `mint` runs exactly once.
- Resource impact: none at runtime.
