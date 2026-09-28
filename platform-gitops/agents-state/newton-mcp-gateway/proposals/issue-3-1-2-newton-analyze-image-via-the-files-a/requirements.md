# newton_analyze_image via the documented Files API

## Context

Issue #3 asks for a single MCP tool, `newton_analyze_image`, that puts an image in
front of Newton C. Today the gateway exposes only `newton_query` and
`newton_embed_timeseries` (`src/newton_mcp/server.py`). `newton_query` accepts a
`file_ids` list, so an image *can* reach the model, but only if the caller already
obtained a `file_id` somewhere outside this repo — the gateway has no upload path at
all (`src/newton_mcp/newton/api.py` speaks exactly one endpoint, `POST {endpoint}/query`).
That makes the documented image capability effectively unreachable through the gateway.

The issue frames two possible routes and then constrains them hard: ship only what the
public docs actually document, and record any gap in a new `docs/newton-api-notes.md`.
A doc review (docs.archetypeai.app, `/llms.txt`) shows an asymmetry that decides the
design: the **Files API upload route is fully documented** (`POST {ATAI_API_ENDPOINT}/files`,
`multipart/form-data`, response `{"is_valid", "file_id", "file_uid"}`, and the explicit
instruction to pass the extension-bearing `file_id` — not `file_uid` — in `file_ids`),
whereas the **inline `data.base64_img` route is only half documented**: the event type
string appears in the `events` enum of `POST /query`, but no page documents the keys
inside its `event_data`, and no example exists. `mime_type` appears nowhere as an API
field. Under hard rule 1 ("never invent parameters") the inline route therefore cannot
be shipped, and the tool implements the upload route only.

## User stories

- AS an MCP host agent I WANT to ask a natural-language question about a single image
  SO THAT I get Newton C's reading of a physical scene without having to learn
  Archetype's Files API myself.
- AS an agent that already uploaded a file I WANT to pass an existing `file_id`
  SO THAT I can re-question the same image without re-uploading it.
- AS a developer without credentials I WANT the mock backend to answer
  SO THAT I can wire the tool up end-to-end and still be unable to mistake its output
  for real inference.
- AS a reviewer of this repo I WANT every request field traceable to a public doc page
  SO THAT the gateway stays auditable and no endpoint or parameter is invented.
- AS an operator I WANT oversize images rejected before any network call
  SO THAT a large base64 blob cannot be paid for in bandwidth or provider quota.

## Acceptance criteria (EARS)

Tool surface

- WHEN an MCP client calls `tools/list` THE SYSTEM SHALL list exactly three tools:
  `newton_query`, `newton_embed_timeseries` and `newton_analyze_image`.
- WHEN `newton_analyze_image` is listed THE SYSTEM SHALL annotate it
  `read_only_hint=True` and `open_world_hint=True`.
- WHEN `newton_analyze_image` is listed THE SYSTEM SHALL expose the input schema
  `question` (required), `image_base64`, `mime_type`, `file_id`, `system_prompt`,
  `upload`, `max_new_tokens`, `model`.
- WHILE the tool description is rendered THE SYSTEM SHALL state that exactly one of
  `image_base64` or `file_id` must be supplied.

Input validation, all before any network call

- IF neither `image_base64` nor `file_id` is supplied THEN THE SYSTEM SHALL raise a
  `ValueError` naming both parameters and stating that exactly one is required.
- IF both `image_base64` and `file_id` are supplied THEN THE SYSTEM SHALL raise a
  `ValueError` naming both parameters and stating that exactly one is required.
- IF `image_base64` is supplied without `mime_type` THEN THE SYSTEM SHALL raise a
  `ValueError` requiring `mime_type`.
- IF `mime_type` is not one of the documented image types `image/png`, `image/jpeg`
  THEN THE SYSTEM SHALL raise a `ValueError` listing the accepted values.
- IF `image_base64` is not valid base64 THEN THE SYSTEM SHALL raise a `ValueError`
  saying the payload could not be decoded, without echoing the payload.
- IF the decoded image exceeds the configured maximum THEN THE SYSTEM SHALL raise a
  `ValueError` reporting the decoded byte count, the limit, and the variable
  `NEWTON_MAX_IMAGE_BYTES`, and SHALL NOT issue any HTTP request.
- WHILE any input validation error is raised THE SYSTEM SHALL have made zero HTTP
  requests.

Documented-only wire behaviour

- WHEN `image_base64` passes validation and the backend is `api` THE SYSTEM SHALL
  `POST` the decoded bytes to `{ATAI_API_ENDPOINT}/files` as `multipart/form-data`
  with a filename whose extension matches `mime_type` (`.png` for `image/png`,
  `.jpg` for `image/jpeg`).
- WHEN the upload response is read THE SYSTEM SHALL take the identifier from the
  documented `file_id` field and SHALL NOT use `file_uid` in `file_ids`.
- IF the upload response carries `is_valid: false` or a non-200 status THEN THE SYSTEM
  SHALL raise `NewtonApiError` and SHALL NOT issue the follow-up `/query` call.
- WHEN a `file_id` is available (uploaded or supplied) THE SYSTEM SHALL `POST` to
  `{ATAI_API_ENDPOINT}/query` a body whose fields are all documented, containing
  `model`, `query` (the `question`), `system_prompt`, `instruction_prompt`,
  `file_ids: [file_id]`, `max_new_tokens` and `sanitize_response: false`.
- WHILE building the `/query` body THE SYSTEM SHALL NOT emit a `data.base64_img` event
  and SHALL NOT send `mime_type` as an API field, because neither shape is documented.
- IF `upload=False` is combined with `image_base64` THEN THE SYSTEM SHALL raise a
  `ValueError` explaining that the inline `data.base64_img` `event_data` shape is not
  publicly documented and pointing at `docs/newton-api-notes.md`.
- WHEN the real backend's HTTP client is constructed THE SYSTEM SHALL NOT pin
  `Content-Type: application/json` at client level, so that the multipart upload
  carries its own generated `Content-Type` and boundary.

Result envelope

- WHEN a call succeeds THE SYSTEM SHALL return the `newton_query` envelope
  (`NewtonQueryResult` serialized with `raw` excluded): `backend`, `query_id`,
  `status`, `model`, `outputs`, `inference_time_sec`, `error`.
- WHEN no `model` is supplied THE SYSTEM SHALL use `Settings.text_model`, the Newton C
  family that the docs describe as handling image reasoning.

Mock backend

- WHEN the backend is `mock` THE SYSTEM SHALL return `backend: "mock"` and a single
  output string starting with `[mock]`.
- WHILE answering an image call THE SYSTEM SHALL state that no image was analyzed and
  SHALL echo only the decoded byte count, the `mime_type` and the question — never a
  description of image content.
- WHEN the mock handles an upload THE SYSTEM SHALL return a deterministic, obviously
  fake `file_id` whose extension matches `mime_type`.

Configuration and docs

- WHEN `NEWTON_MAX_IMAGE_BYTES` is set THE SYSTEM SHALL use it as the maximum decoded
  image size; otherwise THE SYSTEM SHALL default to 8 MiB.
- IF `NEWTON_MAX_IMAGE_BYTES` is not a positive integer, or exceeds the documented
  512 MB endpoint ceiling, THEN THE SYSTEM SHALL raise a `ValueError` at startup.
- WHEN this change lands THE SYSTEM SHALL ship `docs/newton-api-notes.md` recording,
  per field: the doc page it came from; that `data.base64_img`'s `event_data` keys are
  undocumented; that `mime_type` is gateway-side only; and the `/llms.txt` vs
  API-reference discrepancy over the upload path.
- WHEN this change lands THE README tools table SHALL list `newton_analyze_image`, and
  the "Planned" line SHALL no longer promise image analysis as future work.
- WHILE this change is unmerged and unvalidated against a live account THE SYSTEM SHALL
  keep describing the real adapter as mock-validated only.
- WHEN dependencies are resolved THE SYSTEM SHALL add no new runtime dependency
  (`httpx`, `pydantic`, `mcp` only) and `uv.lock` SHALL be unchanged.

## Out of scope

- Video input, `max_frames`, and multi-image input (`multi_image`).
- Batching more than one image per call.
- A generic file-management tool: listing (`GET /files/metadata`), storage stats
  (`GET /files/info`), download, or deletion (`DELETE /files/{file_id}`).
- Resumable / direct-to-cloud upload for files above the documented 512 MB limit, and
  the `POST /files/upload-base64` variant named only in the `/llms.txt` index.
- The inline `data.base64_img` route, until its `event_data` keys are publicly documented.
- New runtime dependencies, image decoding or re-encoding (no Pillow), thumbnailing,
  EXIF stripping.
- Any change to the action runtime, the Physical Action Contract, or `newton_embed_timeseries`.
- Validating the adapter against a live Archetype account.

## Open questions

- **The `upload` flag's meaning.** The issue asks for an "optional `upload` flag",
  which implies a second, non-upload route for inline bytes. That route is the
  undocumented `data.base64_img` event. Interpretation taken: `upload` defaults to
  `True`, and `upload=False` with `image_base64` fails fast with a pointer to
  `docs/newton-api-notes.md` rather than guessing `event_data` keys. The flag is kept
  in the schema so the inline route can be switched on unchanged the day Archetype
  documents it. A reviewer may prefer dropping the flag entirely until then.
- **Upload path.** `/llms.txt` indexes `POST /files/upload` and
  `POST /files/upload-base64`; the Files API reference page documents `POST /v0.5/files`.
  Interpretation taken: the API reference wins, so the gateway posts to
  `{ATAI_API_ENDPOINT}/files` (the configured endpoint already ends in `/v0.5`). Only a
  live credentialed run can settle this; recorded in `docs/newton-api-notes.md`.
- **Multipart field name.** The docs show a cURL example but do not name the form field
  normatively. Interpretation taken: send one part whose filename carries the correct
  extension, since the docs say `/query` type-filters on the `file_id` extension.
  Recorded as unverified.
- **`read_only_hint` on a tool that uploads.** The issue mandates
  `read_only_hint=True`, and the tool does not modify the caller's environment, but an
  upload does create server-side state on Archetype's side. Following the issue;
  noting the nuance in `docs/newton-api-notes.md`.
- **Default size limit.** 8 MiB decoded is chosen as a safe MCP-transport default,
  far under the documented 512 MB endpoint ceiling, because the base64 form travels
  inside a JSON tool-call argument. Not derived from any doc.
- **Whether to expose `file_uid`.** The upload response carries it; the result envelope
  is specified as `NewtonQueryResult` minus `raw`, which has no place for it. Dropped.
