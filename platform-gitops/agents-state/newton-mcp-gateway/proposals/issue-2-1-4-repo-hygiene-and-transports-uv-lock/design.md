# Design: issue-2-1-4-repo-hygiene-and-transports-uv-lock

## Current state

Everything below was read in the clone at `a0ce6fa` (merge of #17).

**Configuration.** `src/newton_mcp/config.py` defines a single frozen dataclass
`Settings` with six fields (`backend`, `api_key`, `api_endpoint`, `text_model`,
`omega_model`, `request_timeout_sec`) and one classmethod `Settings.from_env(env)`
that takes an optional dict so tests can pass a literal environment
(`tests/test_config.py` calls `Settings.from_env({})`). The validation idiom is already
established: read, `.strip().lower()`, membership check, and on failure
`raise ValueError(f"NEWTON_BACKEND must be 'mock' or 'api', got {backend!r}")`. The
`Backend` type is a `Literal["mock", "api"]` alias at module level, and the constructed
value is passed with a `# type: ignore[arg-type]` because `dict.get` returns `str`.
There is no transport, host or port concept anywhere in the file.

**Server.** `src/newton_mcp/server.py` imports `MCPServer` and `Context` from
`mcp.server.mcpserver` — the v2 name for what was FastMCP — builds the server inside
`create_server(settings=None, backend=None)`, registers exactly two tools
(`newton_query`, `newton_embed_timeseries`), both with
`ToolAnnotations(read_only_hint=True, open_world_hint=True)`, and wires an
`asynccontextmanager` lifespan that yields an `AppState` and calls `backend.aclose()`
on exit. The entry point is three lines:

```python
def main() -> None:
    create_server().run(transport="stdio")
```

`create_server` itself calls `Settings.from_env()` when no settings are passed, so
today `main()` has no `Settings` object of its own. `pyproject.toml` declares the
console script `newton-mcp = "newton_mcp.server:main"`.

**The `mcp` v2 API this depends on.** The constraint `mcp>=2.2,<3` in `pyproject.toml`
resolves to `mcp 2.2.0` (the current latest v2 on PyPI). Reading that wheel's
`mcp/server/mcpserver/server.py`, `MCPServer.run` is an overloaded method:

```python
def run(self, transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
        **kwargs: Any) -> None
```

with a `streamable-http` overload accepting keyword-only `host: str = ...`,
`port: int = ...`, `streamable_http_path: str = ...` and more. The dispatch is a plain
`match` that calls `anyio.run(lambda: self.run_streamable_http_async(**kwargs))`;
`run_streamable_http_async` defaults to `host="127.0.0.1"`, `port=8000`,
`streamable_http_path="/mcp"`, and internally does `import uvicorn` and serves the
Starlette app returned by `streamable_http_app`. Two consequences matter for this
design:

1. **No new dependency is required.** The `mcp 2.2.0` wheel metadata lists
   `uvicorn>=0.31.1`, `starlette`, `sse-starlette` and `python-multipart` as hard
   `Requires-Dist` entries, not extras. The issue's "do not add a web framework" rule
   is met by simply not adding one — the transport is already in the box.
2. **DNS-rebinding protection is host-conditional.** `streamable_http_app` (and the
   SSE path, visibly, at `server.py:1279` and the `sse_app` above it) only synthesizes
   a `TransportSecuritySettings(enable_dns_rebinding_protection=True, ...)` when
   `transport_security is None` *and* the bind host is `127.0.0.1`, `localhost` or
   `::1`. Binding `0.0.0.0` in the container therefore runs without it. That is the
   behaviour that makes a published port usable; it is a documentation obligation, not
   a bug to work around here.

**CI and packaging.** `.github/workflows/ci.yml` is five steps: checkout,
`astral-sh/setup-uv@v5`, `uv python install 3.12`, `uv sync --group dev`,
`uv run pytest -q`. No `uv.lock` exists, so every run re-resolves. `.gitignore` lists
`.venv/`, `__pycache__/`, `*.pyc`, `.env`, `dist/`, `.pytest_cache/` — it does not
exclude `uv.lock`, so committing the lock needs no `.gitignore` change. There is no
`Dockerfile`, no `.dockerignore`, and no `CONTRIBUTING.md`.

**Tests.** `tests/conftest.py` provides a `mock_backend` fixture
(`MockNewtonBackend()`) and a `server` fixture calling
`create_server(Settings(), backend=mock_backend)` — note it constructs `Settings()`
positionally-free, so any new field must have a default or this fixture breaks.
`tests/test_mcp_server.py` holds two async tests over `server.list_tools()`.
`tests/test_config.py` holds three tests over `Settings.from_env`. `pytest` runs in
`asyncio_mode = "auto"`.

**Schema.** `tests/test_action_contract.py:19` asserts
`json.loads(SCHEMA.read_text()) == PhysicalActionContract.model_json_schema()`, where
`SCHEMA` is `schemas/physical-action-contract.schema.json`. There is no regeneration
script in the repo — regeneration today is a manual dump of `model_json_schema()`.
That is the gap `CONTRIBUTING.md` must close.

## Proposed solution

Five changes, each small and independently reviewable.

### 1. `Settings` grows three fields

In `src/newton_mcp/config.py`, add a module-level
`Transport = Literal["stdio", "streamable-http"]` next to the existing `Backend` alias,
three defaulted fields on the frozen dataclass — `transport: Transport = "stdio"`,
`host: str = "127.0.0.1"`, `port: int = 8000` — and their parsing in `from_env`,
written in the file's existing idiom:

```python
transport = env.get("NEWTON_MCP_TRANSPORT", "stdio").strip().lower()
if transport not in ("stdio", "streamable-http"):
    raise ValueError(
        f"NEWTON_MCP_TRANSPORT must be 'stdio' or 'streamable-http', got {transport!r}"
    )
```

`PORT` is parsed defensively because `int()` on garbage raises a bare
`invalid literal for int()` that names neither the variable nor the expectation:

```python
port_raw = env.get("PORT", "8000").strip()
try:
    port = int(port_raw)
except ValueError:
    raise ValueError(f"PORT must be an integer, got {port_raw!r}") from None
if not 1 <= port <= 65535:
    raise ValueError(f"PORT must be in 1-65535, got {port}")
```

`HOST` is `env.get("HOST", "127.0.0.1").strip() or "127.0.0.1"`, so an empty
`HOST=` in a `.env` file falls back rather than binding to the empty string. All three
fields are defaulted, so `tests/conftest.py`'s bare `Settings()` keeps working and
every existing `test_config.py` assertion stays true.

Note the existing `request_timeout_sec=float(env.get(...))` has the same bare-`ValueError`
weakness; it is deliberately left alone, since touching it is not in this issue's scope.

### 2. `main()` reads config once and dispatches

`src/newton_mcp/server.py`:

```python
def main() -> None:
    settings = Settings.from_env()
    server = create_server(settings)
    if settings.transport == "streamable-http":
        server.run(transport="streamable-http", host=settings.host, port=settings.port)
    else:
        server.run(transport="stdio")
```

Three properties fall out of this shape. Configuration is read exactly once instead of
once inside `create_server` and again in `main` — an invalid `NEWTON_MCP_TRANSPORT`
fails before a backend or an HTTP listener exists. The stdio branch passes no `host`
or `port`, matching the `Literal["stdio"]` overload exactly, so a future `mcp` release
that rejects stray kwargs on the stdio path cannot break us. And `create_server` keeps
its current signature, so every existing caller — including `tests/conftest.py` — is
untouched.

The `if/else` is deliberate rather than a dict dispatch or `**kwargs` spread: with two
transports, an explicit branch is smaller, and the kwargs each branch passes are
genuinely different, which a spread would hide.

### 3. `uv.lock` and CI

Run `uv lock` and commit the result. CI's install step becomes
`uv sync --locked --group dev`, which fails loudly if `uv.lock` is stale relative to
`pyproject.toml` rather than silently re-resolving. The rest of the `test` job is
unchanged.

A second CI job, `docker`, runs `docker build -t newton-mcp-gateway:ci .` and then two
assertions against the built image:

- `docker run --rm --entrypoint id newton-mcp-gateway:ci -u` returns a non-zero uid.
- `docker run -d -p 8000:8000` the image, poll `http://127.0.0.1:8000/mcp` until it
  returns *any* HTTP status code, then stop the container. A bare GET to `/mcp` is not
  a valid MCP request and will answer 4xx; that is the point — a status code proves a
  listener answered, while a connection refusal proves it did not. The check must not
  assert 200.

The two jobs are independent and run in parallel; the docker job does not need `uv` on
the runner.

### 4. `Dockerfile` and `.dockerignore`

Multi-stage, `uv`-based, slim Python 3.12:

- **Builder**: `python:3.12-slim`, with the `uv` binary copied in from the pinned
  `ghcr.io/astral-sh/uv:<version>` image via `COPY --from`. Copy `pyproject.toml`,
  `uv.lock` and `README.md` (the `readme` field makes hatchling need it), then
  `uv sync --locked --no-dev --no-install-project` to create `/app/.venv` as a cached
  layer, then copy `src/` and `uv sync --locked --no-dev` to install the project
  itself. `UV_COMPILE_BYTECODE=1` and `UV_LINK_MODE=copy` are set so the venv is
  self-contained and importable from the runtime stage.
- **Runtime**: the same `python:3.12-slim` base, a non-root user created with
  `useradd`, `COPY --from=builder /app/.venv /app/.venv` — **root-owned, no
  `--chown`** — followed by `RUN chmod -R go-w /app` so no group/other write bit
  survives, then `ENV PATH="/app/.venv/bin:$PATH"`, `USER <user>`, `EXPOSE 8000`, and
  `ENTRYPOINT ["newton-mcp"]`. Image-level `ENV` defaults are
  `NEWTON_BACKEND=mock`, `NEWTON_MCP_TRANSPORT=streamable-http`, `HOST=0.0.0.0`,
  `PORT=8000`, plus `PYTHONUNBUFFERED=1` so container logs are not swallowed.

Setting `NEWTON_MCP_TRANSPORT=streamable-http` at the image level, while the library
default stays `stdio`, is what reconciles the issue's two requirements: a bare
`docker run -p 8000:8000` serves HTTP, and a bare `uv run newton-mcp` still speaks
stdio. Every one of those values is overridable with `docker run -e`, including
`-e NEWTON_MCP_TRANSPORT=stdio` for `docker run -i`.

The runtime user never owns `/app` or `/app/.venv`: the process runs as the non-root
user with read/execute access only, which is what the "owning no write access to the
application directory" acceptance criterion requires. (Amended before approval: the
first draft used `COPY --chown=<user>`, which would have made the service user the
owner of the venv and contradicted that criterion.)

`uv` is deliberately *not* present in the runtime stage — only the resulting venv is
copied. That keeps the runtime image free of the build toolchain and means
`uv.lock` correctness is enforced at build time, once.

`.dockerignore` excludes `.git/`, `.github/`, `.venv/`, `__pycache__/`, `*.pyc`,
`.pytest_cache/`, `.env`, `dist/`, `tests/`, `docs/`, `examples/` and `*.md` except
`README.md`. Excluding `.git/` matters most: it is the largest and most sensitive part
of the context.

### 5. Documentation

`README.md`: verify the existing Claude Desktop snippet by actually running
`uv --directory <path> run newton-mcp` — the snippet's `args` are
`["--directory", "/path/to/newton-mcp-gateway", "run", "newton-mcp"]`, which is valid
`uv` invocation order, but the `Quickstart` above it uses `uv sync` without
`--group dev` and the snippet assumes the project is already synced; if the host must
run `uv sync` first for the snippet to work, say so. Correct whatever does not work and
record the finding in the PR description. Then add a short section with two new
examples:

```bash
NEWTON_MCP_TRANSPORT=streamable-http PORT=8000 uv run newton-mcp   # http://127.0.0.1:8000/mcp
```

```bash
docker build -t newton-mcp-gateway .
docker run --rm -p 8000:8000 newton-mcp-gateway                     # http://127.0.0.1:8000/mcp
```

with one explicit sentence that the container binds `0.0.0.0` for the container
network, ships no authentication, and should not be published to an untrusted network
without a proxy in front. `.env.example` gains the three new variables with the same
commented style it already uses.

`CONTRIBUTING.md` is short by design: setup (`uv sync --group dev`), tests
(`uv run pytest`), the transports table, schema regeneration — concretely, that
`tests/test_action_contract.py` asserts
`schemas/physical-action-contract.schema.json` equals
`PhysicalActionContract.model_json_schema()`, and the one-liner that rewrites it after
a model change — and a pointer to `AGENTS.md` for the hard rules rather than a copy of
them, so the two files cannot drift.

## Alternatives

**Read the transport in `create_server` and return a pre-configured runner.** Rejected:
`create_server` is the seam every test uses to get a server with an injected mock
backend, and transport is a process-level concern, not a server-construction one.
Pushing it down would make `tests/conftest.py`'s `create_server(Settings(), backend=...)`
carry a meaning it does not want, and would make the transport untestable without
constructing a real server.

**Add a CLI (`typer`/`argparse`) with `--transport`, `--host`, `--port` flags.**
Rejected: the issue specifies environment variables, container and MCP-host
configuration are both environment-shaped, and `AGENTS.md` says "prefer small, explicit
code over frameworks". `mcp[cli]` would pull `typer` for no gain here. Environment
variables also compose with the Dockerfile `ENV` defaults without a shell wrapper.

**Build the Docker image with `pip install .` instead of `uv sync --locked`.**
Rejected: it would silently re-resolve at image build time, so the image could
contain a different dependency set than CI tested — which is the exact failure mode
`uv.lock` exists to prevent. The issue asks for a `uv`-based build for this reason.

**Expose `sse` alongside `streamable-http` since `mcp 2.2.0` supports both.** Rejected:
SSE is the deprecated transport, the issue names exactly two values, and every extra
accepted value is another branch in `main()` and another row of test matrix for no
current consumer.

**Mount the `mcp` Starlette app inside a thin FastAPI/Starlette app to add a `/healthz`
route.** Rejected outright: that is adding a web framework, which the issue forbids.
The container ships no `HEALTHCHECK` instead.

## Platform impact

**Migrations and backward compatibility.** There is no persistent state and no wire
format to migrate. Every new `Settings` field is defaulted, so `Settings()` and
`Settings.from_env({})` behave exactly as before. With `NEWTON_MCP_TRANSPORT` unset,
`main()` reaches the same `run(transport="stdio")` call it does today, so existing
Claude Desktop configurations are unaffected — this is the issue's third acceptance
criterion and is covered by leaving `tests/test_mcp_server.py`'s existing assertions
untouched and green.

One behaviour does change subtly: `main()` now calls `Settings.from_env()` itself and
passes the result to `create_server`, instead of letting `create_server` read the
environment. The resulting `Settings` is identical; only the moment of failure moves
earlier. No caller other than `main` is affected.

**Resource impact.** The runtime image is a slim Python 3.12 base plus a virtualenv
containing `mcp`, `pydantic`, `httpx`, `httpx2`, `starlette`, `uvicorn` and their
transitive dependencies — expect roughly 200-300 MB uncompressed, dominated by the
base image and `pydantic`'s compiled core. Serving streamable-http adds one `uvicorn`
process; memory footprint is a few tens of MB at idle. CI gains a docker build job,
adding a couple of minutes of wall clock in parallel with the test job.

**Risks and mitigations.**

- *`0.0.0.0` bind disables `mcp`'s DNS-rebinding protection.* This is load-bearing
  behaviour in `mcp 2.2.0`, confirmed by reading `streamable_http_app`. Mitigation: the
  default outside the container stays `127.0.0.1`, where protection is on, and the
  README states plainly that the container ships no authentication and must not face an
  untrusted network unproxied. Recorded as an open question for the reviewer.
- *A committed `uv.lock` can drift from `pyproject.toml`.* Mitigation: `--locked` in CI
  turns drift into a red build with an actionable message instead of a silent
  re-resolve.
- *Pinning the lock freezes a `mcp` patch level.* Accepted: that is the point. Updating
  is `uv lock --upgrade-package mcp` plus a green CI run, documented in
  `CONTRIBUTING.md`.
- *A naive container healthcheck would report a healthy server as unhealthy*, because
  `/mcp` rejects a bare GET. Mitigation: ship no `HEALTHCHECK`, and write the CI smoke
  check to assert "an HTTP status was returned", never a specific 200.
- *`docker build` in CI on a repository with no registry push* means the image is
  verified but never published. That is exactly the issue's stated scope; the job is a
  build gate, not a release step.
- *Unprefixed `HOST` / `PORT` may pick up an unrelated ambient value* in a shell or
  PaaS. Mitigation: documented in `.env.example` and `README.md`, and recorded as an
  open question; the names come from the issue and are implemented as specified.
