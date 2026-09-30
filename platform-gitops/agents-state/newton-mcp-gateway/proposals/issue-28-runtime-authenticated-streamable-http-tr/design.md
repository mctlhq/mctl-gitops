# Design: issue-28-runtime-authenticated-streamable-http-tr

## Current state

### The transport model

`src/newton_mcp/runtime/config.py` defines a discriminated union:

```python
class HttpTransport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["streamable-http"]
    url: str

Transport = Annotated[StdioTransport | HttpTransport, Field(discriminator="kind")]
```

`ServerConfig.transport_fingerprint` (same file, lines ~101-128) hashes a canonical dict with
`newton_mcp.canonical.sha256_hex`:

- `streamable-http` -> `{"kind": "streamable-http", "url": _canonical_url(transport.url)}`
- `stdio` -> `{"kind": "stdio", "command": ..., "args": [...], "env": {...}}`

`_canonical_url()` lowercases only the scheme and host, elides a default port, and keeps
userinfo byte-exact -- its docstring says so explicitly, "because those properties silently
drop userinfo ... which would make two URLs that differ only in credentials fingerprint the
same". `ServerConfig.binding_identity` is
`f"{resolved_identity}@sha256:{transport_fingerprint}"`.

`binding_identity` is load-bearing for authority: `CandidateAction.server_binding_identity`
(`runtime/resolver.py`) carries it, `action/approval.py::issue_approval()` binds
`Approval.server_identity` to it and feeds it into `compute_binding()`, `verify_approval()`
compares it, and `Executor._resolve_server()` raises `ExecutorError` ("refusing to call a
re-pointed server") when it no longer matches. A credential placed in URL userinfo is therefore
a direct input to every one of those values.

### The one client factory

`src/newton_mcp/runtime/catalog.py::default_client_factory()` is, in its own words, "exactly
one place that maps a transport to a client":

```python
if isinstance(transport, StdioTransport):
    target = StdioServerParameters(command=..., args=..., env=...)
elif isinstance(transport, HttpTransport):
    target = transport.url
return Client(target)
```

`CapabilityCatalog.__init__` defaults `self._client_factory` to it,
`Executor.__init__` (`runtime/executor.py:95`) defaults to it, and
`Verifier.__init__` (`runtime/verifier.py:95`) defaults to it. Every test and
`examples/smart-home/fake_alice.py::in_process_factory()` substitutes a fake at the same
`ClientFactory` seam, which is why the whole suite is subprocess-free and socket-free.

### What the SDK actually does with a URL (mcp 2.2.0, pinned in `uv.lock`)

`mcp/client/client.py::Client.__post_init__` dispatches on the shape of `server`:

```python
elif isinstance(srv, str):
    self._connect = _connect_transport(streamable_http_client(srv))
...
else:
    self._connect = _connect_transport(srv)     # any async CM yielding TransportStreams
```

and `mcp/client/streamable_http.py` exposes

```python
@asynccontextmanager
async def streamable_http_client(
    url: str, *, http_client: httpx2.AsyncClient | None = None, terminate_on_close: bool = True
) -> AsyncGenerator[TransportStreams, None]
```

whose docstring says: "To configure headers, authentication, or other HTTP settings, create an
`httpx2.AsyncClient` and pass it here." Crucially, its body sets
`client_provided = http_client is not None` and only enters the client onto its own exit stack
when it created the client itself -- a caller-supplied client is **not** closed by the SDK.

`mcp/shared/_httpx_utils.py` exports (in `__all__`)
`create_mcp_http_client(headers=None, timeout=None, auth=None) -> httpx2.AsyncClient` with the
MCP-recommended 30s connect/write/pool and 300s read timeouts. `httpx2` is a hard dependency of
`mcp>=2.2` (`Requires-Dist: httpx2>=2.5.0`); the repo's own `pyproject.toml` pins `httpx`
(v1-line) for the Newton API client, which is a different package.

### Error paths that could carry a secret

- `CapabilityCatalog.refresh()` stores `detail=_truncate(repr(exc))` on a
  `server_unavailable` problem -- an unfiltered exception repr.
- `Executor._classify_call_failure()` already records only `timeout` or
  `transport failure (<ExceptionClass>)`, with a docstring explaining that a raw message
  "would carry a credential straight into the append-only audit log past `redact_args()`".
- `runtime/audit.py::redact_args()` redacts by *key name* substring only, with no value-shape
  detection -- it cannot catch a secret that arrives inside an exception string.
- Pydantic v2 `ValidationError` embeds the rejected input in its rendered message
  (`input_value=...`). A naive `extra="forbid"` rejection of `auth: {value: "sk-live-..."}`
  would therefore print the secret. This is the single sharpest trap in this issue.

### Docs and tests that constrain the change

- `docs/action-runtime.md` has the `runtime.yaml` shape (line ~38), the
  "Server identity in an approval binding" section (line ~107) listing exactly what the
  fingerprint covers, and "Adding an MCP actuator by configuration only" (line ~504).
- `examples/smart-home/README.md` line ~152 names this gap and links this issue.
- `tests/test_docs_consistency.py::test_env_vars_are_read_by_code` fails if any
  `NEWTON_*`/`ATAI_*` token appears in the doc corpus without being ast-collected from
  `src/newton_mcp/**/*.py` or assigned in `.env.example`. `_ENV_TOKEN_RE` matches only those
  two prefixes, so an operator-chosen example name like `ALICE_MCP_TOKEN` is safe --
  a name like `NEWTON_MCP_ALICE_TOKEN` would break the suite.
- `tests/test_docs_consistency.py::test_relative_links_resolve` checks every backticked
  `docs/|examples/|src/|tests/` path in the corpus.

## Proposed solution

Five changes, all additive, none of which touches the `ClientFactory` signature.

### 1. `HttpAuth` model in `runtime/config.py`

```python
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HTTP_TOKEN_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")   # RFC 9110 token
_SDK_MANAGED_HEADERS = frozenset({"content-type", "accept", "mcp-session-id", "mcp-protocol-version"})
_ALLOWED_AUTH_KEYS = frozenset({"header", "scheme", "env"})


class AuthConfigError(Exception):
    """Raised for an invalid `auth` block. Deliberately NOT a ValueError."""


class HttpAuth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    header: str
    scheme: str | None = None
    env: str


class HttpTransport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["streamable-http"]
    url: str
    auth: HttpAuth | None = None
```

**Why `AuthConfigError` is not a `ValueError`.** pydantic-core converts a `ValueError` or
`AssertionError` raised inside a validator into a `ValidationError` whose rendered message
includes `input_value=<the raw dict>` -- which is the secret when the operator wrote
`auth: {value: "sk-live-..."}`. Any other exception type propagates out of `model_validate()`
untouched. So a `model_validator(mode="before")` on `HttpTransport` inspects the raw `auth`
mapping *before* pydantic ever builds an error for it, and raises `AuthConfigError` naming only
keys and field names:

```python
@model_validator(mode="before")
@classmethod
def _screen_auth_block(cls, data: Any) -> Any:
    if not isinstance(data, dict) or "auth" not in data:
        return data
    auth = data["auth"]
    if not isinstance(auth, dict):
        raise AuthConfigError("transport.auth must be a mapping of header/scheme/env")
    extra = sorted(set(auth) - _ALLOWED_AUTH_KEYS)
    if extra:
        raise AuthConfigError(
            f"transport.auth may only contain {sorted(_ALLOWED_AUTH_KEYS)}; "
            f"rejected key(s) {extra}. A secret value must never appear in runtime.yaml -- "
            "name an environment variable with `env:` instead. "
            "(The rejected value is intentionally not shown.)"
        )
    # header / scheme / env shape checks, each naming only the field:
    ...
```

Every check inside that validator raises `AuthConfigError` with a message that contains field
names and, at most, the *env variable name* -- never a value. The `env` name is safe to print
by construction: it is the one part of the block the whole design treats as non-secret.

`load_runtime_config()` needs no change: `AuthConfigError` propagates out of
`RuntimeConfig.model_validate(data or {})` as-is, which is the desired fail-loudly behaviour.
Existing `pytest.raises(ValidationError)` tests for unknown keys elsewhere are untouched,
because the screen only fires for `transport.auth`.

### 2. Fingerprint extension, backward-compatible by omission

In `ServerConfig.transport_fingerprint`:

```python
if isinstance(transport, HttpTransport):
    canonical = {"kind": "streamable-http", "url": _canonical_url(transport.url)}
    if transport.auth is not None:
        canonical["auth"] = {
            "header": transport.auth.header,
            "scheme": transport.auth.scheme,
            "env": transport.auth.env,
        }
```

The `auth` key is added **only** when auth is declared, so every existing unauthenticated
server's fingerprint -- and therefore every outstanding approval and every value asserted in
`tests/runtime/` -- is byte-identical to today. No environment lookup happens here, which is
what makes "rotating the value does not invalidate approvals, re-pointing `env:` does" true by
construction rather than by discipline. The header name is stored as written (not
case-folded): consistent with `_canonical_url()`'s "normalise nothing you do not have to"
rule, where the failure mode is a spurious invalidation, never a spurious validity.

### 3. Header resolution: a separate, pure, testable function

New module `src/newton_mcp/runtime/auth.py` (keeps `config.py` declarative and gives the
executor/verifier a redaction helper without importing the catalog):

```python
class MissingAuthSecret(Exception):
    """The environment variable an HttpAuth names is unset or blank."""

def resolve_auth_header(
    auth: HttpAuth, *, server_name: str, env: Mapping[str, str] | None = None
) -> tuple[str, str]:
    """Return `(header_name, header_value)`. Raises MissingAuthSecret naming the VARIABLE."""
    source = os.environ if env is None else env
    raw = source.get(auth.env)
    if raw is None or not raw.strip():
        raise MissingAuthSecret(
            f"server {server_name!r} declares auth from environment variable {auth.env!r}, "
            "which is unset or blank; set it or remove the auth block "
            "(the runtime will not connect unauthenticated)"
        )
    value = raw.strip()
    return auth.header, (f"{auth.scheme} {value}" if auth.scheme else value)


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every non-empty secret occurrence with audit.REDACTED. Defence in depth."""
```

`resolve_auth_header` takes an injectable `env` mapping so tests never mutate the real
environment (and never need `monkeypatch.setenv` for the pure unit tests).

### 4. `default_client_factory` builds and owns an authenticated HTTP client

```python
HttpClientBuilder = Callable[[dict[str, str]], "httpx2.AsyncClient"]

def _default_http_client_builder(headers: dict[str, str]) -> httpx2.AsyncClient:
    from mcp.shared._httpx_utils import create_mcp_http_client
    return create_mcp_http_client(headers=headers)


@asynccontextmanager
async def _authenticated_http_client(
    url: str, headers: dict[str, str], builder: HttpClientBuilder
) -> AsyncIterator[SupportsListTools]:
    async with builder(headers) as http_client:                      # we own it: SDK will not close it
        async with Client(streamable_http_client(url, http_client=http_client)) as client:
            yield client


def default_client_factory(
    server: ServerConfig, *, http_client_builder: HttpClientBuilder = _default_http_client_builder
) -> AbstractAsyncContextManager[SupportsListTools]:
    ...
    elif isinstance(transport, HttpTransport):
        if transport.auth is None:
            return Client(transport.url)            # unchanged path, byte-for-byte
        name, value = resolve_auth_header(transport.auth, server_name=server.name)
        return _authenticated_http_client(transport.url, {name: value}, http_client_builder)
```

Four properties this shape buys:

- **The SDK will not close a caller-supplied `httpx2.AsyncClient`** (`client_provided` in
  `streamable_http_client`), so the wrapper owns it in an `async with` -- closed on the
  success path and the exception path alike.
- `Client(streamable_http_client(...))` hits the `else: _connect_transport(srv)` branch of
  `Client.__post_init__`, since the `@asynccontextmanager` object satisfies the `Transport`
  protocol (`AbstractAsyncContextManager[TransportStreams]`).
- `create_mcp_http_client(headers=...)` inherits the SDK's own connect/read timeouts rather
  than httpx defaults -- material because `Verifier._poll()` and `Executor.execute()` already
  wrap calls in `anyio.fail_after`, and mismatched inner timeouts turn a clean timeout into a
  hang.
- `http_client_builder` is a keyword-only parameter with a default, so
  `default_client_factory` still satisfies `ClientFactory = Callable[[ServerConfig], ...]` and
  every existing caller (`CapabilityCatalog`, `Executor`, `Verifier`) is unchanged. A test
  injects an `httpx2.ASGITransport`-backed client to prove the header actually lands in a
  server-side request, with no socket.

Because the header is resolved *inside* the factory, and the factory is called once per
connect by all three components, `list_tools`, `call_tool` and the verifier's read poll all
carry it -- there is still exactly one place that maps a transport to a client.

### 5. Containment at the two remaining leak sites

- `CapabilityCatalog.refresh()`: when `server.transport` is an `HttpTransport` with `auth`,
  pass the recorded `detail` through `redact(...)`. Resolution failures
  (`MissingAuthSecret`) are caught by the same `except Exception` arm and become one
  `server_unavailable` problem whose detail names the variable, never a value. Using
  `repr(exc)` for `MissingAuthSecret` is safe by construction, and the `redact()` pass is
  belt-and-braces for httpx2 exceptions that might echo a request header.
- `Executor`/`Verifier`: unchanged. `_classify_call_failure()` already records only the
  exception class, and `Verifier._poll()` swallows the exception entirely (`except Exception:
  return None`).

### Docs

- `docs/action-runtime.md`: add `auth` to the `runtime.yaml` block; extend the
  `streamable-http` bullet under "Server identity in an approval binding" to state exactly
  what enters the digest (`header`, `scheme`, `env` *name*) and what never does (the value,
  which is never read during fingerprinting); add a short "Authenticated streamable-http"
  subsection covering the connect-time failure, the rotation-vs-re-point rule, the
  no-OAuth-flow boundary, and an explicit **mock-validated** label; update "Adding an MCP
  actuator by configuration only" to mention the extra env export.
- `examples/runtime.example.yaml`: add a commented `auth:` block on `home-bridge`.
- `examples/smart-home/README.md`: the OAuth bullet under "Why a real Alice server is not
  drivable yet" changes from "no auth-header support" to "a static bearer header is now
  supported, but Alice's OAuth authorization-code flow is not", keeping the other two gaps and
  the mock-validated framing intact.
- Example variable name in docs stays operator-namespaced (`ALICE_MCP_TOKEN`), outside the
  `NEWTON_*`/`ATAI_*` prefixes that `test_env_vars_are_read_by_code` polices. `.env.example`
  is not touched.

## Alternatives

**A. Keep credentials in URL userinfo and redact them out of the fingerprint.**
Zero config surface: `https://token@host/mcp` already connects, and `_canonical_url()` could
strip userinfo before hashing. Dropped because it inverts the current, deliberate safety
property (`_canonical_url`'s docstring: two URLs differing only in credentials must fingerprint
differently), because the secret would still sit in a committed, reviewable `runtime.yaml`,
and because it would still reach `CatalogProblem.detail` through `repr(exc)` on any httpx
error that echoes the URL. It also fails the issue's first acceptance criterion outright.

**B. Use the SDK's OAuth client (`mcp/client/auth/`) instead of a static header.**
Strictly more capable, and the real Alice server genuinely speaks OAuth. Dropped for this
proposal because it needs a token store, a refresh path, a redirect handler, and a client
registration -- none of which fit "prefer small, explicit code over frameworks" (`AGENTS.md`),
none of which is testable without a real authorization server, and none of which the issue
asks for. A static `Authorization: Bearer` header is a superset of what a service-account or
pre-issued token needs, and `HttpAuth` is a forward-compatible place to later add
`oauth: {...}` as a sibling.

**C. Resolve the environment variable at *load* time and store the value on `HttpTransport`.**
Simplest to implement, and gives a single failure point. Dropped because it puts the secret
inside a Pydantic model that `Executor.execute()` deep-copies (`server.model_copy(deep=True)`),
that `repr()` renders in any traceback frame showing a `ServerConfig`, and that is one
`model_dump()` away from a log line; it would also make `transport_fingerprint` uncomputable
in a process without credentials, and would couple config *validation* to the deployment
environment (breaking a CI lint of `runtime.yaml`). Resolving at connect keeps the secret's
lifetime bounded to one `async with`.

**D. Add a generic `headers: {NAME: ENV_VAR}` map instead of `{header, scheme, env}`.**
More flexible (multiple headers, no scheme special-casing). Dropped because the issue
specifies the singular shape, because `scheme` as its own field makes the fingerprint's
"what changed" story precise (re-pointing `Bearer` -> `Basic` is a visible authority change),
and because a `{name: value}` map invites an operator to write a literal value and makes the
"reject an inline secret" check ambiguous. A `headers:` list can be added later alongside.

## Platform impact

**Migrations.** None. `auth` is optional and defaults to `None`; an existing `runtime.yaml`
loads unchanged. No file format version, no state to migrate, no stored fingerprints to rewrite.

**Backward compatibility.** The `auth` key is absent from the canonical dict when auth is not
declared, so `transport_fingerprint` and `binding_identity` for every existing server are
byte-identical and outstanding approvals stay valid. `ClientFactory` keeps its one-positional-
argument signature, so `examples/smart-home/fake_alice.py::in_process_factory()`,
`tests/runtime/conftest.py::in_memory_factory()` and every hand-written double keep working
untouched. `Client(transport.url)` is still the code path for an unauthenticated HTTP server,
so nothing about today's behaviour changes there either.

**Dependencies.** No new entry in `pyproject.toml`. `httpx2` arrives transitively with
`mcp>=2.2` and is only imported for a type annotation (under `TYPE_CHECKING`) plus inside the
default builder. If the reviewer prefers not to depend on a transitive package at all, the
fallback is to add `httpx2>=2.5,<3` to `[project.dependencies]` -- note that is a *different*
distribution from the existing `httpx>=0.27,<1` used by `newton/api.py`, and both can coexist.

**Risk: `mcp.shared._httpx_utils` is an underscore-prefixed module.** It declares
`__all__ = ["create_mcp_http_client", ...]` and is what the SDK's own `sse.py`,
`streamable_http.py` and `session_group.py` import, so it is de-facto stable inside the
`mcp>=2.2,<3` pin -- but it is not a documented public path. Mitigation: one test that
imports it and asserts `create_mcp_http_client(headers={"X": "y"}).headers["X"] == "y"`, so an
SDK bump that moves it fails loudly with a clear cause instead of at connect time. Fallback if
it ever disappears: build `httpx2.AsyncClient(headers=..., timeout=httpx2.Timeout(30, read=300))`
directly, reproducing the constants documented in `_httpx_utils.MCP_DEFAULT_TIMEOUT` /
`MCP_DEFAULT_SSE_READ_TIMEOUT`.

**Risk: a leaked secret through a pydantic `ValidationError`.** This is the reason the
inline-secret screen raises a non-`ValueError` exception from a `mode="before"` validator.
Mitigation: a test that constructs `auth: {"header": ..., "value": "<sentinel>"}`, asserts the
raise, and asserts the sentinel is absent from `str(exc)`, `repr(exc)` and the formatted
traceback. Without that test the feature can regress silently on any pydantic upgrade.

**Risk: a leaked secret through an httpx2 exception repr in `CatalogProblem.detail`.**
Mitigated by the `redact()` pass on the auth path, and asserted by a test that forces a
transport failure with the sentinel configured.

**Risk: a leaked HTTP client (socket/fd) if the wrapper is written as a bare
`Client(streamable_http_client(url, http_client=hc))`.** The SDK will not close a
caller-supplied client. Mitigated by the `@asynccontextmanager` wrapper owning it, and by a
test asserting `http_client.is_closed` after the `async with` block exits, including when the
body raises.

**Risk: sending a header the SDK also sets** (`mcp-session-id`, `content-type`) would produce a
duplicate or break session handling. Mitigated by the load-time `_SDK_MANAGED_HEADERS`
rejection.

**Risk: header injection via a `\r\n` in `header` or `scheme`.** Mitigated by the RFC 9110
token regexes at load time. The *value* comes from the environment and is not regex-checked;
`httpx2` rejects control characters in header values itself, and a check here would risk
echoing the value in an error message.

**Resource impact.** One extra `httpx2.AsyncClient` construction per connect for authenticated
servers only. `CapabilityCatalog.refresh()` already opens and closes one client per server per
pass, so the added cost is a client object, not a connection: no pooling regression relative to
today, and the existing `anyio.fail_after` scopes still bound everything.

**Security posture after this change.** The secret exists only between
`resolve_auth_header()` and the close of the `async with` in the factory. It is never in
`runtime.yaml`, never in a Pydantic model, never in `sha256_hex()` input, never in
`Approval`/`compute_binding()`, never in `AuditEvent`, and never in an
`ExecutionOutcome.detail`. `redact_args()`'s key-name heuristic in `runtime/audit.py` is
untouched and remains irrelevant here -- the secret is never an argument.

**Honesty constraint.** Nothing in this change is validated against a real authenticated MCP
server. The docs must keep saying "mock-validated", per `AGENTS.md` and the existing framing in
`examples/smart-home/README.md`. The ASGI-based test proves the header reaches a real MCP
server implementation's request headers in-process; it does not prove any live integration.
