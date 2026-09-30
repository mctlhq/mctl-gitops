# Small follow-ups from issue #23

## Context and agreed scope

Issue #23 and its comments collect review leftovers. Implement this small cleanup after
HTTP-auth issue #28 merges, using the latest main as the implementation baseline. The
investigator confirmed the original five defects against MCP 2.2.0 and main `5541178`
(495 passing tests); that count is historical, not a required count after #28.

Included:

1. Correct the server module docstring from three to four tools.
2. Make exhausted `propose_action.raw_text` represent the final attempt's string or `None`.
3. Advertise PNG/JPEG MIME types in the MCP schema using a shared `ImageMimeType` alias.
4. Reject zero-byte inline images before any backend request.
5. Expose deliberate gateway input errors via SDK `ToolError`, keeping other failures opaque.
6. Declare the directly imported `mcp-types` dependency and regenerate `uv.lock`.
7. Reject malformed IPv6 URL shapes at config validation and pin canonical brackets.
8. Correct any remaining authenticated-approver docs reference to issue #7 to out of scope.
9. Remove unused `TERMINAL_STATES` / `_default_client_factory` only after checking callers.
10. Load demo runtime config once for both allowed goals and catalog.

Deferred, still tracked in issue #23: concurrent per-server discovery (changes cancellation,
ordering, and atomic publication behavior), and adding matched-rule metadata to
`PolicyResult` (a separate model/demo change). Do not close issue #23 while deferred items
remain. No real Newton credentials are needed; live integration remains unvalidated.

## Acceptance criteria

- The module docstring accurately describes the four registered tools. Existing tool-list
  tests suffice; do not introduce a sentence-parsing test for this typo correction.
- When the final exhausted proposal attempt yields no string (empty output/non-string),
  return `raw_text=None` even if the prior attempt yielded text. When the last attempt has
  text, return that text. Preserve success and terminal backend-failure semantics, attempt
  error history, and the result envelope key set.
- `newton_analyze_image.mime_type` is a nullable PNG/JPEG enum, with no additional MIME type.
  Share the alias with `ImageUpload` and assert its values equal `IMAGE_MIME_EXTENSIONS`
  keys. Null remains permitted in the schema but rejected when an inline image is supplied.
- Empty base64 and an empty data-URI payload fail after decode and before backend access.
  Preserve encoded and decoded size limits and invalid-base64 no-payload-echo behavior.
- Only explicitly marked, deliberate input rejections become client-visible `ToolError`.
  Introduce a small SDK-free `InputValidationError(ValueError)` for those sites and catch
  only that type at the MCP boundary (or an equally explicit narrow boundary). Proposal
  preflight errors remain compatible with library callers catching `ValueError`; action
  code must not import MCP. Do not catch arbitrary `ValueError` or `ValidationError` from
  backend, request construction, response parsing, or internal bugs.
- Gateway-authored input messages contain field names, accepted values, and size limits,
  without rejected image/events/file-id payloads. Ordinary SDK argument validation stays
  unchanged; no broad claim is made about redacting every SDK argument error.
- Real in-process client tests prove `is_error=True` and an actionable reason for image,
  timeseries, and proposal preflight rejection, with zero backend calls. Backend exceptions
  (including `ValueError`, nested validation errors, and `RuntimeError` containing a
  sentinel) retain a generic client message without the sentinel. Preserve cancellation,
  success structured content, argument defaults, ctx exclusion, and tool annotations.
- `mcp-types` is a direct dependency compatible with the existing MCP pin; lock resolution
  remains reproducible. No unrelated dependency upgrades.
- Malformed bracketed HTTP URLs fail at config load/model validation, rather than during
  fingerprint access. Diagnostics name the server/field when safe, never credential-bearing
  URL input. Preserve userinfo-sensitive hashing and exact IPv6 brackets. Test the exact
  canonical string for `http://[::1]:8080/mcp`.
- Cleanup does not remove a symbol that gained callers in #28. The demo loads one config
  snapshot per run, including contract-override runs, and uses it consistently.
- Full tests and mock demo smoke pass against the post-#28 baseline. Key regression tests
  pass normally and fail under deliberate reversible mutations.

## Out of scope

New tools, changed envelope keys, OAuth, image decoding/magic-byte validation, physical
actuation, live Newton validation, concurrent discovery, matched-rule policy metadata, and
changes to the HTTP-auth design approved for #28. Do not hard-code the historical test count.
