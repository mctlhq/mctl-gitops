# Design: issue-3-1-2-newton-analyze-image-via-the-files-a

## Current state

**One endpoint, one seam.** `src/newton_mcp/newton/protocol.py` defines the whole
boundary between this gateway and Archetype as a two-method `runtime_checkable`
Protocol:

```python
class NewtonBackend(Protocol):
    name: str
    async def query(self, request: NewtonQueryRequest) -> NewtonQueryResult: ...
    async def aclose(self) -> None: ...
```

Two implementations satisfy it: `MockNewtonBackend` (`newton/mock.py`) and
`ArchetypeNewtonBackend` (`newton/api.py`). `build_backend(settings)` at the bottom of
`api.py` picks between them from `Settings.backend`. There is no file upload anywhere in
the repo: `ArchetypeNewtonBackend.query` performs exactly one call,
`POST f"{self._endpoint}/query"`, and nothing else.

**Request/response models mirror the docs field-for-field.**
`newton/models.py` holds `EventType` (a `Literal` that already includes
`"data.base64_img"` and `"data.base64_img_array"`), `DataEvent` with `text()` and
`numeric_array()` constructors, `NewtonQueryRequest` (`model`, `query`, `system_prompt`,
`instruction_prompt`, `file_ids`, `events`, `max_new_tokens`, `normalize_input`) whose
`to_payload()` forces `sanitize_response = False`, and `NewtonQueryResult`
(`backend`, `query_id`, `status`, `model`, `outputs`, `inference_time_sec`, `error`,
`raw`). Note that `data.base64_img` is already in the type enum but has **no**
constructor — the repo has so far declined to guess its `event_data` shape.

**The server exposes two tools.** `src/newton_mcp/server.py` builds an `MCPServer`
(`mcp>=2`; FastMCP was renamed), registers `newton_query` and
`newton_embed_timeseries`, both annotated `ToolAnnotations(read_only_hint=True,
open_world_hint=True)`, and both return `result.model_dump(exclude={"raw"})`.
`newton_query` sets `instruction_prompt=system_prompt` (the same string in both fields)
and defaults `max_new_tokens=400`. `AppState` carries `settings` and `backend`;
`_state(ctx)` reads it off `ctx.request_context.lifespan_context`.

**Config is a frozen dataclass, not BaseSettings.** `src/newton_mcp/config.py`
`Settings.from_env()` validates each variable and raises `ValueError` with the offending
variable named. Relevant defaults: `text_model="Newton::c2_5_8b_260413b723a9ab"`,
`api_endpoint="https://api.u1.archetypeai.app/v0.5"` (note: the version is part of the
endpoint), `request_timeout_sec=90.0`.

**Mock labelling is load-bearing.** `MockNewtonBackend.query` branches on
`request.model.startswith("OmegaEncoder::")`; the text branch emits
`f"[mock] Newton is not connected. Received query={...!r}, events={n}, file_ids={n}. ..."`.
It keeps `self.requests` so tests can assert what was built.

**Tests to be aware of.** `tests/test_mcp_server.py::test_lists_exactly_the_documented_tools`
asserts `names == {"newton_query", "newton_embed_timeseries"}` — an exact-set assertion
that **will fail** and must be updated. `test_tools_are_marked_read_only` loops over all
tools and will cover the new one for free. `tests/test_api_backend.py` drives the real
adapter through `httpx.MockTransport`, which is the established pattern for the new
upload test. `tests/conftest.py` provides `mock_backend` and `server` fixtures.
`pyproject.toml` sets `asyncio_mode = "auto"`, so tests are plain `async def`.

**A latent blocker found in the existing adapter.** `ArchetypeNewtonBackend.__init__`
constructs the shared client with
`headers={"Authorization": ..., "Content-Type": "application/json"}`. httpx applies
content-type headers generated from `files=` with `setdefault`, so a client-level
`Content-Type` wins. Verified against the locked httpx 0.28.1:
`Client(headers={"Content-Type": "application/json"}).build_request("POST", url, files=...)`
produces `content-type: application/json` with **no multipart boundary**. A multipart
upload on this client would silently be sent with the wrong content type.

## Documentation review that shapes this design

Read on docs.archetypeai.app and `/llms.txt` before designing:

| Thing | Documented? |
|---|---|
| `POST {ATAI_API_ENDPOINT}/files`, `multipart/form-data`, `Authorization: Bearer` | yes (Files API reference) |
| Upload response `{"is_valid", "file_id", "file_uid"}` | yes |
| Pass the extension-bearing `file_id` (not `file_uid`) in `file_ids`; `/query` filters file types by extension | yes, explicitly |
| Limits: 512 MB; JPEG, PNG, MP4, text, CSV, JSON accepted | yes |
| `data.base64_img` as an `events` type string | yes (enum only) |
| The keys inside `data.base64_img`'s `event_data` | **no** — no example, no field list |
| `mime_type` as any API field | **no** — appears nowhere |
| Upload path spelling | **conflicting**: `/llms.txt` indexes `POST /files/upload` + `/files/upload-base64`; the reference documents `POST /v0.5/files` |

Consequence, and the single most important design decision: **only the Files API route
is implemented.** Sending `{"type": "data.base64_img", "event_data": {"contents": ...}}`
would be inventing a parameter name, which hard rule 1 forbids, however plausible the
`contents` convention looks next to `data.json`. The `upload` flag stays in the tool
schema but `upload=False` with inline bytes is a fast, explanatory failure rather than a
guess.

## Proposed solution

Five small, additive edits plus one bug fix. No new module, no new dependency.

### 1. `newton/models.py` — two new Pydantic v2 models

```python
IMAGE_MIME_EXTENSIONS: dict[str, str] = {"image/png": ".png", "image/jpeg": ".jpg"}

class ImageUpload(BaseModel):
    data: bytes
    mime_type: Literal["image/png", "image/jpeg"]

    @property
    def filename(self) -> str:      # extension matters: /query type-filters on file_id
        return f"image{IMAGE_MIME_EXTENSIONS[self.mime_type]}"

class UploadedFile(BaseModel):
    backend: Literal["mock", "api"]
    file_id: str                    # the documented, extension-bearing identifier
    file_uid: str | None = None     # documented but deliberately unused downstream
    is_valid: bool = True
```

`NewtonQueryRequest` is untouched — every field the image path needs already exists.
No `DataEvent.base64_img()` constructor is added; its absence is the design.

### 2. `newton/protocol.py` — extend the seam by one method

```python
async def upload_image(self, image: ImageUpload) -> UploadedFile: ...
```

Putting the upload on the existing backend Protocol, rather than in a separate
`FilesClient`, keeps one mock/real switch (`build_backend`) and lets the mock stay
self-consistent: it can mint a `file_id` and then recognise it in a later `query`.

### 3. `newton/api.py` — the documented upload, and the header fix

```python
self._client = client or httpx.AsyncClient(
    headers={"Authorization": f"Bearer {api_key}"},   # no client-level Content-Type
    timeout=timeout_sec,
)
```

`query()` already passes `json=`, which sets `application/json` per request, so nothing
is lost. Then:

```python
async def upload_image(self, image: ImageUpload) -> UploadedFile:
    resp = await self._client.post(
        f"{self._endpoint}/files",
        files={"file": (image.filename, image.data, image.mime_type)},
    )
    body = self._json(resp)
    if resp.status_code != 200:
        raise NewtonApiError(resp.status_code, body.get("errors", body.get("detail", body)))
    if not body.get("is_valid", False) or not body.get("file_id"):
        raise NewtonApiError(resp.status_code, body.get("errors", body))
    return UploadedFile(backend="api", file_id=str(body["file_id"]),
                        file_uid=body.get("file_uid"))
```

Reuses the existing `_json` helper and `NewtonApiError`. No retry logic, no new
timeout knob.

### 4. `config.py` — one new setting

`max_image_bytes: int = 8 * 1024 * 1024`, read from `NEWTON_MAX_IMAGE_BYTES` in
`from_env()`, in the same style as the existing validators: reject non-integer, reject
`<= 0`, reject `> DOCUMENTED_MAX_UPLOAD_BYTES` (512 * 1024 * 1024), and name the
variable in the message. 8 MiB is a transport-shaped default, not a documented one: the
base64 form arrives inside a JSON tool-call argument.

### 5. `server.py` — the `newton_analyze_image` tool

```python
@server.tool(
    name="newton_analyze_image",
    description=(
        "Ask Newton C a question about one image. Supply exactly one of image_base64 "
        "(with mime_type) or file_id from a previous upload. The image is uploaded "
        "through Archetype's documented Files API and passed to /query as a file_id."
    ),
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def newton_analyze_image(
    ctx: Context,
    question: str,
    image_base64: str | None = None,
    mime_type: str | None = None,
    file_id: str | None = None,
    system_prompt: str = "",
    upload: bool = True,
    max_new_tokens: int = 400,
    model: str | None = None,
) -> dict[str, Any]:
```

Body, in strict order so that every rejection is pre-network:

1. `if (image_base64 is None) == (file_id is None): raise ValueError(...)` — the
   exactly-one rule, enforced in one expression.
2. Inline branch: require `mime_type`; check it against `IMAGE_MIME_EXTENSIONS`; strip an
   optional `data:<mime>;base64,` prefix; `base64.b64decode(payload, validate=True)`
   inside `try/except (binascii.Error, ValueError)` re-raised as a `ValueError` that does
   not echo the payload; then
   `if len(raw) > state.settings.max_image_bytes: raise ValueError(...)` naming the
   decoded size, the limit and `NEWTON_MAX_IMAGE_BYTES`.
3. `if not upload: raise ValueError("inline data.base64_img is not implemented: its "
   "event_data fields are not publicly documented - see docs/newton-api-notes.md")`.
4. `uploaded = await state.backend.upload_image(ImageUpload(data=raw, mime_type=mime_type))`;
   `resolved_id = uploaded.file_id`. In the `file_id` branch, `resolved_id = file_id`
   and no upload happens at all.
5. Build `NewtonQueryRequest(model=model or state.settings.text_model, query=question,
   system_prompt=system_prompt, instruction_prompt=system_prompt,
   file_ids=[resolved_id], max_new_tokens=max_new_tokens)` — mirroring `newton_query`'s
   duplication of `system_prompt` into `instruction_prompt`.
6. `return (await state.backend.query(request)).model_dump(exclude={"raw"})`.

The exactly-one constraint is expressed to MCP clients by making both parameters
`| None = None` plus the description; the runtime `ValueError` is the enforcement. A
Pydantic discriminated union in the signature would be stricter but the `mcp>=2`
`@server.tool` decorator derives the schema from the annotations, and a flat signature
keeps the tool callable from hosts that flatten arguments.

### 6. `newton/mock.py` — image-aware, still unmistakably fake

```python
async def upload_image(self, image: ImageUpload) -> UploadedFile:
    ext = IMAGE_MIME_EXTENSIONS[image.mime_type]
    file_id = f"mock-image-{next(self._counter):06d}{ext}"
    self._uploads[file_id] = image          # new dict, alongside self.requests
    return UploadedFile(backend="mock", file_id=file_id)
```

and in `query()`, before the existing text branch, a check for any `request.file_ids`
entry present in `self._uploads`:

```
"[mock] Newton is not connected and no image was analyzed. "
"Received file_id='mock-image-000001.png' (mime_type='image/png', 20614 bytes) "
"and question='what is on the bench?'. "
"Set NEWTON_BACKEND=api with an authorized ATAI_API_KEY for real inference."
```

Byte count and mime type only — no scene description, no object list, nothing that could
be mistaken for having looked at pixels. A `file_id` the mock did not mint falls through
to the existing text branch unchanged.

### 7. Docs

- **`docs/newton-api-notes.md` (new)** — the traceability ledger the issue requires: the
  table above, verbatim-quoted field names with the page each came from, the three
  recorded gaps (`data.base64_img` `event_data` keys, `mime_type` absent as an API field,
  the `/llms.txt` vs reference path discrepancy), the documented-but-deliberately-unused
  `/query` fields (`multi_image`, `max_frames`, `temperature`, `top_p`, `top_k`,
  `do_sample`, `repetition_penalty`, `presence_penalty`, `response_start_prompt`,
  `template_name`, `query_metadata`, `render`, `max_query_size_mb`, `max_wait_time_sec`),
  the `read_only_hint`-on-an-upload nuance, and a standing note that none of it has been
  run against a live account.
- **`README.md`** — add the `newton_analyze_image` row to the tools table; drop "image
  analysis via the Files API" from the "Planned" line; keep the mock-validated status
  wording untouched.
- **`.env.example`** — document `NEWTON_MAX_IMAGE_BYTES`.

## Alternatives

1. **Inline `data.base64_img` with a guessed `event_data.contents` key.** The fastest
   path, one HTTP call instead of two, no server-side state, and `contents` is what
   `data.json` and `data.numeric_array` use. Dropped: the key is not documented for this
   event type and `mime_type` is not documented at all, so shipping it would invent
   parameters — the exact thing hard rule 1 and the issue's "if the docs do not document
   a field, do not implement it" forbid. A guess that happens to be right is still a
   guess, and it would be indistinguishable in review from one that is wrong.
2. **Add image parameters to `newton_query` instead of a new tool.** Keeps the tool count
   at two, which matches the repo's "few tools" rule. Dropped: the issue asks for a named
   tool; more importantly `newton_query` would then need conditional size validation, a
   mime whitelist and an upload side effect on a path that today is a pure pass-through,
   making a well-scoped read tool substantially harder to reason about.
3. **A separate `FilesClient` class (or a `newton/files.py` module) instead of a method on
   `NewtonBackend`.** Cleaner single-responsibility split, and it avoids widening a
   `runtime_checkable` Protocol. Dropped: it creates a *second* mock/real switch that
   `build_backend` does not own, and the mock could no longer correlate the `file_id` it
   minted with the later `query`, which is exactly what makes the honest
   "no image was analyzed" mock message possible.
4. **A generic `newton_upload_file` tool plus plain `newton_query`.** Most composable,
   and it maps one-to-one onto the documented endpoint. Dropped: explicitly out of scope
   in the issue, and a write-capable file tool cannot honestly carry `read_only_hint`.

## Platform impact

**Migrations.** None. No database, no schema file. `schemas/physical-action-contract.schema.json`
is untouched, so the sync test in `tests/test_action_contract.py` is unaffected.

**Backward compatibility.**
- `newton_query` and `newton_embed_timeseries` keep identical signatures and behaviour.
- Removing `Content-Type: application/json` from the client constructor is behaviour-
  preserving for `query()`, which uses `json=` and therefore sets the header per request.
  `tests/test_api_backend.py` injects its own client and asserts only the URL and
  `Authorization`, so it stays green.
- Adding `upload_image` to the `runtime_checkable` `NewtonBackend` Protocol is a
  source-breaking change for any out-of-repo implementation, and `isinstance` checks
  against it would newly fail for a backend lacking the method. Both in-repo
  implementations are updated in this change, and `NewtonBackend` is re-exported from
  `newton/__init__.py`, so the break is worth one line in the notes file. Version stays
  `0.1.0`; nothing here is released.
- `Settings` gains a field with a default, so `Settings()` calls in `tests/conftest.py`
  keep working unchanged.

**Resource impact.** Two HTTP calls instead of one on the inline path, on the existing
90 s client timeout — an image upload plus inference can plausibly approach it, which is
worth watching on the first live run. Peak memory is roughly the base64 string plus its
decoded bytes (about 2.3x the image), bounded by `NEWTON_MAX_IMAGE_BYTES` (8 MiB default)
— but bounded only *after* the base64 string has already been received in the tool call,
so the transport-level ceiling of the MCP host still applies upstream of us. No new
dependency, so `uv.lock` is unchanged and CI's `uv sync --locked` stays green.

**Risks and mitigations.**

| Risk | Mitigation |
|---|---|
| The upload path is wrong (`/files` vs `/files/upload`) and every live upload 404s | Recorded as an open question in `docs/newton-api-notes.md`; the endpoint is one `f`-string in `upload_image`; `ATAI_API_ENDPOINT` already lets an operator redirect the base |
| The multipart form field name is not what the server expects | Documented as unverified; the filename carries the extension the docs say `/query` filters on, which is the part the docs are explicit about |
| The client-level `Content-Type` bug silently corrupts the upload | Fixed in this change and pinned by a test asserting the request's content-type starts with `multipart/form-data` |
| `file_uid` accidentally used in `file_ids` (the docs say it is rejected) | `UploadedFile.file_uid` is captured but never read downstream; a test asserts the `/query` body carries the `file_id` |
| The mock drifts into sounding like real vision output | The mock echoes only byte count and mime type; a test asserts the output starts with `[mock]`, contains "no image was analyzed", and contains the byte count |
| A caller sends a 200 MB base64 blob | Decoded-size check before any network call, with the limit and variable named in the error |
| Someone later reads the `data.base64_img` entry in `EventType` as an invitation to implement it | `docs/newton-api-notes.md` states the gap explicitly, and the `upload=False` error message points there |
| The new tool is mistaken for live-validated | README status block and `docs/newton-api-notes.md` keep saying mock-validated until a credentialed run happens |

**Security.** No credential handling changes; the API key stays in the one
`Authorization` header. Error messages never echo image bytes or the base64 payload. The
upload creates state in the caller's Archetype account that this gateway offers no way to
delete (`DELETE /files/{file_id}` is out of scope) — called out in the notes file.
