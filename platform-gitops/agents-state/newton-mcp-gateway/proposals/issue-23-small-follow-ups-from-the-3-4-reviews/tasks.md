# Tasks: issue-23-small-follow-ups-from-the-3-4-reviews

Baseline before starting: `uv sync --group dev && uv run pytest` must report **495 passed**.
Tasks 1-4 are independent of each other. Task 5 is the only one that changes existing tests, so
do it last; task 6 depends on it.

- [ ] 1. **FU1 -- fix the stale module docstring.** In `src/newton_mcp/server.py:3`, change
      "Three tools on purpose." to "Four tools on purpose." Nothing else in the docstring changes.
      — DoD: the docstring states four; `uv run pytest` still green; T1 (below) passes.

- [ ] 2. **FU2 -- make `raw_text` the last attempt's raw text, or `None`.** In
      `src/newton_mcp/action/propose.py:169-170`, delete the `if raw_text is not None:` guard so the
      assignment is an unconditional `last_raw_text = raw_text`. Then update the two docstrings that
      describe the field: `ProposeActionResult` (`propose.py:47-53`) gains an explicit note that
      `raw_text` is the final attempt's raw text or `None` when that attempt produced no string
      output, and `propose_action`'s docstring (`propose.py:1-9`) says the same. Do not add or remove
      any envelope field.
      — DoD: `raw_text` is `None` when the last attempt yielded no string output, even if an earlier
      attempt yielded text; `set(ProposeActionResult(...).model_dump())` is still exactly
      `{status, contract, raw_text, errors, backend, observation_id}`; no existing
      `tests/test_propose_action.py` assertion needed changing; T2 and T3 pass.

- [ ] 3. **FU3 -- share one `ImageMimeType` alias and use it for `mime_type`.** In
      `src/newton_mcp/newton/models.py`, add `ImageMimeType = Literal["image/png", "image/jpeg"]`
      above `IMAGE_MIME_EXTENSIONS`, retype that dict as `dict[ImageMimeType, str]`, and change
      `ImageUpload.mime_type` (`models.py:97`) from its inline `Literal[...]` to `ImageMimeType`.
      In `src/newton_mcp/server.py`, import `ImageMimeType` and change `newton_analyze_image`'s
      parameter (`server.py:134`) to `mime_type: ImageMimeType | None = None`. Keep the body's
      `mime_type is None or mime_type not in IMAGE_MIME_EXTENSIONS` check as it is -- the schema
      permits `null`, so the body must still reject it.
      — DoD: the `newton_analyze_image` input schema renders `mime_type` as
      `{"anyOf": [{"enum": ["image/png", "image/jpeg"], "type": "string"}, {"type": "null"}]}`;
      no literal MIME string is duplicated outside `models.py`; T4 passes.

- [ ] 4. **FU4 -- reject a zero-byte inline image before any network call.** In
      `src/newton_mcp/server.py`, immediately after the `base64.b64decode` block
      (`server.py:171-174`) and **before** the `len(raw) > max_bytes` check, add:
      ```python
      if not raw:
          raise ValueError(
              "image_base64 decoded to zero bytes; provide a non-empty base64-encoded "
              "PNG or JPEG image"
          )
      ```
      Placement after the decode is deliberate: it also catches a bare `data:image/png;base64,`
      prefix, which `server.py:157-158` strips to `""`.
      — DoD: `image_base64=""` and `image_base64="data:image/png;base64,"` both raise before the
      backend is touched; `mock_backend.requests == []` in both cases; the zero-byte message, not a
      size message, is the one raised; T5 passes.

- [ ] 5. **FU5 -- surface anticipated validation failures to MCP clients as `ToolError`.** Two
      parts, one commit.
      *(a) Source.* In `src/newton_mcp/server.py`: `import functools`; add
      `from mcp.server.mcpserver.exceptions import ToolError`; define a module-level
      `_surface_value_errors(fn)` decorator that wraps an async tool body with
      `functools.wraps`, catches `ValueError`, and re-raises `ToolError(str(exc)) from exc`. Apply
      it to all four tools, placed **innermost** -- directly above each `async def`, below the
      `@server.tool(...)` call. Do not touch `src/newton_mcp/action/**` or
      `src/newton_mcp/runtime/**`: `propose_action` keeps raising `ValueError` and keeps importing
      no MCP symbol.
      *(b) Existing tests.* In `tests/test_analyze_image.py`, delete the `_root_cause` helper
      (`lines 133-137`) and rewrite the twelve assertions that used it. The pattern is
      `with pytest.raises(ToolError) as ei:` / `message = str(ei.value)` /
      `assert not isinstance(ei.value, UnexpectedToolError)` / then the existing fragment and
      no-echo assertions against `message`. Import both names from
      `mcp.server.mcpserver.exceptions`. Affected tests:
      `test_invalid_input_raises_before_any_request` (7 params),
      `test_oversize_image_rejected_before_request`,
      `test_invalid_base64_error_does_not_echo_payload`,
      `test_oversize_payload_rejected_before_decoding`,
      `test_one_byte_over_limit_caught_by_post_decode_check` (3 params).
      — DoD: full suite green; no `UnexpectedToolError` is raised for any deliberately rejected
      input in `tests/test_analyze_image.py`; `grep -r "from mcp" src/newton_mcp/action/` and
      `.../runtime/` show no new import of `mcp.server.mcpserver.exceptions`;
      `tests/test_propose_action.py::test_preflight_value_errors_make_zero_backend_calls` still
      asserts `pytest.raises(ValueError)` and still passes unchanged; T6 and T7 pass.

- [ ] 6. **Docs touch-up** (depends on 5). In `docs/newton-api-notes.md:16`, extend the `mime_type`
      row to note the accepted values are now enforced by the tool schema, not only by a body check.
      In `docs/architecture.md`'s design-principles section (around line 26), add two or three lines
      stating that an anticipated validation failure is raised as the SDK's `ToolError` so its reason
      reaches the client, while anything else stays a crash with the reason withheld. Re-check the
      `README.md:101-102` tool table still reads true. Claim nothing about live Newton behaviour.
      — DoD: `uv run pytest tests/test_docs_consistency.py` green (every backticked
      `docs/`/`src/`/`tests/` path resolves, every `uv run` target real); no new `NEWTON_*`/`ATAI_*`
      token introduced.

- [ ] 7. **Final gate** (depends on 1-6). Run `uv sync --group dev && uv run pytest`.
      — DoD: all tests pass, count is 495 plus the new tests below; no skips added; no file outside
      `src/newton_mcp/server.py`, `src/newton_mcp/newton/models.py`,
      `src/newton_mcp/action/propose.py`, `tests/**` and the three docs files is modified.

## Tests

- [ ] T1. **Docstring tool count cannot drift again** (`tests/test_mcp_server.py`). Parse the count
      word out of `server_module.__doc__` with
      `re.search(r"\b(One|Two|Three|Four|Five|Six) tools? on purpose\b", doc)`, map it to an int, and
      assert equality with `len(await server.list_tools())`. Assert the regex matched at all, so
      deleting the sentence fails rather than silently passing. Mirrors
      `tests/test_docs_consistency.py`'s "check the docs against the real repo" approach.

- [ ] T2. **`raw_text` is `None` when the last attempt yielded no string output**
      (`tests/test_propose_action.py`). Parametrised over `[]` (`empty_output`) and `[None]`
      (`not_a_string`), with a `ScriptedNewtonBackend([_completed("attempt-1-text"), {"status":
      "completed", "outputs": bad}])`. Assert `status == "failed"`, `raw_text is None`, exactly two
      backend calls, and `[(e.attempt, e.kind) for e in result.errors] == [(1, "invalid_json"),
      (2, <kind>)]` -- so the test also proves attempt 1's failure is still reported even though its
      text is not returned. This is the case the issue names and that no current test covers.

- [ ] T3. **`raw_text` is attempt 2's text when attempt 1 yielded none**
      (`tests/test_propose_action.py`). Script `[{"status": "completed", "outputs": []},
      _completed("attempt-2-text")]`. Assert `raw_text == "attempt-2-text"`. Guards against
      "fixing" T2 by hard-coding `None`.

- [ ] T4. **`mime_type` enum: schema and no-drift** (`tests/test_analyze_image.py`). (a) From
      `await server.list_tools()`, assert the `newton_analyze_image` schema's `mime_type` entry
      offers exactly `{"image/png", "image/jpeg"}` as its enum members and admits `null`.
      (b) Assert `set(get_args(ImageMimeType)) == set(IMAGE_MIME_EXTENSIONS)` so the alias and the
      extension map can never diverge. (c) Keep the existing `mime_type="image/gif"` rejection case
      -- it now fails at argument validation, and the message must still contain `mime_type`.
      (d) Add a case for `image_base64` supplied with `mime_type=None`, which the schema permits and
      the body must still reject.

- [ ] T5. **Empty inline image rejected before any request** (`tests/test_analyze_image.py`).
      Parametrised over `image_base64=""` and `image_base64="data:image/png;base64,"`, both with
      `mime_type="image/png"`. Assert the raised message contains "zero bytes", that it is not a
      size/`NEWTON_MAX_IMAGE_BYTES` message, and that `mock_backend.requests == []`.

- [ ] T6. **Client-level: the reason reaches an MCP client** (new `tests/test_mcp_errors.py`). Use a
      real in-process client: `async with Client(create_server(Settings(), backend=mock_backend))
      as client:` -- this runs the server's own lifespan, so no `conftest.call_tool` scaffolding is
      needed. For each of: `newton_analyze_image` with `file_id="fil_abc"` (the exact stdio-smoke
      case from the issue), `newton_embed_timeseries` with `channels=[]`, and
      `newton_propose_action` with no events -- assert `result.is_error is True` and that
      `result.content[0].text` contains the specific reason (`"file_id"`, `"channels"`,
      `"text_events"` respectively) **and** is not merely
      `"Error executing tool <name>"`. Also assert one success path returns `is_error is False`
      with populated `structured_content`, so the decorator is shown not to break the happy path.
      Assert `mock_backend.requests == []` for the rejected calls.

- [ ] T7. **The decorator does not perturb tool registration** (`tests/test_mcp_server.py`). After
      the decorator is applied, assert from `await server.list_tools()` that for every tool `ctx` is
      absent from `input_schema["properties"]`, that `required` still lists the genuinely required
      arguments (e.g. `question` for `newton_analyze_image`, `query` for `newton_query`,
      `channels` for `newton_embed_timeseries`), and that
      `annotations.read_only_hint is True` still holds for all four. The existing
      `test_tools_are_marked_read_only` and `test_analyze_image_schema_has_no_upload_property` cover
      part of this; extend rather than duplicate. Pins the one framework-introspection risk in the
      design against a future `mcp` 2.x minor.

## Rollback

Every change is source-only, additive-in-behaviour and confined to three source files plus tests
and docs. There is no migration, no persisted state, no config key and no deployed component to
drain, so rollback is a plain `git revert` of the merge commit -- nothing else to undo.

Partial rollback, if only one item proves troublesome, in decreasing order of independence:

- **FU1 (task 1 + T1), FU4 (task 4 + T5):** fully self-contained. Revert the hunk and its test.
- **FU3 (task 3 + T4):** revert `mime_type: ImageMimeType | None` to `str | None` in
  `server.py` and restore the inline `Literal[...]` on `ImageUpload.mime_type`. The body's runtime
  check against `IMAGE_MIME_EXTENSIONS` was never removed, so validation coverage is unchanged by
  the revert -- only the schema narrows back to `string`.
- **FU2 (task 2 + T2/T3):** restore the `if raw_text is not None:` guard. Equivalently, if the owner
  picks the documentation route from requirements' first open question, keep the guard and change
  only the docstrings plus the direction of T2. No caller code changes either way.
- **FU5 (task 5 + T6/T7):** the widest-reaching item and the one to revert first if a client
  misbehaves. Remove the four `@_surface_value_errors` lines and the decorator, drop the
  `ToolError` import, restore `_root_cause` and the twelve assertions in
  `tests/test_analyze_image.py`, and delete `tests/test_mcp_errors.py`. Client-visible behaviour
  returns to the generic `Error executing tool <name>`. Because `src/newton_mcp/action/**` and
  `src/newton_mcp/runtime/**` were never modified, reverting FU5 cannot affect the action runtime,
  the policy engine or the demo.

Confidence that a revert lands clean: all five changes were prototyped together against real
`mcp==2.2.0` with the suite green before (495 passed) and after, and the only existing tests
touched were the twelve FU5-affected assertions -- so no other test file encodes an assumption that
a partial revert would strand.
