# Tasks: issue-28-runtime-authenticated-streamable-http-tr

- [ ] 1. Add the `HttpAuth` model and the `auth` field to `HttpTransport` in
  `src/newton_mcp/runtime/config.py`, with `AuthConfigError(Exception)` and a
  `model_validator(mode="before")` on `HttpTransport` that screens the raw `auth` mapping:
  reject any key outside `{header, scheme, env}` without echoing arbitrary key names,
  accept `auth: null` as omitted auth, reject other non-mapping `auth`, validate
  `header` against the RFC 9110 token regex, reject `_SDK_MANAGED_HEADERS`
  (`content-type`, `accept`, `mcp-session-id`, `mcp-protocol-version`, case-insensitive),
  validate `scheme` as a single token when present, and validate `env` against
  `^[A-Za-z_][A-Za-z0-9_]*$`.
  — DoD: `AuthConfigError` subclasses `Exception` and **not** `ValueError`, so pydantic-core
  propagates it instead of wrapping it in a `ValidationError` that would echo `input_value`;
  no message emitted by this validator contains unvalidated data; stdio auth is rejected
  by the safe raw-input screen before `extra="forbid"` can echo its value;
  `uv run pytest` is green with no changes to existing tests.

- [ ] 2. Extend `ServerConfig.transport_fingerprint` (depends on 1) so the canonical dict for
  `streamable-http` gains `"auth": {"header": ..., "scheme": ..., "env": ...}` **only when**
  `transport.auth is not None`, and update the property's docstring.
  — DoD: for a server with no `auth`, the digest is byte-identical to the pre-change value
  (pinned by an explicit regression test); no `os.environ` access anywhere in
  `transport_fingerprint` or `binding_identity`; changing `env`/`header`/`scheme` changes the
  digest.

- [ ] 3. Add `src/newton_mcp/runtime/auth.py` (depends on 1) with `MissingAuthSecret(Exception)`,
  `resolve_auth_header(auth, *, server_name, env=None) -> tuple[str, str]` (injectable env
  mapping, `f"{scheme} {value}"` when `scheme` is set, raw value otherwise, blankness checked with `.strip()` but nonblank credentials preserved byte-exact; reject
  control characters and unencodable values with fixed safe errors), and `redact(text, secrets) -> str` reusing
  `newton_mcp.runtime.audit.REDACTED`.
  — DoD: a missing or blank variable raises `MissingAuthSecret` whose message names
  `auth.env` and the server but contains no value; `redact()` is a no-op for an empty or
  blank secret (never turns a whole string into `[redacted]`); the module imports nothing from
  `catalog.py`/`executor.py`, so no import cycle.

- [ ] 4. Rework `default_client_factory()` in `src/newton_mcp/runtime/catalog.py` (depends on
  2, 3): add the keyword-only `http_client_builder: HttpClientBuilder = _default_http_client_builder`
  parameter, keep `Client(transport.url)` verbatim for `HttpTransport` with `auth is None`,
  and for the auth case return an `@asynccontextmanager` wrapper that owns the
  `httpx2.AsyncClient` (`async with builder(headers) as hc: async with
  Client(streamable_http_client(url, http_client=hc)) as client: yield client`).
  — DoD: `default_client_factory` still satisfies `ClientFactory = Callable[[ServerConfig], ...]`
  so `CapabilityCatalog`, `Executor` (`executor.py:95`) and `Verifier` (`verifier.py:95`) need
  no change; the `httpx2.AsyncClient` is closed on both the success and the exception path
  (the SDK does not close a caller-supplied client); `httpx2` is imported under
  `TYPE_CHECKING` for annotations and `create_mcp_http_client` is imported inside the default
  builder; the stdio branch is untouched.

- [ ] 5. Implement connection-bound safe authenticated transport errors (depends on 3, 4).
  Cover builder/connect/list/call/close and nested exception groups; expose fixed messages or
  exception class names, not raw provider text. Keep missing-variable diagnostics useful.
  — DoD: no secret in `str`/`repr`/traceback/chaining/logs/catalog/audit/outcome; sanitize before
  truncation, never re-read env for redaction; cancellation and caller-body exceptions keep
  their semantics. Preserve executor/verifier safety behavior.

- [ ] 6. Update `docs/action-runtime.md` (depends on 2, 4): add `auth` to the `runtime.yaml`
  example block; extend the `streamable-http` bullet in "Server identity in an approval
  binding" to state that the digest covers `header`, `scheme` and the env-var *name* and never
  the value, and that rotating the value keeps approvals valid while re-pointing `env:`
  invalidates them; add an "Authenticated streamable-http" subsection covering connect-time
  resolution, the loud failure on a missing variable, the explicit non-goal of an OAuth flow,
  and a **mock-validated** label; mention the extra `export` in "Adding an MCP actuator by
  configuration only".
  — DoD: the example variable name is operator-namespaced (`ALICE_MCP_TOKEN`), i.e. outside the
  `NEWTON_*`/`ATAI_*` prefixes that `tests/test_docs_consistency.py::test_env_vars_are_read_by_code`
  polices; every backticked repo path added resolves
  (`test_relative_links_resolve`); no claim that this works against a live server.

- [ ] 7. Update `examples/runtime.example.yaml` and `examples/smart-home/README.md`
  (depends on 6): add a commented `auth:` block to the `home-bridge` server; change the OAuth
  bullet under "Why a real Alice server is not drivable yet" to say a static bearer header is
  now supported but Alice's OAuth authorization-code flow is not, keeping the
  structured-read-output gap, the `device`-id target-shape gap, and the mock-validated framing.
  — DoD: `examples/smart-home/runtime.yaml` is untouched (the testbed's in-process
  `fake_alice` ignores the declared transport); `uv run pytest tests/test_docs_consistency.py`
  is green.

- [ ] 8. Add a `.env.example` comment (depends on 6) explaining that an authenticated
  `streamable-http` server's credential is named by `auth.env` in `runtime.yaml` and that the
  variable is operator-chosen, so no `NEWTON_*` variable is added here.
  — DoD: no new `NEWTON_*=` assignment is introduced; comment only.

## Tests

- [ ] T1. `tests/runtime/test_config.py`: a valid `auth: {header: Authorization, scheme:
  Bearer, env: ALICE_MCP_TOKEN}` block loads and populates `HttpTransport.auth`; an omitted
  `auth` leaves it `None`.
- [ ] T2. `tests/runtime/test_config.py`: **the leak test.** `auth: {header: Authorization,
  value: "<SENTINEL>"}` raises `AuthConfigError`, and `<SENTINEL>` appears in neither
  `str(exc)` nor `repr(exc)` nor `traceback.format_exception(exc)`. Parametrised over
  `value`, `token`, `secret`, `password`. Also assert `AuthConfigError` is not a subclass of
  `ValueError` (the property the whole containment argument rests on).
- [ ] T3. `tests/runtime/test_config.py`: invalid `env` name, invalid/CRLF-bearing `header`,
  an `_SDK_MANAGED_HEADERS` name, a whitespace-bearing `scheme`, and a non-mapping `auth` each
  raise; each message names the field and never the rejected value. Plus: `auth` on a
  `stdio` transport raises.
- [ ] T4. `tests/runtime/test_config.py`: fingerprint regression. The `binding_identity` of a
  `streamable-http` server with no `auth` equals a hard-coded literal captured before this
  change (proving no existing approval is invalidated).
- [ ] T5. `tests/runtime/test_config.py`: changing `auth.env`, `auth.header` or `auth.scheme`
  changes `binding_identity`; changing only the *value* of the named environment variable
  (via `monkeypatch.setenv`) leaves it identical; and `transport_fingerprint` is computable
  with the variable entirely unset.
- [ ] T6. New `tests/runtime/test_auth.py`: `resolve_auth_header` returns
  `("Authorization", "Bearer <sentinel>")` with a scheme, the bare value without one;
  an unset and a blank variable each raise `MissingAuthSecret` naming the variable and not
  the value; `redact()` replaces the sentinel and no-ops on an empty secret.
- [ ] T7. New `tests/runtime/test_http_auth_transport.py`: **the end-to-end header test,
  socket-free.** Build an `MCPServer` (as `tests/runtime/conftest.py::build_fake_server` does)
  with one tool, take `server.streamable_http_app()`, and drive it through
  `httpx2.AsyncClient(transport=httpx2.ASGITransport(app=...), base_url=...)` injected via
  `functools.partial(default_client_factory, http_client_builder=...)`. Record every inbound
  request's headers in ASGI middleware. Assert the sentinel token appears in the recorded
  headers for the connect handshake, `list_tools` **and** `call_tool` (drive the last two
  through `CapabilityCatalog.refresh()` and `Executor.execute()`).
- [ ] T8. Same module: run a full `refresh()` + approval + `run_action()` cycle with the
  sentinel set, then assert the sentinel string appears in **none** of:
  `ServerConfig.transport_fingerprint`, `binding_identity`,
  `Approval.model_dump_json()`, every `MemoryAuditSink` event's
  `model_dump_json(by_alias=True)`, every `CatalogProblem.detail`, and
  `ExecutionOutcome.detail`.
- [ ] T9. Same module: the HTTP client lifecycle. After the factory's `async with` exits
  normally, and again after the body raises, `http_client.is_closed` is `True`.
- [ ] T10. Same module: with `auth` declared and the variable unset, `refresh()` produces
  exactly one `server_unavailable` problem whose `detail` contains the variable name and not
  any value, while a second, unauthenticated server in the same config is still discovered.
- [ ] T11. Same module: with the variable set and the transport forced to fail (ASGI app that
  500s or a builder raising a synthetic `httpx2` error whose message embeds the sentinel),
  the resulting `CatalogProblem.detail` is a useful safe diagnostic and contains no sentinel.
  Prefer class-only failures; a redaction marker is not required.
- [ ] T12. `tests/runtime/test_catalog.py`: `default_client_factory` for an `HttpTransport`
  with `auth is None` still returns a plain `Client` built from the URL (the unchanged path),
  and for `StdioTransport` still builds `StdioServerParameters` -- guard against collateral
  damage to the two untouched branches.
- [ ] T13. SDK-surface guard: `from mcp.shared._httpx_utils import create_mcp_http_client`
  imports, and `create_mcp_http_client(headers={"X-Test": "y"}).headers["X-Test"] == "y"`.
  A future `mcp` bump that moves this helper then fails with an obvious cause.
- [ ] T14. `uv run pytest` fully green, including `tests/test_docs_consistency.py` after the
  doc edits (tasks 6-8).

## Rollback

Every change is additive and gated on `HttpTransport.auth is not None`, so rollback is a clean
revert of the feature commit: `git revert <sha>` restores `HttpTransport` to `kind`+`url`,
`transport_fingerprint` to its two-key dict, and `default_client_factory` to
`Client(transport.url)`. No migration, no persisted state and no stored digest changes, because
T4 pins that an auth-free server's `binding_identity` is unchanged by the feature -- so every
approval issued while the feature was live against an *unauthenticated* server stays valid
after the revert.

Operator-level rollback without a code revert: delete the `auth:` block from `runtime.yaml`.
That immediately returns the server to the unauthenticated code path. It changes
`binding_identity` (the `auth` key leaves the canonical dict), so every outstanding approval
for that server is invalidated and `Executor._resolve_server()` raises `ExecutorError`
("refusing to call a re-pointed server") rather than silently calling it without credentials --
the intended fail-safe direction.

If only the leak containment is suspect and the feature must stay, the narrow mitigation is to
unset the named environment variable: `refresh()` then degrades that one server to
`server_unavailable` and no call is ever attempted, while the rest of the catalog keeps working.

## Additional review tasks and verification

- [ ] R1. Extend task 1 with a runtime raw-input screen before sibling Pydantic validation;
  test unrelated invalid fields, stdio auth, unknown kinds, malformed server/root containers,
  direct model validation, arbitrary extra keys containing the sentinel, and `auth: null`.
  Sentinel must be absent from `str`, `repr`, and formatted tracebacks for every rejection.
- [ ] R2. Extend T6 with CR/LF/DEL and unencodable secret values and with a nonblank value
  containing surrounding whitespace. Invalid values fail before client creation without
  echo; valid values are not silently trimmed.
- [ ] R3. Extend T11 to full-header/token reflection, nested groups, a sentinel straddling
  the truncation limit, and env rotation during an awaited failure. Inspect captured logs,
  externally rendered exception chains, catalog problems, and audit/outcomes.
- [ ] R4. Extend T7/T8 to verifier read-back requests, actual approval reuse after value
  rotation, and rejection before actuator calls after header/scheme/env-name changes.
- [ ] R5. Exercise cancellation during connect/call and exceptions from the caller's async
  context body; ensure resources close and neither is converted to `server_unavailable`.
- [ ] R6. Verify a cross-origin redirect never receives the configured credential, using
  the default SDK redirect policy and a socket-free transport double.
- [ ] R7. Before ready/merge, run the full suite and mock demo smoke and perform reversible
  mutation checks: remove auth from the request, add secret value to fingerprint, drop env
  name from fingerprint, disable containment, and sanitize only after truncation/re-reading
  rotated env. Each relevant detector must pass normally and fail under its mutation.
