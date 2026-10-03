# Design: issue-726-fix-agentapi-admin-profile-body-accepts

## Current state
- `internal/agentapi/profilehandler.go` `NewAdminAgentProfileHandler`:
  reads the body under `http.MaxBytesReader(..., maxRequestBodyBytes)`
  (`internal/agentapi/json.go`, 1 MiB), calls
  `agentprofile.RejectDuplicateJSONKeys(rawRequest)`, then decodes into
  `upsertAgentProfileRequest` with `DisallowUnknownFields` and a trailing
  `Decode(&struct{}{})` EOF check. `DisallowUnknownFields` does not flag
  `TELEGRAM_ID` because `encoding/json` matches it to `TelegramID`
  case-insensitively; the duplicate check does not flag
  `telegram_id` + `TELEGRAM_ID` because it compares exactly.
- `internal/agent/profile/profile.go`: `RejectDuplicateJSONKeys` maps
  `jsonstrict` sentinels to profile-specific wording. `ParseJSON` runs it, then
  decodes into `Data` with `UseNumber` + `DisallowUnknownFields`. `Data` and
  `RestrictedField` are structs, so their member names are case-folded the same
  way (`Restricted`, `NEVER_AUTO_SEND`, ...). `ParseJSON` is called by the admin
  handler and by `TenantProvider.load` for stored encrypted documents.
- `internal/jsonstrict/jsonstrict.go`: `RejectDuplicateKeys` is documented as
  exact-compare, explicitly telling callers that need an exact key set to check
  spelling separately.
- `internal/bot/bridge.go` `decodeObservation` (the #725 fix): after
  `jsonstrict.RejectDuplicateKeys`, unmarshals into `map[string]json.RawMessage`
  and requires `exactObservationKeys` (all three lowercase keys, nothing else),
  then decodes into the struct.
- Tests: `internal/agentapi/profilehandler_test.go` has
  `TestAdminAgentProfileHandler_RejectsDuplicateEnvelopeKeys` and
  `..._RejectsUnknownFields` using `doProfileReq`/`adminIdentity`/
  `newProfileTestStore`; `internal/agent/profile/profile_test.go` covers
  `ParseJSON` rejections.

## Proposed solution
1. Add a small helper to `internal/jsonstrict`:
   ```go
   // ErrUnknownKey is an object member name not in the allowed set, compared exactly.
   var ErrUnknownKey = errors.New("unknown JSON key")

   // ObjectKeysWithin requires raw to be a JSON object whose member names are
   // all spelled exactly as one of allowed. It does not check duplicates; run
   // RejectDuplicateKeys first.
   func ObjectKeysWithin(raw []byte, allowed ...string) error
   ```
   Implementation: `json.Unmarshal(raw, &map[string]json.RawMessage{})` (a map
   preserves exact key spelling), error if not an object, then every key must be
   in the allowed set; returns `fmt.Errorf("%w %q", ErrUnknownKey, k)`.
   This is the "subset" counterpart of the bridge's exact-set check; the
   profile body is a partial update, so keys are optional, but every present key
   must be exact. (Optionally the bridge's `exactObservationKeys` may keep its
   own exact-set check unchanged; it is not refactored here.)
2. Envelope: in `NewAdminAgentProfileHandler`, immediately after
   `RejectDuplicateJSONKeys`, call
   `jsonstrict.ObjectKeysWithin(rawRequest, upsertAgentProfileKeys[:]...)` and on
   error return 400 `invalid request body`. `upsertAgentProfileKeys` is a
   package-level array listing the twelve JSON names of
   `upsertAgentProfileRequest`. The existing struct decode with
   `DisallowUnknownFields` stays as defence in depth.
3. Owner-profile document: in `agentprofile.ParseJSON`, after
   `RejectDuplicateJSONKeys(trimmed)`, check the top level with
   `jsonstrict.ObjectKeysWithin(trimmed, dataKeys...)`; if a `restricted` member
   is present and is an object, unmarshal it to
   `map[string]json.RawMessage` and run
   `ObjectKeysWithin(entry, restrictedFieldKeys...)` on each entry value.
   Errors surface as the handler's existing `invalid owner_profile` 400.
   Free-form maps (`identity`, `public_profile`, `preferences`) are not checked:
   they are `map[string]any`, which `encoding/json` never case-folds.
4. Drift guard: a unit test reflects over the `json` tags of
   `upsertAgentProfileRequest`, `profile.Data` and `profile.RestrictedField` and
   asserts each key list equals the tag set, so adding a field without updating
   the list fails CI rather than rejecting valid requests in production.

Why this way: it mirrors the reviewed #725 approach (raw-bytes passes before the
struct decode), keeps the generic duplicate walker unchanged, and centralises
the exact-spelling rule in `jsonstrict`, whose package doc already names the
admin agent-profile envelope as a client.

## Alternatives
- Make `jsonstrict.RejectDuplicateKeys` compare case-folded names. Rejects
  `field`+`FIELD`, but not a lone `FIELD` alias, and would wrongly reject
  legitimate case-distinct keys inside free-form maps (`identity`,
  `preferences`). Dropped.
- Decode into `map[string]json.RawMessage` and hand-decode each field instead of
  using the struct. Exact by construction but duplicates the type handling for
  twelve fields (pointer-vs-omitted semantics) and is a larger, riskier diff.
  Dropped.
- Reflection-driven key set at runtime instead of a literal list. Avoids drift
  but hides the contract and re-implements tag parsing in a hot path; a
  reflection-based test gets the same drift protection. Dropped.

## Platform impact
- Migrations: none.
- Backward compatibility: only requests using non-canonical key spellings
  change behaviour (now 400). Documented clients (and the admin tooling) send
  snake_case lowercase keys. Stored owner-profile documents are written via
  `json.Marshal(profile.Data)` and therefore canonical, so `TenantProvider.load`
  is unaffected.
- Resources: one extra `json.Unmarshal` into a map per admin request and per
  profile load, bounded by the 1 MiB body limit. Negligible.
- Risks: (a) a future field added to the struct but not the key list would be
  rejected -- mitigated by the reflection drift test; (b) an unexpectedly
  non-canonical stored document would fail to load -- mitigated by the canonical
  write path, and by rollback being a plain revert.
