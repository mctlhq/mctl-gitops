# Tasks: small follow-ups from issue #23

- [ ] 1. Wait for #28 to merge, then use its final main as baseline. Read repository rules,
  sync dev dependencies, and run the full suite. Do not require exactly 495 tests.
- [ ] 2. Correct the four-tool docstring; fix final-attempt `raw_text` and its documentation.
- [ ] 3. Share the PNG/JPEG MIME alias, expose it in the nullable tool schema, and reject
  zero-byte decoded inline images while preserving size and invalid-base64 checks.
- [ ] 4. Define an SDK-free marked `InputValidationError(ValueError)` for deliberate input
  failures. Change only own validation sites (including proposal preflight) to use it;
  translate only this type to SDK `ToolError` at the MCP boundary. Never translate generic
  backend/request/response `ValueError`/`ValidationError`. Keep MCP imports out of action.
- [ ] 5. Adapt direct tool tests and add real `Client(server)` tests for actionable marked
  errors, zero backend calls, generic backend failures, and unaffected success/schema.
- [ ] 6. Declare direct `mcp-types` and regenerate `uv.lock` without unrelated upgrades.
- [ ] 7. Add safe malformed-IPv6 URL validation at model/config load and exact canonical
  bracket tests. Preserve URL userinfo-sensitive fingerprinting and #28 secret containment.
- [ ] 8. Check callers before removing unused `TERMINAL_STATES` and the private factory
  alias. Correct the approver docs reference if still present. Load demo config once for
  ordinary and override paths, using the same snapshot for goals and catalog.
- [ ] 9. Update existing documentation for MIME schema and deliberate input error surfacing.
  Keep live integration claims unchanged. Leave concurrent discovery/policy metadata open.

## Verification

- [ ] V1. Final attempt empty/non-string after first text => None; final text after earlier
  empty => final text; success and terminal backend failure remain correct.
- [ ] V2. Schema advertises exactly PNG/JPEG plus null; null with inline input and invalid
  MIME fail before backend use. Alias/map values agree.
- [ ] V3. Empty base64 and empty data URI fail before backend use; existing encoded/decoded
  limits and payload-echo tests remain meaningful.
- [ ] V4. Real MCP client receives actionable image/timeseries/proposal preflight errors.
  Backend `ValueError`, `RuntimeError`, and internal `ValidationError` with a sentinel stay
  generic client errors, not anticipated input errors. Cover backend entry points and
  cancellation; preserve successful structured content and all tool schemas/annotations.
- [ ] V5. Malformed IPv6 URL fails at config/model load without reflecting credential input;
  `_canonical_url("http://[::1]:8080/mcp")` equals that exact string. Existing userinfo and
  default-port fingerprints remain correct.
- [ ] V6. Verify one demo config load in ordinary and override runs. Run the full suite and
  mock smoke (success, denial, offline escalation, deterministic trace reproduction).
- [ ] V7. Reversible mutations must turn relevant green detectors red: restore sticky
  `raw_text`, remove empty-image check, widen MIME schema, broaden input exception handling
  to all `ValueError`, drop IPv6 brackets, and restore the second demo config load. Restore
  from committed snapshots without wiping other edits.
- [ ] V8. CI and Claude review on the current head have no unaddressed P1/P2. Let the
  existing shepherd merge after independent review; report completed and deferred #23
  checklist items without closing the issue. Run post-merge smoke.

## Rollback

Revert the relevant cleanup via a feature branch and reviewed PR. No migrations or persisted
state changes. Preserve the earlier #28 feature and do not directly commit to main.
