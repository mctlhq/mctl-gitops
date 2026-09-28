# Tasks: issue-3-1-2-newton-analyze-image-via-the-files-a

- [ ] 1. Re-verify the public docs before writing code: the Files API upload page
      (method, path, multipart example, response fields), and the `POST /query` page's
      `events` section. Capture verbatim field names and the page URL for each.
      — DoD: a scratch list of quoted field names + source URLs exists; the three known
      gaps are confirmed still open (`data.base64_img` `event_data` keys undocumented,
      `mime_type` absent as an API field, `/llms.txt` `POST /files/upload` vs reference
      `POST /v0.5/files`). If a gap has since closed, stop and revise the design rather
      than implementing against this proposal.

- [ ] 2. Write `docs/newton-api-notes.md` first (depends on 1) — the traceability ledger:
      a documented/not-documented table with source URLs; the three gaps; the
      documented-but-unused `/query` fields (`multi_image`, `max_frames`, `temperature`,
      `do_sample`, `repetition_penalty`, `top_p`, `top_k`, `presence_penalty`,
      `response_start_prompt`, `template_name`, `query_metadata`, `render`,
      `max_query_size_mb`, `max_wait_time_sec`); the documented limits (512 MB; JPEG,
      PNG, MP4, text, CSV, JSON); the `read_only_hint`-on-an-upload nuance; that an
      upload leaves account-side state this gateway cannot delete; and a standing
      "not validated against a live account" note.
      — DoD: every request field the implementation will send appears in the table with
      a doc source; the file states plainly that the inline `data.base64_img` route is
      not implemented and why.

- [ ] 3. Add `ImageUpload`, `UploadedFile` and `IMAGE_MIME_EXTENSIONS`
      (`{"image/png": ".png", "image/jpeg": ".jpg"}`) to
      `src/newton_mcp/newton/models.py` (depends on 2). `ImageUpload.filename` returns
      `f"image{ext}"`. Do **not** add a `DataEvent.base64_img()` constructor and do not
      change `NewtonQueryRequest`.
      — DoD: Pydantic v2 models with type hints, `mime_type` typed as a
      `Literal["image/png", "image/jpeg"]`; `NewtonQueryRequest.to_payload()` output is
      byte-identical to before.

- [ ] 4. Add `async def upload_image(self, image: ImageUpload) -> UploadedFile: ...` to
      the `NewtonBackend` Protocol in `src/newton_mcp/newton/protocol.py` (depends on 3),
      and export the two new models from `src/newton_mcp/newton/__init__.py`'s `__all__`.
      — DoD: `uv run python -c "from newton_mcp.newton import ImageUpload, UploadedFile"`
      succeeds; the Protocol docstring still names both implementations.

- [ ] 5. Fix the client header bug in `src/newton_mcp/newton/api.py` (depends on 4):
      drop `"Content-Type": "application/json"` from the `httpx.AsyncClient`
      constructor, leaving only `Authorization`. `query()` passes `json=`, so the header
      is still set per request.
      — DoD: `tests/test_api_backend.py` still passes unchanged; a fresh assertion shows
      a `files=`-built request now carries `content-type: multipart/form-data; boundary=...`.

- [ ] 6. Implement `ArchetypeNewtonBackend.upload_image` (depends on 5):
      `POST f"{self._endpoint}/files"` with
      `files={"file": (image.filename, image.data, image.mime_type)}`; parse via the
      existing `_json`; raise `NewtonApiError` on non-200 **or** on
      `is_valid` falsy / missing `file_id`; return
      `UploadedFile(backend="api", file_id=str(body["file_id"]), file_uid=body.get("file_uid"))`.
      — DoD: no retry logic, no new timeout knob, no new dependency; `file_uid` is
      captured but never used to build `file_ids`.

- [ ] 7. Add `max_image_bytes` to `Settings` in `src/newton_mcp/config.py` (depends on 3),
      default `8 * 1024 * 1024`, read from `NEWTON_MAX_IMAGE_BYTES`, with a module
      constant `DOCUMENTED_MAX_UPLOAD_BYTES = 512 * 1024 * 1024`. Reject non-integer,
      `<= 0`, and `> DOCUMENTED_MAX_UPLOAD_BYTES`, naming the variable in the message —
      matching the existing `ValueError` style.
      — DoD: `Settings()` with no arguments still works (so `tests/conftest.py` is
      unchanged); the field is frozen-dataclass-compatible.

- [ ] 8. Make `MockNewtonBackend` image-aware in `src/newton_mcp/newton/mock.py`
      (depends on 4, 3): add `self._uploads: dict[str, ImageUpload]`; `upload_image`
      mints `f"mock-image-{next(self._counter):06d}{ext}"` and records the upload;
      `query()` gains a branch before the existing text branch that fires when any
      `request.file_ids` entry is a known mock upload and returns one output string
      starting `[mock]`, containing "no image was analyzed", the `file_id`, the
      `mime_type`, the decoded byte count and the question, and the existing
      "Set NEWTON_BACKEND=api ..." tail.
      — DoD: no scene description, object list, caption or confidence score anywhere in
      the string; an unknown `file_id` still takes the existing text branch verbatim;
      the Omega branch is untouched.

- [ ] 9. Register `newton_analyze_image` in `src/newton_mcp/server.py` (depends on 6, 7, 8)
      with `ToolAnnotations(read_only_hint=True, open_world_hint=True)` and the signature
      `(ctx, question, image_base64=None, mime_type=None, file_id=None, system_prompt="",
      upload=True, max_new_tokens=400, model=None)`. Validation order, all before any
      network call: exactly-one-of via `(image_base64 is None) == (file_id is None)`;
      `mime_type` required and whitelisted; strip an optional `data:<mime>;base64,`
      prefix; `base64.b64decode(..., validate=True)` in a `try/except` that re-raises a
      `ValueError` without echoing the payload; decoded-size check naming the size, the
      limit and `NEWTON_MAX_IMAGE_BYTES`; then the `upload=False` refusal pointing at
      `docs/newton-api-notes.md`. Then upload (inline branch only), build
      `NewtonQueryRequest(model=model or state.settings.text_model, query=question,
      system_prompt=system_prompt, instruction_prompt=system_prompt,
      file_ids=[resolved_id], max_new_tokens=max_new_tokens)`, and return
      `result.model_dump(exclude={"raw"})`.
      — DoD: the tool description states the exactly-one rule; no `data.base64_img`
      event and no `mime_type` field is ever put on the wire; the `file_id` branch makes
      exactly one HTTP call.

- [ ] 10. Update `README.md` (depends on 9): add the `newton_analyze_image` row to the
      tools table (model family "Newton C", behaviour: one image via the documented Files
      API, `file_id` passed to `/query`), and remove "image analysis via the Files API"
      from the "Planned (see issues)" line. Leave the experimental/mock-validated status
      block and the "What is confirmed vs. proposed" table wording intact, and add a
      pointer to `docs/newton-api-notes.md`.
      — DoD: no claim anywhere that the live integration has been validated; the tool
      count in prose ("Deliberately few") still reads correctly with three tools.

- [ ] 11. Document `NEWTON_MAX_IMAGE_BYTES` in `.env.example` (depends on 7), in the
      existing commented style, noting the 8 MiB default and the documented 512 MB
      endpoint ceiling.
      — DoD: the variable name matches `config.py` exactly.

- [ ] 12. Run `uv sync --locked --group dev && uv run pytest -q` (depends on 1-11) and
      confirm `uv.lock` and `pyproject.toml` are untouched.
      — DoD: all tests green; `git status` shows no change to `uv.lock`,
      `pyproject.toml`, or `schemas/`.

## Tests

- [ ] T1. **Update** `tests/test_mcp_server.py::test_lists_exactly_the_documented_tools`
      to `{"newton_query", "newton_embed_timeseries", "newton_analyze_image"}`. This
      existing exact-set assertion fails otherwise. `test_tools_are_marked_read_only`
      needs no change and now covers the new tool.

- [ ] T2. Mock path, end to end through the server fixture: call `newton_analyze_image`
      with a small valid base64 PNG and a question. Assert `backend == "mock"`,
      `status == "completed"`, `outputs[0].startswith("[mock]")`, that the string contains
      "no image was analyzed", the decoded byte count and `image/png`, and that
      `mock_backend.requests[-1].file_ids` is the single mock-minted `file_id` ending
      `.png`.

- [ ] T3. API path via `httpx.MockTransport` (the `tests/test_api_backend.py` pattern),
      asserting the full two-call sequence and the documented request shapes:
      call 1 URL is `https://api.example/v0.5/files`, its `content-type` starts with
      `multipart/form-data`, its body contains the `.png` filename and the PNG bytes, and
      `authorization == "Bearer t"`; the handler returns
      `{"is_valid": true, "file_id": "img.png", "file_uid": "fil_abc"}`;
      call 2 URL is `https://api.example/v0.5/query` with a JSON body whose keys are
      exactly the documented set used — `model`, `query`, `system_prompt`,
      `instruction_prompt`, `file_ids`, `events`, `max_new_tokens`, `normalize_input`,
      `sanitize_response` — with `file_ids == ["img.png"]`, `events == []`, and **no**
      `mime_type` key and **no** `data.base64_img` event anywhere in the body.

- [ ] T4. `file_id` passthrough: calling with `file_id="existing.png"` and no
      `image_base64` performs **zero** upload calls and puts `["existing.png"]` in
      `file_ids`.

- [ ] T5. Invalid input, parametrized, each asserting `pytest.raises(ValueError)` **and**
      that the transport recorded zero requests: (a) neither source, (b) both sources,
      (c) `image_base64` without `mime_type`, (d) `mime_type="image/gif"`,
      (e) non-base64 garbage, (f) decoded payload one byte over a `Settings`
      constructed with a tiny `max_image_bytes`, (g) `upload=False` with `image_base64`
      — message mentions `docs/newton-api-notes.md`.

- [ ] T6. Upload failure surfaces as `NewtonApiError` and short-circuits: a 200 response
      with `{"is_valid": false}` and, separately, a 400 response, each raising
      `NewtonApiError` with **no** subsequent `/query` call recorded.

- [ ] T7. `tests/test_config.py` additions: `NEWTON_MAX_IMAGE_BYTES` parsed; default is
      `8 * 1024 * 1024` when unset; `ValueError` naming the variable for `"abc"`, `"0"`,
      `"-1"` and a value above 512 MB.

- [ ] T8. Header regression guard: an `ArchetypeNewtonBackend` built without an injected
      client has no `Content-Type` in `client.headers`, and a `files=`-built request from
      that client carries a `multipart/form-data` content-type with a boundary.

## Rollback

Every change is additive except two edits, so rollback is a clean revert of the single
PR — `git revert <merge-sha>` — with no data or state to unwind (no migrations, no
generated schema, no lockfile change, no released version bump).

The two non-additive edits and their revert consequences:
1. `tests/test_mcp_server.py::test_lists_exactly_the_documented_tools` returns to the
   two-name set, which is correct once the tool is gone.
2. Dropping `Content-Type: application/json` from the `httpx.AsyncClient` constructor
   reverts to the old header. This is the one edit worth keeping even if the image tool
   is abandoned, since it is a latent bug for any future multipart call; if the tool is
   reverted for behavioural reasons, re-apply this one-line fix separately.

Partial rollback without reverting the PR, if only the live API path misbehaves: set
`NEWTON_BACKEND=mock`, which routes `upload_image` to `MockNewtonBackend` and makes zero
network calls. If only the size limit is wrong, set `NEWTON_MAX_IMAGE_BYTES`; if only the
upload path is wrong, point `ATAI_API_ENDPOINT` elsewhere — neither needs a redeploy of
code. Removing the tool from a running deployment without a revert is not possible, as
tool registration is unconditional in `create_server`; that is deliberate, to avoid a
feature flag for a read-only tool.
