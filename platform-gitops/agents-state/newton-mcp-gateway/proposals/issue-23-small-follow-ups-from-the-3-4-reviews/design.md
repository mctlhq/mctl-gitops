# Design: issue-23-small-follow-ups-from-the-3-4-reviews

## Current state

Verified in the read-only clone at `main` (`5541178`, "Merge pull request #32 from
mctlhq/fix/runtime-verification-safety"). Baseline suite: **495 passed** under `mcp==2.2.0`.

### The server and its four tools

`src/newton_mcp/server.py` is a single `create_server(settings, backend)` factory that builds an
`MCPServer` (from `mcp.server.mcpserver`, the v2 rename of FastMCP) and registers four tools with
`@server.tool(...)`:

| tool | defined at | deliberate `ValueError`s in the body |
| --- | --- | --- |
| `newton_query` | `server.py:65` | none |
| `newton_embed_timeseries` | `server.py:99` | empty/ragged `channels` (`server.py:106-107`) |
| `newton_analyze_image` | `server.py:130` | six, `server.py:142-189` |
| `newton_propose_action` | `server.py:216` | raised inside `propose_action()` |

The module docstring at `server.py:1-5` still reads "Three tools on purpose", written before #4
added `newton_propose_action`. `tests/test_mcp_server.py::test_lists_exactly_the_documented_tools`
already asserts the four names, so the docstring is the only stale statement -- and nothing checks
it, which is why it drifted (**FU1**).

Each tool reads `AppState` out of the lifespan via `_state(ctx)` (`server.py:53-54`). Because
`MCPServer.call_tool` builds a `Context` without a request context, `tests/conftest.py:61-80`
provides a `call_tool` helper that fabricates the `AppState` and calls `tool.run(...)` directly.
Every existing tool test goes through that helper; **no test currently drives a real MCP client**.

### How the MCP SDK v2 surfaces tool errors (FU5 -- the substantive finding)

The issue asks to "check how the MCP SDK v2 surfaces tool errors". Read from the real
`mcp==2.2.0` wheel:

- `mcp/server/mcpserver/exceptions.py` defines `ToolError` ("a tool failure you anticipated") and
  `UnexpectedToolError(ToolError)` ("the SDK raises this itself, around a crash... **You never
  raise it**").
- `mcp/server/mcpserver/tools/base.py:205-210`, in `Tool.run`:
  ```python
  except (ToolError, ResourceError) as exc:
      raise ToolError(f"Error executing tool {self.name}: {exc}") from exc
  except Exception as exc:
      # A crash: the exception's own text stays on the server.
      raise UnexpectedToolError(f"Error executing tool {self.name}") from exc
  ```
- `mcp/server/mcpserver/server.py:428-447`, in `_handle_call_tool`: a plain `ToolError` is logged
  at INFO (`"Tool %r failed: %r"`); anything else gets `logger.exception(...)`. Either way it
  returns `CallToolResult(content=[TextContent(text=str(exc))], is_error=True)`.

So the client's text is `str(exc)` of whatever `Tool.run` raised. A `ValueError` becomes
`UnexpectedToolError("Error executing tool <name>")` -- the message is stripped **by design**.
Confirmed by running a probe against the real SDK with an in-process `mcp.Client`:

```
raise_value_error  -> is_error=True  text='Error executing tool raise_value_error'
raise_tool_error   -> is_error=True  text="Error executing tool raise_tool_error: file_id must end in ..."
```

This reproduces the issue's stdio-smoke observation exactly, and identifies the fix: raise the
SDK's `ToolError` for anticipated failures. The same probe confirmed `mcp.Client` accepts an
`MCPServer` instance for in-process testing, and that `mcp/client/client.py:113` does
`await exit_stack.enter_async_context(server.lifespan(server))` -- so a client-level test gets the
**real** `AppState` and needs none of `conftest.call_tool`'s scaffolding.

`tests/test_analyze_image.py:133-137` already documents the symptom from the inside:

```python
def _root_cause(exc: BaseException) -> BaseException:
    """Unwrap the framework's UnexpectedToolError wrapper to the raw ValueError
    the tool raised (see conftest.call_tool's docstring for why the wrapper's
    own str() doesn't carry the message)."""
```

Twelve assertions in that file rely on this helper -- the main regression surface for FU5.

### `propose_action`'s final `raw_text` (FU2)

`src/newton_mcp/action/propose.py` runs up to `MAX_ATTEMPTS = 2` attempts. `_classify_output`
(`propose.py:208-273`) returns either a validated contract or `(raw_text, errors)`, with
`raw_text=None` for `empty_output` and `not_a_string`. The loop at `propose.py:169-170` keeps a
*sticky* last-seen value:

```python
if raw_text is not None:
    last_raw_text = raw_text
```

`ProposeActionResult.raw_text` is documented by the #4 spec as "the last attempt's raw text, or
`None`", but the guard makes it "the last **non-None** text seen across attempts". The divergence
is exactly the case the issue names: attempt 1 yields text, attempt 2 yields no string output.
No existing test covers it -- `test_invalid_json_both_attempts_fails` (both attempts yield text) and
the `empty_output`/`not_a_string` parametrisation (neither attempt yields text) both straddle it.

Note `propose.py:150-154` (the `backend_failed` early return) already computes `raw_text` from
*that attempt's* outputs only, so the terminal path is already spec-conformant; only the
exhausted-attempts path diverges.

### `mime_type` typing (FU3) and the empty inline image (FU4)

`newton_analyze_image`'s `mime_type` is `str | None` (`server.py:134`), validated at runtime against
`IMAGE_MIME_EXTENSIONS` (`server.py:150-155`), whose keys are the single source of truth in
`src/newton_mcp/newton/models.py:24`. `ImageUpload.mime_type` in the same file (`models.py:97`) is
already `Literal["image/png", "image/jpeg"]`, so the enum form exists in the codebase -- just
duplicated as a literal rather than shared.

For FU4, the inline path's guards (`server.py:156-179`) bound encoded length, decode with
`validate=True`, and bound decoded size -- but nothing rejects *zero* bytes. Confirmed live against
the clone:

```
BUG CONFIRMED: backend calls = 1
  event sent: {'type': 'data.base64_img', 'event_data': {'contents': ''}}
```

`image_base64=""` passes the "exactly one source" check (it is not `None`), passes the length bound,
decodes to `b""`, and is sent to `/query` as a zero-byte `data.base64_img` event.
`newton_embed_timeseries` already rejects the analogous empty input (`server.py:106-107`), so the
gateway is internally inconsistent. `docs/newton-api-notes.md:12` records that
`event_data.contents` is "the base64 encoded image as a byte string" -- an empty string is not a
documented input, so rejecting locally is the conservative reading.

## Proposed solution

Five changes across **three** source files. All five were prototyped in a scratch copy and the full
suite re-run: **495 passed** after adapting the twelve FU5-affected assertions.

### 1. FU1 -- docstring, plus a guard

`server.py:3`: "Three tools on purpose." -> "Four tools on purpose." Add a test to
`tests/test_mcp_server.py` that parses the count word out of `server_module.__doc__` and compares it
to `len(await server.list_tools())`. This follows `tests/test_docs_consistency.py`'s stated
philosophy -- "check the doc corpus against the real repo, not manually" -- and makes the drift
mechanically impossible to repeat.

### 2. FU2 -- `raw_text` is the last attempt's text

Delete the `if raw_text is not None:` guard at `propose.py:169-170`, leaving an unconditional
`last_raw_text = raw_text`. That is the whole fix: `raw_text` now always reflects the attempt that
last ran, `None` included. Verified:

```
attempt1=text, attempt2=empty_output  -> raw_text=None  errors=[(1,'invalid_json'), (2,'empty_output')]
attempt1=text, attempt2=not_a_string  -> raw_text=None  errors=[(1,'invalid_json'), (2,'not_a_string')]
```

No existing `test_propose_action.py` assertion changes (`test_invalid_json_both_attempts_fails`
still sees `"nope2"`). Also tighten `ProposeActionResult.raw_text`'s and `propose_action`'s
docstrings to state the rule, so code and spec agree in writing as well as behaviour.

### 3. FU3 -- shared `ImageMimeType` alias

In `models.py`, promote the literal to a named alias and reuse it in all three places:

```python
ImageMimeType = Literal["image/png", "image/jpeg"]
IMAGE_MIME_EXTENSIONS: dict[ImageMimeType, str] = {"image/png": ".png", "image/jpeg": ".jpg"}
```

`ImageUpload.mime_type` becomes `ImageMimeType`, and `newton_analyze_image`'s parameter becomes
`mime_type: ImageMimeType | None = None`. A test asserts
`set(get_args(ImageMimeType)) == set(IMAGE_MIME_EXTENSIONS)` so the two can never drift.

Verified schema output from the real SDK:

```json
"mime_type": {"anyOf": [{"enum": ["image/png", "image/jpeg"], "type": "string"},
                        {"type": "null"}], "default": null}
```

An out-of-enum value is now rejected at *argument* validation, before the body runs -- and the SDK
reports argument-validation failures as a plain `ToolError`, so the pydantic message (which names
both accepted values) already reaches the client. The body's `mime_type is None` check stays: the
schema permits `null`, and the body must still forbid it alongside `image_base64`.

### 4. FU4 -- reject a zero-byte image

One guard, immediately after the decode at `server.py:172-174`:

```python
if not raw:
    raise ValueError(
        "image_base64 decoded to zero bytes; provide a non-empty base64-encoded "
        "PNG or JPEG image"
    )
```

Placed *after* the decode rather than before it so it also catches a bare
`data:image/png;base64,` prefix, which strips to `""` at `server.py:157-158`. Still before any
network call, matching `newton_embed_timeseries`. It sits before the `len(raw) > max_bytes` check,
so the zero-byte message is never shadowed by a size message.

### 5. FU5 -- surface anticipated validation failures as `ToolError`

A small decorator in `server.py`, applied innermost (below `@server.tool(...)`) on all four tools:

```python
def _surface_value_errors(fn):
    """Re-raise a tool body's `ValueError` as the SDK's `ToolError`."""
    @functools.wraps(fn)
    async def wrapper(**kwargs):
        try:
            return await fn(**kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    return wrapper
```

Why a decorator at the MCP boundary rather than changing the raises:

- **It keeps the action library SDK-free.** `propose_action`'s preflight `ValueError`s live in
  `action/propose.py`, which is deliberately backend-agnostic ("driven entirely through the
  `NewtonBackend` protocol") and which `docs/action-runtime.md:620` says must not "wire into
  `create_server()`". Converting at the boundary covers it without importing `mcp` there, and
  leaves its `pytest.raises(ValueError)` tests untouched.
- **One place, not eight.** `newton_analyze_image` alone raises `ValueError` at six sites.
- **It is framework-safe.** Verified against the real SDK: with `functools.wraps`,
  `inspect.signature` follows `__wrapped__`, so schema generation, `required`, the `ToolAnnotations`,
  `ctx` exclusion from the schema, and structured output all behave identically. The probe returned
  `schema props: ['file_id', 'question']`, `required: ['question']`,
  `annotations read_only: True`, and on success `is_error=False` with the normal
  `structured_content`.

`ToolError` (not `MCPError`) is correct here: `MCPError` means "respond with a JSON-RPC protocol
error", whereas a rejected argument should come back as a normal `is_error=True` tool result the
model can read and retry.

Non-`ValueError` failures are untouched -- they still become `UnexpectedToolError` with a generic
message and a server-side traceback, which is what a genuine crash should do.

**Test-surface consequence (the main work item).** Twelve assertions in
`tests/test_analyze_image.py` use `_root_cause(...)` + `isinstance(cause, ValueError)`. With the
change the raised type is `ToolError`, so they fail -- exactly as they should, since the behaviour
they pin has intentionally changed. The fix is a simplification: delete `_root_cause` and assert on
the `ToolError` message directly.

```python
with pytest.raises(ToolError) as ei:
    await call_tool(...)
message = str(ei.value)
assert not isinstance(ei.value, UnexpectedToolError)   # anticipated, not a crash
assert message_fragment in message
```

`assert not isinstance(ei.value, UnexpectedToolError)` is the load-bearing assertion: it is what
distinguishes "deliberately rejected, reason included" from "crashed, reason withheld". Verified:
all 495 tests pass with this adaptation, including the `mime_type="image/gif"` case, which now fails
at argument validation (`pydantic.ValidationError` subclasses `ValueError`, and the SDK's own
argument-validation path already raises plain `ToolError`).

On top of that, a new `tests/test_mcp_errors.py` drives a real in-process `mcp.Client(server)` --
the client-level test the issue asks for -- asserting `CallToolResult.is_error is True` and the
reason text in `result.content[0].text`, for the exact `file_id="fil_abc"` case from the smoke plus
one `newton_embed_timeseries` and one `newton_propose_action` case. This is the only test in the
repo that exercises the genuine client -> server path, so it also covers lifespan wiring that
`conftest.call_tool` fabricates.

### Docs

- `README.md:101-102`: no change needed (the tool description already names the accepted MIME
  types), but confirm the `newton_analyze_image` row still reads true after the enum change.
- `docs/newton-api-notes.md:16`: the `mime_type` row ("gateway-side validation only; never sent on
  the wire") stays accurate -- extend it to note the validation is now schema-level.
- `docs/architecture.md` (design-principles section, around line 26): add two or three lines stating
  that anticipated validation failures are raised as `ToolError` so the reason reaches the client,
  and that everything else stays a crash. Keep `tests/test_docs_consistency.py` green -- any
  backticked `docs/`, `src/`, `tests/` path added must resolve.

## Alternatives

1. **Replace every `raise ValueError` with `raise ToolError` at each site.** Dropped: it forces
   `mcp` into `action/propose.py`, breaking the module's deliberate SDK independence
   (`docs/action-runtime.md:620`) and invalidating its `pytest.raises(ValueError)` tests -- or else
   leaves `newton_propose_action`'s preflight errors still opaque, i.e. a partial fix to the one item
   that actually changes user-visible behaviour. An eight-site edit also has more drift surface than
   one decorator.

2. **Catch `ValueError` explicitly in each of the four tool bodies (`try`/`except` around the
   whole body).** Functionally identical, no framework-introspection risk at all, but adds four
   nested blocks and re-indents ~120 lines of working code for no behavioural gain. Dropped once
   the decorator was empirically confirmed to preserve schema generation, annotations, `ctx`
   handling and structured output.

3. **FU2: keep the sticky `raw_text` and document it as "the last text seen".** The issue permits
   this and it is a one-line docstring change. Dropped because `raw_text` carries no attempt
   marker, so a caller cannot tell which attempt produced it; the `errors` list already preserves
   attempt 1's `kind` and `message`, so the diagnostic loss is small. Recorded as an open question
   since it is the owner's call.

4. **FU3: derive a dynamic enum from `IMAGE_MIME_EXTENSIONS.keys()` instead of a `Literal`.** A
   `Literal` cannot be built from a runtime dict in a way pydantic will read for schema generation
   without `eval`-style tricks. Dropped in favour of the named alias plus a `get_args` equality test,
   which gets the same no-drift guarantee with explicit, readable code.

5. **FU4: reject the empty payload before decoding (`if not payload`).** Equivalent for
   `image_base64=""`, but misses `data:image/png;base64,` with an empty payload. Dropped for the
   post-decode guard, which is one check covering both and is still pre-network.

## Platform impact

- **Migrations:** none. No config, no schema, no persisted state. Three source files change:
  `src/newton_mcp/server.py`, `src/newton_mcp/newton/models.py`,
  `src/newton_mcp/action/propose.py`.
- **Backward compatibility (wire):** tool names, argument names, argument defaults and result
  envelope keys are all unchanged. `mime_type`'s JSON-Schema type narrows from `string` to a
  nullable enum -- a previously-accepted-then-rejected value is now rejected one layer earlier with
  a better message, and every value that used to succeed still succeeds.
- **Backward compatibility (client-visible behaviour):** intentional and the point of FU5 -- a
  rejected call's text changes from `Error executing tool <name>` to
  `Error executing tool <name>: <reason>`. `is_error` stays `True`; no client that only checks
  `is_error` is affected. A client string-matching the old generic message would break; that is
  not a contract this repo has ever documented.
- **Backward compatibility (internal):** `_root_cause` in `tests/test_analyze_image.py` is deleted
  and twelve assertions are rewritten. `conftest.call_tool` is unchanged and still used.
- **Resource impact:** nil at steady state. Strictly negative request count: FU4 removes one
  pointless `/query` call per empty-image invocation, and FU3 moves a rejection earlier. The
  decorator adds one `try`/`except` frame per tool call.
- **Risk: the decorator over-reports.** An internal bug surfacing as `ValueError` would show its
  message to the client instead of being logged as a crash. *Mitigation:* the wrapper catches only
  `ValueError` (not bare `Exception`); messages in this repo are already written not to echo caller
  payloads, pinned by `test_invalid_base64_error_does_not_echo_payload`; and the new client-level
  test asserts `not isinstance(..., UnexpectedToolError)`, so a crash silently reclassified as
  anticipated is visible. Recorded as an open question with a narrower option.
- **Risk: `pydantic.ValidationError` is a `ValueError`.** A stray `model_validate` in a tool body
  would be reported as anticipated. *Mitigation:* no tool body validates caller data outside an
  existing `try` today; noted in requirements' open questions so a reviewer can choose to exclude
  it explicitly.
- **Risk: decorator breaks SDK introspection.** *Mitigation:* already disproved empirically against
  `mcp==2.2.0` (schema properties, `required`, annotations, `ctx` exclusion, structured output all
  identical); T7 re-pins the schema so a future SDK minor cannot regress it silently.
- **Risk: FU2 loses attempt 1's text in a real debugging session.** *Mitigation:* `errors` still
  carries attempt 1's `kind`, `message` and `loc`. Recorded as an open question.
- **Risk: SDK behaviour is version-specific.** The pin is `mcp>=2.2,<3`, so a 2.x minor could in
  principle change the `ToolError`/`UnexpectedToolError` split. *Mitigation:* the client-level test
  in T5/T6 asserts against the real client path, so a change fails CI rather than silently
  degrading the gateway.
- **Verification status:** all five changes prototyped in a scratch copy against real
  `mcp==2.2.0`; suite green (495 passed) both before and after. The only tests requiring edits were
  the twelve FU5-affected assertions in `tests/test_analyze_image.py`.
