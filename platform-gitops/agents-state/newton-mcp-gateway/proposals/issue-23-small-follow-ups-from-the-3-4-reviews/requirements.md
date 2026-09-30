# Small follow-ups from the #3 / #4 reviews

## Context

Issue #23 collects five non-blocking leftovers from the reviews of #3 and #4 so they are not
lost. Four are small correctness or ergonomics fixes inside `src/newton_mcp/server.py`,
`src/newton_mcp/newton/models.py` and `src/newton_mcp/action/propose.py`: a stale module
docstring that still says "Three tools on purpose" after `newton_propose_action` made four; a
failure-envelope `raw_text` that can carry attempt 1's text when the #4 spec says it is the last
attempt's text or `None`; a `mime_type` parameter typed `str | None` that hides its two accepted
values from the tool schema; and an `image_base64=""` that decodes to `b""` and is sent to
`/query` as a zero-byte `data.base64_img` event instead of being rejected locally.

The fifth is the one that actually changes what a user sees. In the stdio smoke on `main`, a
tool-side `ValueError` (for example `file_id="fil_abc"`) reached the client only as
`Error executing tool newton_analyze_image`, with the reason stripped. This was confirmed against
the real `mcp==2.2.0` SDK: `mcp.server.mcpserver.tools.base.Tool.run` wraps any exception that is
not `ToolError`/`ResourceError`/`MCPError` in `UnexpectedToolError(f"Error executing tool
{self.name}")`, deliberately withholding the original text from the client, while a deliberate
`ToolError` is surfaced as `Error executing tool <name>: <message>`. Every one of this gateway's
input validations is a `ValueError`, so every one of them is currently opaque to MCP clients --
the careful, specific messages written in #3 and #4 (which extension a `file_id` must have, which
`NEWTON_MAX_IMAGE_BYTES` to raise) never reach the caller who needs them. No public contract
changes: the four tool names, their arguments and their result envelopes all stay as they are.

## User stories

- AS an MCP client (or the model driving it) I WANT a rejected tool call to tell me *why* it was
  rejected SO THAT I can correct the argument myself instead of guessing from a generic
  "Error executing tool" string.
- AS an MCP client I WANT `newton_analyze_image`'s `mime_type` to advertise its accepted values in
  the tool schema SO THAT I can send a valid value on the first attempt rather than discovering
  the constraint from a runtime error.
- AS an operator of the gateway I WANT an empty inline image rejected before any network call SO
  THAT a pointless zero-byte request never reaches Archetype and never consumes quota.
- AS a consumer of `newton_propose_action`'s failure envelope I WANT `raw_text` to mean exactly
  one thing SO THAT I can attribute the text I am shown to a specific attempt.
- AS a maintainer I WANT the `server.py` module docstring's tool count checked by a test SO THAT
  it cannot silently drift again the next time a tool is added.

## Acceptance criteria (EARS)

### FU1 -- stale module docstring

- WHEN `src/newton_mcp/server.py`'s module docstring is read THE SYSTEM SHALL state a tool count
  equal to the number of tools `create_server()` registers (four: `newton_query`,
  `newton_embed_timeseries`, `newton_analyze_image`, `newton_propose_action`).
- WHILE the docstring states a tool count THE SYSTEM SHALL fail a test if that count differs from
  `len(await server.list_tools())`.
- IF a future change adds or removes a tool without updating the docstring THEN THE SYSTEM SHALL
  fail that test rather than ship a stale docstring.

### FU2 -- `propose_action` final `raw_text`

- WHEN `propose_action` returns `status="failed"` after exhausting `MAX_ATTEMPTS` THE SYSTEM SHALL
  set `raw_text` to the final attempt's raw text, or `None` when that attempt produced no string
  output.
- WHEN attempt 1 yields text and attempt 2 fails with `empty_output` or `not_a_string` THE SYSTEM
  SHALL return `raw_text=None`, not attempt 1's text.
- WHEN attempt 1 fails with `empty_output` or `not_a_string` and attempt 2 yields text THE SYSTEM
  SHALL return that attempt-2 text as `raw_text`.
- WHILE `propose_action` returns `status="completed"` THE SYSTEM SHALL keep `raw_text=None`, as
  today.
- WHEN the backend reports `status="failed"` THE SYSTEM SHALL keep the existing terminal behaviour:
  `raw_text` is that attempt's first string output, or `None`.
- WHILE this change is applied THE SYSTEM SHALL keep the failure envelope's key set exactly
  `{status, contract, raw_text, errors, backend, observation_id}` -- no key added or removed.

### FU3 -- `newton_analyze_image` `mime_type` typing

- WHEN a client reads the `newton_analyze_image` input schema THE SYSTEM SHALL expose `mime_type`
  as a nullable enum whose members are exactly `image/png` and `image/jpeg`.
- IF a client sends a `mime_type` outside that enum THEN THE SYSTEM SHALL reject the call at
  argument validation with a message naming the accepted values, and SHALL make no backend call.
- WHILE `mime_type` is typed as an enum THE SYSTEM SHALL keep a single source of truth for the
  accepted MIME types, shared with `IMAGE_MIME_EXTENSIONS` and `ImageUpload.mime_type`, enforced by
  a test.
- IF `image_base64` is supplied with `mime_type=None` THEN THE SYSTEM SHALL still reject the call
  with a message naming the accepted values (the schema permits `null`; the body forbids it).

### FU4 -- empty inline image

- IF `image_base64` decodes to zero bytes THEN THE SYSTEM SHALL raise a validation error naming
  the problem and SHALL make no backend call.
- WHEN `image_base64` is `""`, or a bare `data:image/png;base64,` prefix with no payload, THE
  SYSTEM SHALL reject it locally rather than sending a zero-byte `data.base64_img` event to
  `/query`.
- WHILE rejecting an empty image THE SYSTEM SHALL behave consistently with
  `newton_embed_timeseries`, which already rejects empty `channels` before any network call.

### FU5 -- validation errors reaching MCP clients

- WHEN a tool body raises `ValueError` for an input it deliberately rejects THE SYSTEM SHALL
  surface that `ValueError`'s message to the MCP client in the `CallToolResult` content, alongside
  `is_error=True`.
- WHILE surfacing a deliberate validation failure THE SYSTEM SHALL raise the SDK's
  `mcp.server.mcpserver.exceptions.ToolError`, so the SDK classifies it as anticipated (logged at
  INFO without a traceback) rather than as a crash.
- IF a tool fails for any reason other than a `ValueError` THEN THE SYSTEM SHALL leave the SDK's
  crash handling untouched: `UnexpectedToolError`, a generic client-facing message, and a
  server-side traceback at ERROR.
- WHEN the failure is surfaced THE SYSTEM SHALL NOT include the caller's rejected payload in the
  message, preserving the #3 rule that an invalid-base64 error never echoes the payload.
- WHILE this behaviour is in place THE SYSTEM SHALL pin it with a test that drives a real
  in-process MCP client (`mcp.Client(server)`) and asserts on `CallToolResult.is_error` and the
  reason text, not only on the server-side exception type.
- WHILE tool-side `ValueError` is converted at the MCP boundary THE SYSTEM SHALL keep
  `newton_mcp.action.propose.propose_action` free of any MCP SDK import, so it stays callable as a
  backend-agnostic library and its own tests keep asserting `pytest.raises(ValueError)`.

## Out of scope

- Any change to tool names, argument names, argument defaults, or result envelope keys.
- Adding a fifth tool, or splitting an existing one.
- Structured/machine-readable error payloads for tool failures (an error `code` enum, or a
  `structured_content` error body). This proposal only makes the existing human-readable reason
  reach the caller.
- Migrating off `ValueError` inside `src/newton_mcp/action/**` or `src/newton_mcp/runtime/**`.
  Those modules stay SDK-free.
- Image validation beyond emptiness and size: no magic-byte sniffing, no decode, no check that the
  bytes agree with the declared `mime_type`.
- Accepting new MIME types (for example `image/webp`) or new `file_id` extensions.
- Anything touching the `mcp>=2.2,<3` pin, or supporting the legacy `mcp.server.fastmcp` API.
- Uploading images via the Files API from a tool (`ImageUpload` stays backend-only).

## Open questions

- **FU2 direction.** The issue offers two resolutions -- return `None`, or document that `raw_text`
  is the last text *seen*. This proposal takes the first: align the code to the #4 spec. Rationale:
  `raw_text` carries no attempt marker, so a value that may come from any attempt is unattributable,
  whereas the `errors` list already records attempt 1's `kind` and `message`; and adding a
  `raw_text_attempt` field would change the envelope's key set, which the issue rules out. If the
  owner prefers the documentation route instead, task 2 becomes a docstring plus README/spec wording
  change and test T2 inverts to assert attempt 1's text is retained -- the rest of the proposal is
  unaffected.
- **FU5 blast radius.** This proposal applies the `ValueError` -> `ToolError` conversion uniformly to
  all four tools, for a predictable rule ("a rejected argument always tells you why"). The cost: a
  genuine internal bug that happens to surface as `ValueError` would now have its message shown to
  the client instead of being logged as a crash. A narrower alternative is to apply it only to the
  three tools that deliberately raise `ValueError`. Uniform is recommended; flagged because it is a
  judgement call, not a derived requirement.
- **FU5 and pydantic.** `pydantic.ValidationError` subclasses `ValueError`, so a stray
  `model_validate` raising inside a tool body would also be surfaced as an anticipated failure.
  Today no tool body validates caller data outside an existing `try` block, so this is latent, not
  live. Noted so a reviewer can decide whether the wrapper should exclude `ValidationError`
  explicitly.
- **Docs placement.** A short note on MCP error surfacing would fit `docs/architecture.md`'s design
  principles. The exact wording is the owner's call; the task lists it as a small doc touch with no
  claim about live Newton behaviour.
