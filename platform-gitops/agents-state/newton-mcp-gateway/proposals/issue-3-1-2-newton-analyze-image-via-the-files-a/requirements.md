# newton_analyze_image — stateless image questions over documented /query inputs

> **Amended at owner review (before approval).** The first draft concluded that the
> `data.base64_img` event's `event_data` keys are undocumented and therefore shipped only
> an upload-through-the-Files-API path, with an `upload` flag whose `false` value failed.
> That doc review was incomplete: the Data Events page linked from the `/query` `events`
> parameter documents `data.base64_img` with a required `event_data.contents` string (the
> base64-encoded image), with an example, and the current `/llms.txt` states those payload
> shapes are the ones Direct Query uses in `events`. `POST /v0.5/files/base64` also has its
> own API-reference page. The tool is therefore redesigned to be **stateless**: inline
> images go in `events` as `data.base64_img`; existing files go in `file_ids`. The tool
> never uploads, so it is honestly `read_only_hint=True`. The documented Files API upload
> is kept as a tested **backend capability** (not exposed as a tool).

## Context

Issue #3 asks for one MCP tool, `newton_analyze_image`, that puts an image in front of
Newton C. Today the gateway exposes `newton_query` and `newton_embed_timeseries`
(`src/newton_mcp/server.py`); an image can reach the model only as a `file_id` obtained
outside the gateway. Two documented `/query` inputs carry an image:

- `events: [{"type": "data.base64_img", "event_data": {"contents": "<base64>"}}]` —
  documented on the Data Events page (`/core-concepts/streams/events/data-events`), which
  the `/query` reference links for the event payload shapes. One call, no server-side state.
- `file_ids: ["<file_id>"]` — documented on the `/query` reference, with the explicit rule
  to pass the extension-bearing `file_id` (not the `file_uid`), because `/query` filters
  file types by the extension, and that `.png` / `.jpg` / `.jpeg` contents are injected into
  the Newton text model's context.

Uploading (`POST /v0.5/files`, multipart, field `file`; response `is_valid`, `file_id`,
`file_uid`; 512 MB; JPEG/PNG among accepted types) creates organisation-scoped state. An
MCP tool's `read_only_hint` is static for the whole tool, so a tool that may upload cannot
honestly be read-only. Hence: the analysis tool never uploads.

## User stories

- AS an MCP host agent I WANT to ask a question about one image I hold as bytes
  SO THAT I get Newton C's reading of a scene in one stateless call.
- AS an agent whose image is already in the Archetype Files storage I WANT to pass its
  `file_id` SO THAT I can question it without re-sending bytes.
- AS a developer without credentials I WANT the mock backend to answer
  SO THAT I can wire the tool end to end and still never mistake its output for inference.
- AS a reviewer I WANT every request field traceable to a public doc page
  SO THAT no endpoint or parameter is invented.
- AS an operator I WANT oversize images rejected before any network call.

## Acceptance criteria (EARS)

Tool surface

- WHEN an MCP client calls `tools/list` THE SYSTEM SHALL list exactly `newton_query`,
  `newton_embed_timeseries` and `newton_analyze_image`.
- WHEN `newton_analyze_image` is listed THE SYSTEM SHALL annotate it
  `read_only_hint=True`, `open_world_hint=True`, and its input schema SHALL be `question`
  (required), `image_base64`, `mime_type`, `file_id`, `system_prompt`, `max_new_tokens`,
  `model` — and SHALL NOT contain an `upload` parameter.
- WHILE the tool description is rendered THE SYSTEM SHALL state that exactly one of
  `image_base64` (with `mime_type`) or `file_id` is required, and that the tool never
  uploads or stores anything.

Input validation, all before any network call

- IF neither or both of `image_base64` and `file_id` are supplied THEN THE SYSTEM SHALL
  raise `ValueError` naming both parameters and stating exactly one is required.
- IF `image_base64` is supplied without `mime_type`, or `mime_type` is not `image/png` or
  `image/jpeg`, THEN THE SYSTEM SHALL raise `ValueError` listing the accepted values.
- IF `image_base64` (after stripping an optional `data:<mime>;base64,` prefix) is not valid
  base64 THEN THE SYSTEM SHALL raise `ValueError` without echoing the payload.
- IF the decoded image exceeds `Settings.max_image_bytes` THEN THE SYSTEM SHALL raise
  `ValueError` naming the decoded size, the limit and `NEWTON_MAX_IMAGE_BYTES`.
- IF `file_id` has no `.png`, `.jpg` or `.jpeg` extension (case-insensitive) THEN THE
  SYSTEM SHALL raise `ValueError` citing the documented rule that `/query` filters by the
  `file_id` extension and rejects a `file_uid`.
- WHILE any validation error is raised THE SYSTEM SHALL have made zero HTTP requests.

Wire behaviour (documented fields only)

- WHEN `image_base64` passes validation THE SYSTEM SHALL make exactly one HTTP call,
  `POST {ATAI_API_ENDPOINT}/query`, whose body carries
  `events == [{"type": "data.base64_img", "event_data": {"contents": <normalized base64>}}]`,
  `file_ids == []`, `query` = the question, `system_prompt`, `instruction_prompt`,
  `model`, `max_new_tokens`, and `sanitize_response: false`.
- WHEN `file_id` is supplied THE SYSTEM SHALL make exactly one HTTP call to `/query` with
  `file_ids == [file_id]` and `events == []`.
- WHILE building any request THE SYSTEM SHALL NOT send `mime_type` (gateway-side
  validation only) and SHALL NOT call any Files API endpoint.
- WHEN the real backend's HTTP client is constructed THE SYSTEM SHALL NOT pin a
  client-level `Content-Type`, so a multipart request built from it carries its own
  generated `multipart/form-data; boundary=…` (latent bug found in review; `query()` keeps
  sending `application/json` per request via `json=`).

Files API capability (backend only, not a tool)

- WHEN `ArchetypeNewtonBackend.upload_image(ImageUpload)` is called THE SYSTEM SHALL
  `POST {ATAI_API_ENDPOINT}/files` as `multipart/form-data` with one part named `file`
  whose filename carries the mime-matching extension, and SHALL return an `UploadedFile`
  built from the documented `file_id` (keeping `file_uid` only as data).
- IF the upload answers non-200, `is_valid` falsy or no `file_id` THEN THE SYSTEM SHALL
  raise `NewtonApiError`.
- WHILE this capability exists THE SYSTEM SHALL NOT invoke it from any MCP tool in this change.

Result envelope and model

- WHEN a call succeeds THE SYSTEM SHALL return the `newton_query` envelope
  (`NewtonQueryResult` without `raw`). WHEN no `model` is given THE SYSTEM SHALL use
  `Settings.text_model`.

Mock backend

- WHEN the backend is `mock` THE SYSTEM SHALL return `backend: "mock"` and one output
  starting `[mock]` that states no image was analyzed and echoes only the input kind
  (`data.base64_img` event with its decoded byte count, or the `file_id`) and the question —
  never any description of image content.
- WHEN the mock's `upload_image` is called THE SYSTEM SHALL return a deterministic,
  obviously fake `file_id` with the mime-matching extension.

Configuration and docs

- `NEWTON_MAX_IMAGE_BYTES` sets the decoded-size limit (default 8 MiB); a non-integer,
  `<= 0` or `> 512 MiB` value raises `ValueError` naming the variable.
- `docs/newton-api-notes.md` (new) records, with source URLs: `data.base64_img` →
  `event_data.contents` (Data Events page, linked from `/query`; page marked archived but
  `/llms.txt` states its shapes are used by Direct Query `events`); `file_ids` rules;
  `POST /v0.5/files` and `POST /v0.5/files/base64` as the two documented upload endpoints
  (the backend uses the multipart `/files` one); `mime_type` as gateway-side only; the
  not-live-validated status; and — as an open item for the live-validation issue #12, not
  changed here — that the docs show `data.json` `event_data` with arbitrary keys, while
  `newton_query` currently wraps JSON as `{"contents": …}`.
- README tools table lists `newton_analyze_image`; the "Planned" line no longer promises
  image analysis; the adapter stays described as mock-validated.
- No new runtime dependency; `uv.lock` unchanged.

## Out of scope

- An upload tool, or any MCP tool that uploads, lists, downloads or deletes files.
- `data.base64_img_array`, video, `max_frames`, multi-image, batching.
- Changing `newton_query`'s `data.json` encoding (tracked for #12).
- Image decoding/re-encoding (no Pillow), EXIF stripping.
- Validating against a live Archetype account.

## Open questions

- Default 8 MiB is transport-shaped (base64 arrives inside a JSON tool argument), not
  documented. Kept.
- The multipart part name `file` comes from the documented cURL example (`-F "file=@…"`);
  unverified against a live account, noted in `docs/newton-api-notes.md`.
