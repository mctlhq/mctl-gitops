# Design: issue-1158-fix-contract-reconcile-automation-v1-wit

## Current state

The contract package is `internal/automation/contract`. It is pure validation and decision code,
and nothing outside the package imports it: `grep -rln internal/automation/contract --include=*.go`
returns only package files.

- `occurrence.go`:
  - `OccurrenceKey(auID, definitionVersion int, triggerKind, instantOrDelivery)` hashes
    `strings.Join([...], "|")` with no length prefix or domain tag, and includes the definition
    version.
  - `OccurrenceKeyAt` formats the instant as UTC `RFC3339Nano`.
  - `ExternalKey` returns `automation:<au>:<occ>`, and `FireIdempotencyKey` returns
    `automation-fire:<occ>`.
  - `OccurrenceSet.Claim` is an unsynchronised map that returns `CodeOccurrenceDuplicate` on a
    second claim.
- `schema.go`:
  - `Code` vocabulary and `httpStatus`. `CodeOccurrenceDuplicate` is 409.
  - `ErrorBody(c)` uses a fixed message, so a 404 body is byte-identical.
  - The `serverOwned` prepass, plus `ValidateCreate`, `ValidatePatch`, `ValidateDefinition` and
    `ValidateRun`.
  - The schemas are embedded from `schema/v1/*.schema.json`.
- `authority.go`: `Decide(cp, Inputs)` refuses in this order: unavailable (503), identity (403),
  not found (404), policy drift, budget (`HeadroomPerRun/Day/Tenant`), approval. Nothing names
  which system is the budget authority.
- `support.go`:
  - `CheckSupport`: `SupportMaxTTL = 24h`, `SupportMaxFires = 3`, and `auth_ref` is accepted only
    with `AuthRefLive`.
  - `supportInputsFromBody` and `ttlFromSeconds`.
  - Nothing models the fire-time token or consent.
- `templates.go`: one `templates` map holds both `reminder.v1` and `support.diagnostic-followup.v1`.
  Enablement is decided by `mvpTriggers` in `trigger.go` (`reminder.v1` with `at` only).
- `trigger.go`:
  - `offsetOnlyZone = ^(UTC|GMT)?[+-]?[0-9]`, which does not match `Etc/GMT+2`.
  - `instant` is checked with `time.Parse(time.RFC3339, ...)`.
- `contract_test.go` contains `TestFixtures` (manifest-driven, kinds `create|patch|definition|run`),
  `TestOccurrenceKeys` (asserts duplicate on the second claim), `TestDecide`,
  `TestNotFoundBodiesIdentical`, `TestCheckSupport`, `TestSupportTTLOverflowIsRefused` and
  `TestParallelValidation`. Fixtures live in `testdata/{valid,invalid}` and `testdata/manifest.json`.
- `schema/v1/automation-run.schema.json` requires `definition_version`.
- `docs/automation-contract.md`:
  - section 2 gives the old key formula and marks durable dedupe `assumed`;
  - section 3's `run` row has no request schema;
  - section 7 points the budget at `internal/commerce/budget.go`;
  - section 8 sets the 24h Support TTL;
  - section 12 lists `automation-api-store`, which "decides durable occurrence dedupe".

Related code (read only, not changed):
- `internal/workitems/store.go`: the unique index `work_items_tenant_external_key_open` applies
  only `WHERE ... state IN ('active','waiting')`, and child tables use
  `REFERENCES work_items (id) ON DELETE CASCADE`. `execution_requests.go` and `snapshots.go` do
  the same.
- `internal/commerce/budget.go`: `Budget` is per `PayerAccountID`, with `MonthlyLimitMinor`,
  `PerRequestMaxMinor` and `rsv_` reservations with `DefaultReservationWindow = 15m`. This is
  payment, not inference metering.
- `internal/auth/agent_scope.go:344-347`: `AgentScopeSupport` has `BoundTenant: true`,
  `MintByTenantMember: true`, `DefaultTTL: 10 * time.Minute` and `MaxTTL: time.Hour`.

Toolchain reproduction. I ran a scratch program in `/tmp` with Go 1.26.11 (the same version as
`go.mod`):
- `time.Parse(time.RFC3339, ...)` accepts `...00.5Z` and `.123456789+02:00`. It also accepts
  `.1234567891Z` (truncated to ns) and `,5Z` (comma separator).
- The Agy `FAIL:P2` about fractional seconds is not reproduced. Go 1.22+ per-iteration loop
  variables make the closures in `TestParallelValidation` correct.
- `offsetOnlyZone.MatchString("Etc/GMT+2")` is `false`, and `time.LoadLocation` loads it. The same
  holds for `Etc/GMT-14` and `Etc/GMT0`. This P3 is genuine.

Deployed state checked:
- `mctl_list_services(team=admins)` succeeded (complete=true). It lists mctl-agents-worker*,
  mctl-design, mctl-docs, mctl-support (0.4.1), mctl-web and umami. mctl-api is not a catalogue
  service of `admins`, so I did not observe its deployed config. That does not matter here: the
  contract package has no runtime caller, route, flag or config.
- `$MCTL_GITOPS_ROOT/services/` has `admins`, `karabu`, `labs`, `namax66` and `redloop`, and none
  of them holds an `mctl-api/values.yaml`. Absence there does not mean absence elsewhere; not
  relevant to a contract-only change.
- I read `agents-state/mctl-api/proposals/issue-955-*` (status `proposed`, superseded) for
  continuity. This design follows the same shape.
- mctl-gitops#2452 was not readable from this run (see Open questions).

## Proposed solution

Everything stays inside `internal/automation/contract` and the one doc. Every new type is
documented `isolated-model` with no production caller.

1. **Occurrence identity (`occurrence.go`).**
   - Add `type OccurrenceSource struct{ kind string; parts []string }` with the constructors
     `ScheduledSource(t time.Time)`, `EventSource(producer, eventType, stableID string)` and
     `ManualSource(principal, tenant, callerKey string)`. Each returns `automation_invalid` on an
     empty part.
   - `OccurrenceKey(auID, triggerKind string, src OccurrenceSource) (string, error)` hashes
     `"mctl.automation.occurrence.v1"` followed by each field encoded as `uint32be(len) || bytes`:
     au_id, trigger_kind, source kind, then the parts. The output is still
     `occ_ + hex[:32]`, so `automation-run.schema.json` and `ExternalKey`/`FireIdempotencyKey`
     stay unchanged.
   - Remove the `definitionVersion` parameter. Package-internal callers are only tests.
2. **Error vocabulary (`schema.go` and `automation-error.schema.json`).**
   - Add `CodeOccurrenceConflict = "automation_occurrence_conflict"` (409).
   - Keep `CodeOccurrenceDuplicate`, documented as "reserved; not emitted for identical replay".
3. **Claim model (new `claim.go`).**
   - `ClaimStore` is a mutex-guarded map keyed by `(tenant, au_id, occurrence_key)`. Each
     `Claim{WorkItemID, AdmittedVersion, Status, RequestHash, ClosedAt}`.
   - `Claim(ctx-free ClaimRequest, mint func() (string, error)) (ClaimResult{Replayed bool, ...},
     error)` mints exactly once under the lock.
   - An identical hash replays. A different tenant, `au_` or hash for the same key returns
     `CodeOccurrenceConflict`.
   - An injected `Unavailable` flag returns `CodeAuthorityUnavailable` and does not mint.
   - `Close(key, at)` and `Cleanup(now, horizon)` implement the tombstone transition: the
     WorkItem reference may be dropped, but the key and status `tombstoned` remain until
     `now > closedAt + horizon`.
   - `Reconcile(key, lookup func(externalKey) (wi string, found bool, err error))` binds to the
     found `wi_`, or marks `failed` when none is found, or returns unavailable on error. It never
     mints.
   - Delete `OccurrenceSet`.
4. **Usage authority (`authority.go`).**
   - Add `UsageAuthority` with values `UsageAuthorityUnknown` (zero), `UsageAuthorityCommercePayment`
     and `UsageAuthorityVerifiedMetering`.
   - Add `Inputs.UsageAuthority`. Before the budget comparison, `Decide` returns
     `CodeAuthorityUnavailable` unless the value is `VerifiedMetering`.
   - The ordering otherwise stays as it is. The 403-before-404 order already exists and gets an
     exhaustive test.
5. **Templates and Support (`templates.go`, `trigger.go`, `support.go`).**
   - Rename the map to `registry` and add `enabledTemplates = map[string][]string{"reminder.v1":
     {"at"}}` (moved from `mvpTriggers`) plus `TemplateEnabled(id, kind) bool`. `CheckTrigger`
     uses it.
   - Add `SupportTokenMaxTTL = time.Hour`, with a comment citing
     `internal/auth/agent_scope.go` `AgentScopeSupport.MaxTTL`.
   - Add `SupportFireInputs{ConsentLive, ConsentIndependentlyVerified, TokenMintedForFire,
     TokenMintedBy (owner-path|self), TokenTTL, TokenExpiresAt, Now, AuthRef, AuthRefLive}` and
     `CheckSupportFire`, which returns `automation_support_constraint` on any failure. It does not
     enable the template.
6. **Manual run (new schema `automation-manual-run-request.schema.json` and `manual.go`).**
   - The schema is `{schema_version?, idempotency_key (1..128), note? (<=256)}` with
     `additionalProperties: false`.
   - `ValidateManualRunRequest(raw)` runs `parseObject`, then a server-owned prepass that adds
     `occurrence_key`, `principal` and `au_id` to the existing list, then the schema.
   - `ManualRequests` is an isolated model keyed `(principal, tenant, au_id, key)` with a body
     hash. It returns the replay or `CodeIdempotencyKeyReused` and derives the occurrence through
     `ManualSource`.
   - `ManualRunEnabled = false`, so execution returns `CodeTriggerUnsupported`.
   - Add manifest kind `manual-run` to `TestFixtures`.
7. **Zone P3 (`trigger.go`).** Add `etcOffsetZone = ^(Etc/)?GMT[+-]?[0-9]+$`, which refuses any
   GMT-family zone with a numeric suffix (`Etc/GMT+2`, `Etc/GMT-14`, `Etc/GMT0`, `GMT0`, `GMT+0`).
   Zones without a suffix (`UTC`, `Etc/UTC`, `GMT`, `Etc/GMT`) and named IANA zones stay
   accepted. The table-driven test pins this exact boundary.
8. **Doc rewrite (`docs/automation-contract.md`).** Update sections 1, 2 (new 2.1 on the durable
   claim), 3, 5, 7, 8, 9, 11 and 12 as listed in tasks.md. Each statement carries a claim class.
   Add an explicit "contract-only; nothing here is enforced" paragraph with the forbidden-artifact
   list. Section 12 marks `automation-api-store` as hard-gated on section 2.1, and states that
   this issue does not approve it.
9. **PR description.** Include a section-by-section comparison of #950 and #2452, a note that
   #2452 was not part of the #948 approval, and the toolchain reproduction.

## Alternatives

- **Keep the definition version in the key, and add a second "stable" key.** Rejected: two keys
  invite drift, and the amendment requires the dedupe key to be version-free.
- **Repurpose `automation_occurrence_duplicate` to mean conflict.** Rejected: the contract says
  meanings never change, so a new code is cheaper than a carve-out.
- **Add a real `automation_occurrence_claims` table now.** Rejected: the issue explicitly forbids
  migrations, and this slice must only specify the store slice's gate.
- **Model the budget authority as Commerce with new budget classes.** Rejected: it would claim an
  unverified implementation. `unknown` plus fail-closed is the honest contract.

## Platform impact

- No migration, route, MCP tool (the tool count in `server_test.go` is unchanged), flag, Helm,
  GitOps or runtime change. The package has no importer, so there is zero runtime effect.
- Backward compatibility: `OccurrenceKey`'s signature changes, but only tests in the package call
  it. The derived keys change value, but nothing has persisted them. The error vocabulary only
  gains a code. Zone validation becomes stricter for `Etc/GMT*`, which was never served.
- Risk: the doc overstates enforcement. Mitigation: a claim class on every statement, and an
  explicit contract-only section.
- Risk: the tombstone horizon is chosen wrongly. Mitigation: the value is a named constant and an
  open question for the owner, and the store slice must confirm it.
- Risk: the zone regexp is too strict or too loose. Mitigation: a table-driven test that pins the
  accepted set (`UTC`, `Etc/UTC`, `GMT`, `Etc/GMT`, named zones) and the refused set.
