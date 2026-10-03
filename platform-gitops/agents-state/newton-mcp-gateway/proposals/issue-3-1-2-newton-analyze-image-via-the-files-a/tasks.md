# Tasks: issue-3-1-2-newton-analyze-image-via-the-files-a

> Amended at owner review: stateless tool (inline `data.base64_img` or existing
> `file_id`), no `upload` parameter, Files API upload kept as a backend capability only.

- [ ] 1. Re-verify the public docs before writing code and quote field names + URLs:
      `/api-reference/query` (`events`, `file_ids`), the Data Events page
      (`data.base64_img` → `event_data.contents`, `data.json` shape),
      `/api-reference/files/upload`, `/api-reference/files/upload-base64`, and
      `/llms.txt`'s statement about Data Events shapes in Direct Query `events`.
      — DoD: if any of these differs from `design.md`'s table, stop and flag it on the PR
      instead of implementing against the proposal.

- [ ] 2. Write `docs/newton-api-notes.md` (depends on 1) with the documented/source table,
      documented-but-unused `/query` fields, limits, the multipart part-name note, the
      `data.json` discrepancy as an open item for #12, and "not validated against a live
      account". — DoD: every field the implementation sends appears with a source URL.

- [ ] 3. `src/newton_mcp/newton/models.py` (depends on 2): `IMAGE_MIME_EXTENSIONS`,
      `IMAGE_FILE_EXTENSIONS`, `DataEvent.base64_img(b64)` constructor producing
      `{"type": "data.base64_img", "event_data": {"contents": b64}}`, `ImageUpload`,
      `UploadedFile`. — DoD: `NewtonQueryRequest.to_payload()` unchanged for existing callers.

- [ ] 4. `protocol.py`: add `upload_image`; export the new models from
      `newton/__init__.py` (depends on 3).

- [ ] 5. `api.py` (depends on 4): drop the client-level `Content-Type`; implement
      `upload_image` against `POST {endpoint}/files` (multipart part `file`), raising
      `NewtonApiError` on non-200 / falsy `is_valid` / missing `file_id`.
      — DoD: `tests/test_api_backend.py` still green unchanged.

- [ ] 6. `config.py`: `max_image_bytes` from `NEWTON_MAX_IMAGE_BYTES` (default 8 MiB,
      reject non-int, `<= 0`, `> 512 MiB`, naming the variable). — DoD: `Settings()` still works.

- [ ] 7. `mock.py` (depends on 3, 4): deterministic `upload_image`; image-aware `query()`
      branches for a `data.base64_img` event (decoded byte count) and for an image-extension
      `file_id`, both `[mock]` + "no image was analyzed"; other requests unchanged.

- [ ] 8. `server.py` (depends on 5-7): register `newton_analyze_image` exactly as in
      `design.md` §5 — no `upload` parameter, `read_only_hint=True`, all validation
      pre-network, one `/query` call, never any Files API call.

- [ ] 9. `README.md` tools row + "Planned" line + link to notes; `.env.example`
      `NEWTON_MAX_IMAGE_BYTES` (depends on 8). — DoD: status stays mock-validated.

- [ ] 10. `uv sync --locked --group dev && uv run pytest -q` — all green; `uv.lock`,
      `pyproject.toml`, `schemas/` untouched.

## Tests

- [ ] T1. Update `test_lists_exactly_the_documented_tools` to the three-tool set;
      `test_tools_are_marked_read_only` covers the new tool unchanged. Assert the
      `newton_analyze_image` input schema has **no** `upload` property.
- [ ] T2. Mock inline path via the server fixture: small valid PNG base64 → `backend ==
      "mock"`, output starts `[mock]`, contains "no image was analyzed" and the decoded
      byte count; the recorded request has one `data.base64_img` event and `file_ids == []`.
- [ ] T3. API inline path via `httpx.MockTransport`: exactly **one** request, to
      `…/v0.5/query`; JSON body `events == [{"type": "data.base64_img", "event_data":
      {"contents": <canonical b64>}}]`, `file_ids == []`, no `mime_type` key anywhere;
      a `data:image/png;base64,` prefixed input is sent without the prefix.
- [ ] T4. API `file_id` path: `file_id="scene.PNG"` → one `/query` request with
      `file_ids == ["scene.PNG"]`, `events == []`; zero requests to `/files`.
- [ ] T5. Invalid input, parametrized, each `ValueError` with zero recorded requests:
      neither/both sources; base64 without `mime_type`; `image/gif`; non-base64 garbage
      (message does not contain the payload); decoded size one byte over a tiny
      `max_image_bytes`; `file_id="fil_abc"` and `file_id="notes.csv"` (no image extension).
- [ ] T6. Backend capability `upload_image` (called directly, not via the tool):
      multipart request to `…/v0.5/files` with `content-type` starting
      `multipart/form-data` and a boundary, part `file` with filename `image.png`;
      `{"is_valid": true, "file_id": "img.png", "file_uid": "fil_x"}` → `UploadedFile`
      with `file_id == "img.png"`; `is_valid: false` and a 400 each raise `NewtonApiError`.
- [ ] T7. Header regression: a backend built without an injected client has no
      `Content-Type` in `client.headers`; `query()` still sends `application/json`.
- [ ] T8. Config: `NEWTON_MAX_IMAGE_BYTES` default, override, and `ValueError` naming the
      variable for `"abc"`, `"0"`, `"-1"`, and a value above 512 MiB.

## Rollback

Single-PR revert (`git revert <merge-sha>`); no state, schema, lockfile or release to
unwind. If only the live inline path misbehaves, `NEWTON_BACKEND=mock` makes zero network
calls. The `Content-Type` fix is worth keeping even if the tool is reverted.
