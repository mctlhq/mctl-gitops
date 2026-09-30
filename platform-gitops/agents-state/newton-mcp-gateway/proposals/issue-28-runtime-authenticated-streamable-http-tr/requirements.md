# Runtime: authenticated streamable-http transport (auth header from env)

## Context

`HttpTransport` in `src/newton_mcp/runtime/config.py` carries exactly one field, `url`.
`default_client_factory()` in `src/newton_mcp/runtime/catalog.py` turns that value into
`Client(transport.url)`, which the MCP SDK resolves to `streamable_http_client(url)` with a
default `httpx2.AsyncClient` and therefore no credentials. Every real streamable-http MCP
server that sits behind OAuth or bearer auth is consequently unreachable by
`CapabilityCatalog`, `Executor` and `Verifier` -- the three components that all share that one
factory. `examples/smart-home/README.md` records this as one of the three concrete reasons a
real Alice server ("Why a real Alice server is not drivable yet": "It sits behind **OAuth**,
and `HttpTransport` in `runtime/config.py` has no auth-header support") cannot be driven by
this runtime yet.

The only workaround available today is putting a credential into the URL's userinfo
(`https://user:token@host/mcp`). That is explicitly the wrong answer here:
`_canonical_url()` keeps userinfo byte-exact precisely so that two URLs differing only in
credentials fingerprint differently, which means the credential is an input to
`transport_fingerprint` and so to `binding_identity`, which is carried verbatim on
`CandidateAction.server_binding_identity`, on every `Approval.server_identity`, and into
`compute_binding()`. A credential in the URL also travels into
`CatalogProblem.detail`, which stores `_truncate(repr(exc))` of a transport error.
This proposal adds a declared auth header whose *value* comes from a named environment
variable, so the secret never reaches the config file, the fingerprint, an approval, an
audit line, a problem detail or an exception message -- while the header *name*, the scheme
and the env-var *name* do enter the fingerprint, so re-pointing auth at a different variable
still invalidates every outstanding approval.

## User stories

- AS an operator wiring a real MCP actuator, I WANT to declare in `runtime.yaml` that a
  streamable-http server needs an `Authorization: Bearer <token>` header whose value comes
  from a named environment variable, SO THAT `CapabilityCatalog`, `Executor` and `Verifier`
  can reach it without me pasting a credential into a reviewable, committed allow-list.
- AS a reviewer of `runtime.yaml`, I WANT config validation to reject any inline literal
  secret in the `auth` block, SO THAT a pull request that would commit a credential fails at
  load time rather than merging.
- AS a security reviewer of the audit trail, I WANT a guarantee that the token value appears
  in no fingerprint, no `Approval`, no audit line, no `CatalogProblem.detail` and no
  exception text, SO THAT the append-only JSONL log and any crash report stay safe to share.
- AS an operator rotating a credential, I WANT rotating only the env *value* to leave
  outstanding approvals valid, and re-pointing `env:` at a different variable name to
  invalidate them, SO THAT approval invalidation tracks a change of authority, not a routine
  rotation.
- AS an operator with a typo in my environment, I WANT a load/connect failure that names the
  missing variable, SO THAT I can fix it without the runtime silently connecting unauthenticated.

## Acceptance criteria (EARS)

Configuration and validation

- WHEN a `runtime.yaml` declares a `streamable-http` server with
  `auth: {header: <name>, scheme: <scheme>, env: <VAR>}`, THE SYSTEM SHALL load it into an
  `HttpAuth` model attached to `HttpTransport.auth`.
- WHEN a `streamable-http` transport declares no `auth` block, THE SYSTEM SHALL behave
  exactly as today: `HttpTransport.auth` is `None`, no header is sent, and
  `transport_fingerprint` is byte-identical to the value it produces before this change.
- IF an `auth` block carries any key other than `header`, `scheme` and `env` (for example
  `value`, `token`, `password`, `secret`), THEN THE SYSTEM SHALL refuse to load the config
  with an error naming a fixed field path (and a validated owning server name when
  available), and THE SYSTEM SHALL NOT
  include the rejected key's value in the error text, its `repr`, or any `input_value`
  echoed by the validation machinery.
- IF `auth.env` is absent, empty, or not a syntactically valid POSIX environment variable
  name (`[A-Za-z_][A-Za-z0-9_]*`), THEN THE SYSTEM SHALL refuse to load the config with an
  error that names the fixed field path (and a validated owning server name when
  available) but never the rejected value.
- IF `auth.header` is not a valid HTTP field name (RFC 9110 token characters only -- in
  particular no CR, LF, colon or space), THEN THE SYSTEM SHALL refuse to load the config.
- IF `auth.header` case-insensitively names a header the MCP streamable-http transport
  manages itself (`content-type`, `accept`, `mcp-session-id`, `mcp-protocol-version`),
  THEN THE SYSTEM SHALL refuse to load the config, naming the header.
- IF `auth.scheme` is present and is not a single HTTP token (no whitespace, non-empty),
  THEN THE SYSTEM SHALL refuse to load the config with an error naming the field, not the value.
- WHERE `auth.scheme` is omitted, THE SYSTEM SHALL send the environment variable's value as
  the whole header value; WHERE it is present, THE SYSTEM SHALL send `f"{scheme} {value}"`.
- IF a `stdio` transport declares an `auth` block, THEN THE SYSTEM SHALL reject the config
  (`StdioTransport` keeps `extra="forbid"`).

Fingerprint and approval binding

- WHILE a `streamable-http` server declares `auth`, THE SYSTEM SHALL compute
  `transport_fingerprint` over `{"kind": "streamable-http", "url": <canonical url>, "auth":
  {"header": ..., "scheme": ..., "env": ...}}` -- header name, scheme and env-var *name* only.
- WHILE a `streamable-http` server declares `auth`, THE SYSTEM SHALL NOT read the named
  environment variable while computing `transport_fingerprint` or `binding_identity`.
- WHEN only the *value* of the named environment variable changes, THE SYSTEM SHALL produce
  an unchanged `binding_identity`, so approvals issued before the rotation stay valid.
- WHEN the `env` var *name*, the `header` name, or the `scheme` changes, THE SYSTEM SHALL
  produce a different `binding_identity`, so `Executor._resolve_server()` raises
  `ExecutorError` for any candidate resolved before the change.

Connecting with the header

- WHEN `default_client_factory()` is called for a `streamable-http` server that declares
  `auth`, THE SYSTEM SHALL build an HTTP client carrying the resolved header and use it for
  the connect handshake, `list_tools` and `call_tool` alike -- one factory serves
  `CapabilityCatalog.refresh()`, `Executor.execute()` and `Verifier._poll()`.
- WHEN the async context manager returned by `default_client_factory()` exits, THE SYSTEM
  SHALL close the HTTP client it created, on the success path and on the exception path.
- IF the named environment variable is unset or blank at connect time, THEN THE SYSTEM SHALL
  raise an error naming the variable and the server, and SHALL NOT open any transport and
  SHALL NOT connect unauthenticated.
- IF the named environment variable is unset or blank while `CapabilityCatalog.refresh()`
  runs, THEN THE SYSTEM SHALL record exactly one `server_unavailable` `CatalogProblem` whose
  `detail` names the missing variable, and SHALL still discover the remaining servers.

Secret containment

- WHILE any code path formats an error, a reason string, a `CatalogProblem.detail`, an
  `AuditEvent.reason` or an `ExecutionOutcome.detail`, THE SYSTEM SHALL NOT emit the resolved
  header value.
- WHEN a transport error occurs during `CapabilityCatalog._discover_server()` for a server
  that declares `auth`, THE SYSTEM SHALL expose a safe, class-only transport failure instead of raw exception
  text. A missing-variable diagnostic may name the validated variable and server.
  Sanitization SHALL happen before truncation and SHALL NOT re-read the environment to
  discover what secret the failed connection used.
- WHEN `Executor.execute()`'s call attempt fails, THE SYSTEM SHALL keep the existing
  `_classify_call_failure()` behaviour (exception class only, never its message).

Documentation

- WHEN `docs/action-runtime.md` describes `runtime.yaml` and the approval binding, THE SYSTEM
  SHALL document the `auth` block, what enters the fingerprint, what never does, and the
  rotation-vs-re-point distinction.
- WHILE no run against a real authenticated MCP server has happened, THE SYSTEM SHALL keep
  the feature labelled mock-validated in `docs/action-runtime.md` and
  `examples/smart-home/README.md`, and SHALL NOT claim a live integration works
  (`AGENTS.md`: "Do not claim a live Newton integration works until it has been tested with
  real credentials").
- IF a doc names a concrete environment variable in a `NEWTON_*` or `ATAI_*` namespace, THEN
  that variable SHALL be read by `src/newton_mcp/**/*.py` or assigned in `.env.example`,
  because `tests/test_docs_consistency.py::test_env_vars_are_read_by_code` enforces exactly
  that. The documented example variable is therefore operator-chosen and outside those two
  prefixes (for example `ALICE_MCP_TOKEN`, as the issue writes it).

## Out of scope

- A full OAuth 2.1 client: authorization-code flow, token endpoints, refresh, discovery,
  dynamic client registration. `mcp>=2.2` ships `mcp/client/auth/` for that; this proposal
  adds a static header only, and says so in the docs.
- mTLS, client certificates, custom CA bundles, proxy configuration.
- Reading a secret from a file path, a Vault/Kubernetes secret, or a keyring. Environment
  variable only.
- Auth for `stdio` transports -- those already pass `env` through `StdioServerParameters`.
- Per-capability or per-tool credentials; auth is declared once per server.
- Redacting a secret that an operator embeds in URL userinfo. That remains fingerprinted
  verbatim and remains discouraged; the docs will point at `auth` as the supported path.
- Connecting this repository to the real `mctlhq/mctl-alice` server. That still needs
  structured read output (`mctlhq/mctl-alice#47`) and a room-shaped target; this proposal
  closes only the auth gap named in `examples/smart-home/README.md`.
- Rotating a live credential without reconnecting: the header is resolved when the client is
  built, so a rotation takes effect on the next connect, not mid-session.

## Open questions

- **Multiple headers per server.** The issue's shape (`auth: {header, scheme, env}`) is
  singular. Some servers want an API key plus a tenant id. Proceeding with the singular shape
  exactly as the issue specifies; a future `headers: [...]` list can be added without
  breaking it, and the fingerprint scheme already generalises.
- **Whether `scheme` should default to `Bearer`.** The issue's example writes `scheme: Bearer`
  explicitly. Proceeding with no default: an omitted `scheme` means "send the raw value",
  which is what an `X-API-Key`-style header needs, and makes the common bearer case explicit
  in the reviewable file.
- **How strictly to validate at load time vs connect time.** Proceeding with: *shape* is
  validated at load (`load_runtime_config()`), *presence of the value* is checked at connect
  (`default_client_factory()`), because a config file is often loaded in a process or CI job
  that legitimately has no production credentials. `RuntimeConfig` stays purely declarative
  and `transport_fingerprint` stays computable without any environment.
- **Whether a missing variable should be a hard `refresh()` failure rather than one
  `server_unavailable` problem.** Proceeding with the existing per-server-problem contract:
  `CapabilityCatalog.refresh()` already degrades one unreachable server into one problem and
  keeps the rest of the catalog usable, and a credential that is absent is operationally the
  same as a server that is unreachable.
- **Whether `mcp.shared._httpx_utils.create_mcp_http_client` (underscore-prefixed module, but
  with a public `__all__`) is an acceptable import.** Proceeding with yes, plus a guard test,
  because it is the only way to inherit the SDK's own connect/read timeouts; the fallback
  (constructing `httpx2.AsyncClient` directly and declaring `httpx2` in `pyproject.toml`) is
  written up in design.md.

## Review amendments: containment is a connection-bound invariant

- Reject secret-bearing inline auth anywhere in the raw runtime document before Pydantic
  can report an unrelated field error. Cover HTTP and stdio declarations, unknown transport
  kinds, malformed root/server shapes, and direct model validation. An unrelated error must
  not echo a sibling auth block. Validate all auth fields without echoing untrusted values
  or arbitrary rejected key names; only fixed field names and validated server/env names
  are diagnostic data. `auth: null` means no authentication.
- Validate the resolved header value before giving it to httpx2: reject control characters
  (including CR/LF/DEL) and values the client cannot encode, with a value-free error. Check
  blankness without silently stripping or otherwise altering a nonblank credential.
- The production authenticated transport boundary SHALL prevent SDK/client exceptions and
  exception groups from exposing request credentials through `str`, `repr`, rendered
  traceback, chaining, or captured logs. Safe diagnostics may contain fixed messages and
  exception class names; raw provider text is not necessary. Do not convert cancellation
  into a catalog problem, and preserve exceptions raised by a caller inside the client
  context rather than reclassifying them as transport failures.
- Any defensive redaction uses the credential captured for that exact connection, before
  truncation. Re-reading env after a failure is forbidden: the value may have rotated while
  the request was in flight. Do not retain resolved credentials in configuration models,
  catalog snapshots, approvals, or a global secret registry.
- Default HTTP clients SHALL keep redirect following disabled. A cross-origin redirect
  SHALL not deliver the configured auth header to the other origin; test the existing SDK
  guarantee rather than introducing a custom redirect implementation.
- Containment tests SHALL exercise hostile provider exceptions containing the full header
  and token, a token spanning the catalog truncation boundary, environment rotation during
  an awaited failure, and nested exception groups. Include logs and formatted tracebacks,
  not merely final success-path audit events.
- Prove approval behavior with actual candidates/approvals and executor calls: changing only
  the env value keeps the approval usable; changing header/scheme/env name rejects the old
  binding before any actuator call. Include verifier read-back HTTP requests in the
  authenticated integration test.
