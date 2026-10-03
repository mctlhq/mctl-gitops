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
constructor yet; this change adds one, because its `event_data` shape is documented
(see below).

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

## Documentation review that shapes this design (amended at owner review)

| Thing | Documented? | Source |
|---|---|---|
| `events` accepts `data.base64_img`; payload shapes per Data Events | yes | `/api-reference/query` → links `/core-concepts/streams/events/data-events` |
| `data.base64_img` → `event_data.contents` (str, required, "the base64 encoded image as a byte string"), with example | **yes** | Data Events page (marked archived; current `/llms.txt` states its payload shapes are those Direct Query uses in `events`) |
| `file_ids`: pass the extension-bearing `file_id`, not `file_uid`; `/query` filters by extension; `.png/.jpg/.jpeg` contents injected into text-model context | yes | `/api-reference/query` |
| `POST /v0.5/files`, `multipart/form-data`, `-F "file=@…"`; response `is_valid`, `file_id`, `file_uid`; 512 MB; JPEG/PNG accepted | yes | `/api-reference/files/upload` |
| `POST /v0.5/files/base64`, multipart `file` holding base64 text | yes | `/api-reference/files/upload-base64` |
| `mime_type` as any API field | no | — gateway-side validation only |
| `data.json` `event_data` | arbitrary keys (`some_key: …`), no `contents` wrapper | Data Events page — differs from current `newton_query`; **not changed here**, flagged for #12 |

Consequence — the single most important design decision: **the analysis tool is
stateless.** Bytes go inline as `data.base64_img`; an existing file goes as `file_ids`.
The tool never uploads, so `read_only_hint=True` is truthful (an MCP annotation is static
for the whole tool; a tool that sometimes uploads would create organisation-scoped Files
state and could not be marked read-only). The documented multipart upload is still
implemented and tested, but as a backend capability for later tools, not reachable from
this tool.

## Proposed solution

### 1. `newton/models.py`

```python
IMAGE_MIME_EXTENSIONS: dict[str, str] = {"image/png": ".png", "image/jpeg": ".jpg"}
IMAGE_FILE_EXTENSIONS = (".png", ".jpg", ".jpeg")

class DataEvent(...):
    @classmethod
    def base64_img(cls, b64: str) -> "DataEvent":
        return cls(type="data.base64_img", event_data={"contents": b64})

class ImageUpload(BaseModel):
    data: bytes
    mime_type: Literal["image/png", "image/jpeg"]
    @property
    def filename(self) -> str:
        return f"image{IMAGE_MIME_EXTENSIONS[self.mime_type]}"

class UploadedFile(BaseModel):
    backend: Literal["mock", "api"]
    file_id: str
    file_uid: str | None = None
```

`NewtonQueryRequest` is untouched.

### 2. `newton/protocol.py`

Add `async def upload_image(self, image: ImageUpload) -> UploadedFile: ...` so both
backends expose the documented upload as a capability (one mock/real switch in
`build_backend`). No tool calls it in this change.

### 3. `newton/api.py`

- Client constructed with `headers={"Authorization": f"Bearer {api_key}"}` only — no
  client-level `Content-Type` (verified against the locked httpx: a client-level
  `Content-Type: application/json` overrides the multipart header a `files=` request would
  generate, dropping the boundary). `query()` keeps `json=`, so its header is unchanged.
- `upload_image`: `POST f"{self._endpoint}/files"` with
  `files={"file": (image.filename, image.data, image.mime_type)}`; non-200, falsy
  `is_valid` or missing `file_id` → `NewtonApiError`; returns
  `UploadedFile(backend="api", file_id=..., file_uid=...)`.

### 4. `config.py`

`max_image_bytes: int = 8 * 1024 * 1024` from `NEWTON_MAX_IMAGE_BYTES`, with
`DOCUMENTED_MAX_UPLOAD_BYTES = 512 * 1024 * 1024`; reject non-integer, `<= 0`, `> 512 MiB`,
naming the variable — existing `ValueError` style.

### 5. `server.py` — `newton_analyze_image`

Signature `(ctx, question, image_base64=None, mime_type=None, file_id=None,
system_prompt="", max_new_tokens=400, model=None)`, annotated
`ToolAnnotations(read_only_hint=True, open_world_hint=True)`. Description: exactly one of
`image_base64` (+ `mime_type`) or `file_id`; the tool never uploads or stores anything.

Order, every rejection pre-network:
1. `if (image_base64 is None) == (file_id is None): raise ValueError(...)`.
2. Inline branch: `mime_type` required and in `IMAGE_MIME_EXTENSIONS`; strip an optional
   `data:<mime>;base64,` prefix; `raw = base64.b64decode(payload, validate=True)` in
   `try/except (binascii.Error, ValueError)` re-raised without echoing the payload;
   `len(raw) > settings.max_image_bytes` → `ValueError` naming size, limit and variable;
   the normalized base64 sent on the wire is `base64.b64encode(raw).decode()` (canonical,
   prefix-free). Request:
   `events=[DataEvent.base64_img(b64)]`, `file_ids=[]`.
3. `file_id` branch: extension must be in `IMAGE_FILE_EXTENSIONS` (case-insensitive),
   else `ValueError` citing the documented `file_id`-vs-`file_uid` rule. Request:
   `file_ids=[file_id]`, `events=[]`.
4. `NewtonQueryRequest(model=model or settings.text_model, query=question,
   system_prompt=system_prompt, instruction_prompt=system_prompt, ..., 
   max_new_tokens=max_new_tokens)` (mirrors `newton_query`), one `backend.query(...)`,
   `return result.model_dump(exclude={"raw"})`.

### 6. `newton/mock.py`

- `upload_image`: mints `f"mock-image-{n:06d}{ext}"` (deterministic counter).
- `query()`, before the existing text branch: if the request carries a `data.base64_img`
  event → one output
  `"[mock] Newton is not connected and no image was analyzed. Received a data.base64_img event (<N> bytes decoded) and question=<q!r>. Set NEWTON_BACKEND=api with an authorized ATAI_API_KEY for real inference."`;
  else if any `file_ids` entry ends in an image extension → same shape naming the
  `file_id`. Otherwise the existing text branch unchanged. Never any scene description.

### 7. Docs

- `docs/newton-api-notes.md` (new): the table above with URLs; documented-but-unused
  `/query` fields; limits; the `data.json` discrepancy recorded as an open item for #12;
  the multipart part name `file` as from the cURL example; "not validated against a live
  account".
- `README.md`: tools-table row for `newton_analyze_image` (Newton C; one image inline as
  `data.base64_img` or an existing `file_id`; stateless); drop image analysis from
  "Planned"; keep mock-validated wording; link the notes file.
- `.env.example`: `NEWTON_MAX_IMAGE_BYTES`.

## Alternatives

1. **Upload inside the tool (first draft).** Dropped: makes the tool stateful while
   annotated read-only, and needlessly two calls; the inline path is documented.
2. **An `upload` flag on the tool.** Dropped for the same annotation reason — the
   annotation cannot depend on an argument.
3. **Image parameters on `newton_query`.** Dropped: turns a pass-through tool into one
   with mime/size validation; the issue asks for a named tool.
4. **A `newton_upload_file` tool now.** Out of scope; if added later it is a separate,
   non-read-only tool reusing `upload_image`.

## Platform impact

- No migration, schema or lockfile change; `newton_query` / `newton_embed_timeseries`
  unchanged. `tests/test_mcp_server.py::test_lists_exactly_the_documented_tools` exact set
  must be updated.
- Adding `upload_image` to the `runtime_checkable` Protocol is source-breaking for
  out-of-repo backends; both in-repo backends implement it; noted in the notes file.
- One HTTP call per image question; payload bounded by `NEWTON_MAX_IMAGE_BYTES` after
  the MCP host has already delivered the argument.
- Security: no credential change; errors never echo image bytes or base64.
