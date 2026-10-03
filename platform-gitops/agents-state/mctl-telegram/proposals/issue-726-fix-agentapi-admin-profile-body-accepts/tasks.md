# Tasks: issue-726-fix-agentapi-admin-profile-body-accepts

- [ ] 1. Add `ErrUnknownKey` and `ObjectKeysWithin(raw []byte, allowed ...string) error` to `internal/jsonstrict/jsonstrict.go`, with a doc comment explaining it is the exact-spelling complement of `RejectDuplicateKeys` — DoD: non-object input returns an error; every key outside `allowed` (compared exactly) returns an error wrapping `ErrUnknownKey`; `go vet` clean.
- [ ] 2. (depends on 1) In `internal/agentapi/profilehandler.go`, add `upsertAgentProfileKeys` (the 12 JSON names of `upsertAgentProfileRequest`) and call `jsonstrict.ObjectKeysWithin` right after `agentprofile.RejectDuplicateJSONKeys`, returning 400 `invalid request body` on error; extend the handler comment to explain the case-folding reason — DoD: mixed-case aliases and lowercase+uppercase pairs at the envelope level are rejected before any store call.
- [ ] 3. (depends on 1) In `internal/agent/profile/profile.go` `ParseJSON`, after `RejectDuplicateJSONKeys`, check top-level keys against `identity, public_profile, skills, preferences, restricted` and each `restricted` entry against `value, approval_required, never_auto_send` — DoD: case-variant keys in `Data`/`RestrictedField` objects are rejected; keys inside `identity`/`public_profile`/`preferences` and restricted entry names are still free-form.
- [ ] 4. (depends on 2, 3) Run `go fmt`, `go vet`, `golangci-lint`, `go test ./...` — DoD: all green.

## Tests
- [ ] T1. `internal/jsonstrict/jsonstrict_test.go`: table test for `ObjectKeysWithin` — accepts subset/empty object, rejects `FIELD` alias, rejects `field`+`FIELD`, rejects non-object (`[]`, `1`, `null`), error `errors.Is(err, ErrUnknownKey)` for unknown keys.
- [ ] T2. `internal/agentapi/profilehandler_test.go` `TestAdminAgentProfileHandler_RejectsCaseFoldedEnvelopeKeys`: table over `{"Telegram_Id":777}`, `{"telegram_id":777,"MODE":"guarded"}`, `{"telegram_id":777,"Listener_Enabled":true}`, `{"telegram_id":777,"TELEGRAM_ID":888}`, `{"telegram_id":777,"mode":"observe","Mode":"guarded"}`, `{"telegram_id":777,"OWNER_PROFILE":{}}` — each 400 `invalid request body`; seeds users 777 and 888 and asserts neither has an agent profile afterwards (no write happened).
- [ ] T3. `internal/agentapi/profilehandler_test.go` `TestAdminAgentProfileHandler_RejectsCaseFoldedOwnerProfileKeys`: `owner_profile` with `"Restricted":{...}`, and with a restricted entry `{"value":"1","never_auto_send":true,"NEVER_AUTO_SEND":false}` — each 400 `invalid owner_profile`.
- [ ] T4. `internal/agent/profile/profile_test.go`: `ParseJSON` rejects `{"IDENTITY":{}}`, `{"restricted":{"salary":{"value":"1","Approval_Required":true}}}`; still accepts `{"identity":{"Name":"Alice","name":"Alice"}}` and a restricted entry named `Salary` (free-form map keys).
- [ ] T5. Drift guard test: reflect over `json` tags of `upsertAgentProfileRequest`, `profile.Data`, `profile.RestrictedField` and assert equality with the literal key lists.
- [ ] T6. Existing tests (`..._PartialUpdatePreservesOtherFields`, `..._StoresEncryptedTenantDocumentAndClears`, `..._RejectsDuplicateEnvelopeKeys`, `..._RejectsUnknownFields`, bridge tests) still pass unchanged.

## Rollback
Revert the PR (merge commit) and cut a patch release through the normal
release-please flow. No schema or data changes are involved, so a revert fully
restores the previous behaviour.
