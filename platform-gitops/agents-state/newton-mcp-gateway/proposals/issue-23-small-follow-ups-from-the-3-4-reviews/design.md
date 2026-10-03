# Design: small follow-ups from issue #23

## Existing behavior and SDK evidence

The original investigation examined main `5541178` and locked MCP 2.2.0. Server tools use
`mcp.server.mcpserver.MCPServer`; `Tool.run` intentionally wraps ordinary exceptions in
`UnexpectedToolError` with a generic client message. Explicit `ToolError` exposes its
message in `CallToolResult(is_error=True)`. `Client(server)` runs the real lifespan and is
the appropriate client-level test seam. The original broad `ValueError` decorator prototype
is not the approved design: backend errors can also be `ValueError` and contain secrets.

`action/propose.py` currently updates the last raw text only when non-None; this retains an
earlier attempt's output. `server.py` lacks an empty decoded image guard and advertises
`mime_type` as a generic string. `ImageUpload` already has the PNG/JPEG literal. The issue
comments add direct-dependency, IPv6, documentation, unused-symbol, and demo-load cleanup.

## Implementation

1. Correct the module docstring. Keep existing registration tests; no prose-parsing guard.
2. Assign the last raw text unconditionally after each classified failed attempt. Keep the
   terminal backend-failure path intact. Clarify the field docstring.
3. Define `ImageMimeType = Literal["image/png", "image/jpeg"]` in `newton/models.py`, use it
   in `ImageUpload` and the tool argument, and check alias/map agreement. Retain the inline
   MIME null check and existing size limits. Reject decoded zero bytes before backend use.
4. Use an SDK-free `InputValidationError(ValueError)` at deliberate input-rejection sites
   only. Prefer a small shared exception definition over MCP imports in the action library.
   Change gateway-owned image/timeseries checks and proposal preflight helpers to raise it
   with safe, actionable messages. At the tool boundary translate only this marked type to
   SDK `ToolError`. A `functools.wraps` decorator is acceptable if it preserves SDK schema
   introspection, but it must not catch generic `ValueError`. Do not wrap a backend call in
   a broad input-error handler. No raw rejected payload in the marked errors.
5. Add `mcp-types` as a direct dependency compatible with `mcp>=2.2,<3`; update the lock
   without an unrelated upgrade.
6. Validate malformed bracketed URL shapes at config/model load. Reuse #28's safe validation
   error handling where appropriate; raw Pydantic input echo must not reveal URL userinfo.
   Keep `_canonical_url` normalization, userinfo, default-port handling, and IPv6 brackets.
7. Check current callers before removing unused constants/aliases. Fix the approver docs
   reference only if still present. Move demo config loading before the proposal/override
   branch and reuse the same object for goals and catalog.

## Tests and compatibility

Use the post-#28 main baseline; historical 495 tests are not an exact acceptance target.
Test final-attempt text both directions, schema enum/null behavior, empty-image rejection,
client-visible marked errors, and generic backend failures with a secret sentinel. Existing
library tests catching `ValueError` stay valid because the marked exception subclasses it.
Adapt direct tool tests to anticipated SDK errors without losing no-payload-echo assertions.

For backend failures, cover each backend entry point used by the four tools. In-process
client assertions inspect returned content, not merely the server exception class. Include
request/response `ValidationError` to catch accidental broad conversion. SDK argument
validation happens before the handler; this cleanup does not replace the SDK's validator.

For URL validation, invalid input with credential-bearing userinfo must render a safe error
without the sentinel. Assert canonical IPv6 text itself, not just equality between two
possibly equally broken URLs. No credential normalization changes.

For demo loading, use a spy to verify one load for ordinary and contract-override runs and
run the existing deterministic/mock smoke. The deferred policy regex stays as-is.

## Sequencing, risks, and rollback

Do not implement before #28 merges. Rebase/resolve against its final main code so the auth
factory and safe validation changes are retained. Do not duplicate or undo its defenses.
Tool names/defaults/envelope keys remain unchanged; MIME schema and deliberate error text
are intentional improvements. No infrastructure or live integration changes.

Concurrent discovery and matched-rule policy metadata remain open in issue #23. A completion
comment must list finished items and leave those pending; do not use automatic issue-closing
keywords in the PR. Rollback uses a revert PR targeting the relevant cleanup commits (or
`git revert -m 1 <merge>` for the merge), not a direct main push.
