# Reject case-folded aliases and duplicate keys in the admin agent-profile body

## Context
`PUT /api/admin/agent/profile` (`NewAdminAgentProfileHandler` in
`internal/agentapi/profilehandler.go`) is meant to accept a strict JSON body: it
runs `agentprofile.RejectDuplicateJSONKeys` (a wrapper over
`jsonstrict.RejectDuplicateKeys`) on the raw bytes and then decodes with
`DisallowUnknownFields`. But `jsonstrict.RejectDuplicateKeys` compares member
names exactly, while `encoding/json` matches struct fields case-insensitively.
So `{"telegram_id":777,"TELEGRAM_ID":888}` passes the duplicate check as two
distinct names and decodes as 888 (last one wins), and a lone alias such as
`{"Telegram_Id":777}` or `{"telegram_id":777,"MODE":"guarded"}` is silently
accepted. The same weakness exists one level down: the `owner_profile` document
is parsed by `agentprofile.ParseJSON` into the struct types `profile.Data` and
`profile.RestrictedField`, so `{"never_auto_send":true,"NEVER_AUTO_SEND":false}`
inside a restricted entry decodes as `false` and the safety marker is dropped.

#725 closed the identical gap for the bot-start bridge (`internal/bot/bridge.go`,
`decodeObservation` + `exactObservationKeys`) by requiring the exact lowercase
key set after the duplicate check. This proposal applies the same exact-spelling
key validation to the admin profile envelope and to the struct-typed objects of
the owner-profile document, so the strict-body contract actually holds.

## User stories
- AS a platform operator I WANT the admin profile endpoint to reject any key that
  is not spelled exactly as documented SO THAT a request can never mean something
  other than what a human reviewer reads in it.
- AS a security reviewer I WANT the restricted-field safety markers
  (`approval_required`, `never_auto_send`) to be impossible to override with a
  case-variant key SO THAT an owner-profile document cannot silently lose its
  enforcement.
- AS a maintainer I WANT one shared helper for "member names must be exactly
  from this set" SO THAT the bridge and profile paths cannot drift apart again.

## Acceptance criteria (EARS)
- WHEN the request envelope contains a top-level key that is not exactly one of
  `telegram_id`, `mode`, `autopilot_paused`, `listener_enabled`,
  `disclosure_text`, `max_autonomous_turns`, `max_msgs_per_minute`,
  `max_reply_chars`, `intent_allowlist`, `blocked_senders`, `sender_allowlist`,
  `owner_profile` THE SYSTEM SHALL respond 400 `invalid request body` and write
  nothing.
- WHEN the envelope contains a mixed-case alias of a known key (e.g.
  `Telegram_Id`, `MODE`, `Listener_Enabled`) on its own THE SYSTEM SHALL respond
  400 `invalid request body`.
- WHEN the envelope contains a lowercase key together with an upper- or
  mixed-case variant of it (e.g. `{"telegram_id":777,"TELEGRAM_ID":888}`) THE
  SYSTEM SHALL respond 400 `invalid request body` and SHALL NOT resolve or
  modify either account.
- WHEN `owner_profile` is an object whose top-level keys are not exactly from
  `identity`, `public_profile`, `skills`, `preferences`, `restricted` THE SYSTEM
  SHALL respond 400 `invalid owner_profile`.
- WHEN any entry under `owner_profile.restricted` has a key that is not exactly
  `value`, `approval_required` or `never_auto_send` (including a case variant
  alongside the lowercase key) THE SYSTEM SHALL respond 400
  `invalid owner_profile`.
- WHILE a request body uses only exactly-spelled keys THE SYSTEM SHALL behave
  exactly as today (partial update semantics, `owner_profile: null` clears,
  omitted keys untouched).
- IF the envelope check fails THEN THE SYSTEM SHALL return the same generic
  `invalid request body` message as the existing duplicate/unknown-field
  rejections (no echo of the offending key).
- WHILE keys inside free-form maps (`identity`, `public_profile`, `preferences`,
  and the names of `restricted` entries) are only checked for exact duplicates
  THE SYSTEM SHALL continue to accept arbitrary case there, because those are
  `map[string]any` and `encoding/json` does not case-fold map keys.

## Out of scope
- Changing the response shape, status codes for other failure classes, or the
  `maxRequestBodyBytes` limit.
- Other JSON endpoints in `internal/agentapi` that use plain decoding (they are
  not part of the strict-body contract named in the issue); they can be audited
  in a follow-up.
- The legacy YAML path (`ParseYAML`): yaml.v3 matches keys case-sensitively, so
  it does not have this defect.
- Any data migration.

## Open questions
- The issue names only the "profile body". This proposal also hardens the nested
  `owner_profile` document (`profile.Data` / `profile.RestrictedField`) because
  it is part of the same body and the case-folding there can drop a
  `never_auto_send` marker. `ParseJSON` is also used by `TenantProvider.load`
  on stored documents; those are always the `json.Marshal` output of
  `profile.Data` (canonical lowercase keys), so tightening is expected to be
  safe, but the reviewer should confirm no stored row was written by another
  path. If the reviewer prefers, task 3 can be dropped and the change limited to
  the envelope.
