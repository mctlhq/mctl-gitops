# Repo hygiene and transports: uv.lock, Dockerfile, streamable-http

## Context

Phase 0 of `newton-mcp-gateway` left the repository runnable in exactly one way: a
source checkout, `uv sync` with no lockfile, and the stdio transport hard-coded in
`src/newton_mcp/server.py` (`create_server().run(transport="stdio")`). CI
(`.github/workflows/ci.yml`) installs with a bare `uv sync --group dev`, so every run
re-resolves the dependency graph and a silent upstream release can turn a green build
red — or, worse, green on a different set of packages than the one a contributor
tested against. There is no container image, so the only supported MCP host is a local
Claude Desktop / Claude Code pointed at a checkout via `uv --directory`.

Issue #2 asks for the three things that have to land before more features do: a
committed `uv.lock` that CI installs with `--locked`, a `uv`-based multi-stage
Dockerfile that runs the gateway as a non-root user in mock mode, and a
`NEWTON_MCP_TRANSPORT` setting that lets `server.main()` speak `streamable-http`
instead of stdio so any MCP host can reach the gateway over HTTP. No new dependency is
needed for the HTTP transport: `mcp 2.2.0` — the version the current
`mcp>=2.2,<3` constraint resolves to — already declares `uvicorn>=0.31.1`,
`starlette` and `sse-starlette` as hard requirements, and
`MCPServer.run(transport="streamable-http", host=..., port=...)` is a documented
overload of the API the server already uses. The issue's "do not add a web framework"
rule is therefore satisfiable as written. Alongside this, the README's Claude Desktop
snippet must be verified rather than assumed, and a short `CONTRIBUTING.md` has to
exist so the repo can be read by someone who has not read `AGENTS.md` yet.

## User stories

- AS a maintainer I WANT a committed `uv.lock` that CI installs with `--locked` SO THAT
  a CI failure always means my change broke something, never that an upstream release
  moved under me.
- AS an MCP host operator I WANT to run the gateway as a container over
  streamable-http SO THAT I can reach it from a host that is not a local Claude Desktop
  process on the same machine.
- AS a security reviewer I WANT the container to run as a non-root user and to bind
  `127.0.0.1` by default outside the container SO THAT the default posture is not
  "exposed to every interface as uid 0".
- AS an existing stdio user I WANT the gateway to keep speaking stdio when I set
  nothing SO THAT my existing Claude Desktop configuration keeps working untouched.
- AS a new contributor I WANT a short `CONTRIBUTING.md` SO THAT I know how to set up,
  test and regenerate the JSON schema without reverse-engineering the test suite.

## Acceptance criteria (EARS)

Configuration

- WHEN `Settings.from_env` is called with `NEWTON_MCP_TRANSPORT` unset THE SYSTEM SHALL
  return `transport == "stdio"`.
- WHEN `Settings.from_env` is called with `NEWTON_MCP_TRANSPORT` set to `stdio` or
  `streamable-http` in any letter case or with surrounding whitespace THE SYSTEM SHALL
  return the corresponding normalized lowercase transport value.
- IF `NEWTON_MCP_TRANSPORT` holds any other value THEN THE SYSTEM SHALL raise
  `ValueError` whose message names the variable, the accepted values and the rejected
  value — matching the existing `NEWTON_BACKEND` error style in
  `src/newton_mcp/config.py`.
- WHEN `HOST` is unset THE SYSTEM SHALL default `Settings.host` to `127.0.0.1`; WHEN
  `HOST` is set THE SYSTEM SHALL use its stripped value.
- WHEN `PORT` is unset THE SYSTEM SHALL default `Settings.port` to the integer `8000`.
- IF `PORT` is set to a value that is not an integer in the range 1-65535 THEN THE
  SYSTEM SHALL raise `ValueError` naming `PORT` and the rejected value.
- WHILE `Settings` remains a frozen dataclass THE SYSTEM SHALL keep every existing
  field (`backend`, `api_key`, `api_endpoint`, `text_model`, `omega_model`,
  `request_timeout_sec`) and its current default unchanged.

Server dispatch

- WHEN `newton_mcp.server.main()` runs with `transport == "stdio"` THE SYSTEM SHALL
  call the server's `run` with `transport="stdio"` and SHALL NOT pass `host` or `port`.
- WHEN `newton_mcp.server.main()` runs with `transport == "streamable-http"` THE SYSTEM
  SHALL call the server's `run` with `transport="streamable-http"`, `host` and `port`
  taken from `Settings`.
- WHILE `main()` executes THE SYSTEM SHALL read the environment exactly once and pass
  the resulting `Settings` into `create_server`, so configuration errors surface before
  any backend or transport is constructed.
- IF `Settings.from_env()` raises inside `main()` THEN THE SYSTEM SHALL let the error
  propagate and the process SHALL exit non-zero rather than fall back to a default
  transport.
- WHILE the existing tool surface is unchanged THE SYSTEM SHALL still expose exactly
  `newton_query` and `newton_embed_timeseries`, both annotated `read_only_hint=True`
  (`tests/test_mcp_server.py` stays green and unedited in its existing assertions).

Lockfile and CI

- WHEN CI runs THE SYSTEM SHALL install dependencies with `uv sync --locked --group dev`
  and SHALL fail if `uv.lock` does not match `pyproject.toml`.
- WHILE `uv.lock` is committed THE SYSTEM SHALL keep `.gitignore` free of any pattern
  that would exclude it.
- WHEN CI runs THE SYSTEM SHALL additionally build the image with `docker build .` and
  SHALL fail the job if the build fails.

Container

- WHEN `docker build .` runs at the repository root THE SYSTEM SHALL produce an image
  from a multi-stage `uv` build on a slim Python 3.12 base, with dependencies installed
  from `uv.lock` via `--locked` and without the `dev` group.
- WHEN `docker run -p 8000:8000 <image>` runs with no extra environment THE SYSTEM
  SHALL start the gateway in `NEWTON_BACKEND=mock` over `streamable-http`, listening on
  `0.0.0.0:8000`, and SHALL answer an HTTP request to `/mcp` with an HTTP status code
  rather than refusing the connection.
- WHILE the container runs THE SYSTEM SHALL execute as a non-root user (`id -u` != 0)
  owning no write access to the application directory.
- WHEN the image entrypoint is invoked THE SYSTEM SHALL run the `newton-mcp` console
  script declared in `pyproject.toml`.
- WHILE `.dockerignore` exists THE SYSTEM SHALL exclude at least `.git/`, `.venv/`,
  `__pycache__/`, `.pytest_cache/`, `.env`, `dist/` and `tests/` from the build context.

Documentation

- WHEN a reader follows the Claude Desktop / Claude Code JSON snippet in `README.md`
  THE SYSTEM SHALL start and be usable; IF the snippet as currently written does not
  work THEN THE SYSTEM SHALL have it corrected in the same change, with the reason
  recorded in the PR description.
- WHEN a reader looks for a non-stdio setup THE SYSTEM SHALL offer a README example for
  both `NEWTON_MCP_TRANSPORT=streamable-http` from a checkout and `docker run`, each
  naming the `/mcp` endpoint path.
- WHILE `README.md` describes the container THE SYSTEM SHALL state that binding
  `0.0.0.0` is intended for a container network and that the gateway ships no
  authentication, so exposing it to an untrusted network is the operator's
  responsibility.
- WHEN `CONTRIBUTING.md` is read THE SYSTEM SHALL cover setup, running tests, JSON
  schema regeneration for `schemas/physical-action-contract.schema.json`, and SHALL
  point at `AGENTS.md` for the hard rules rather than restating them.
- WHILE any documentation is edited THE SYSTEM SHALL preserve the repo's existing
  wording rules: mock output stays labelled, the live Newton integration stays
  "mock-validated", and the Physical Action Contract stays this project's proposal.

## Out of scope

- New MCP tools, changes to `newton_query` / `newton_embed_timeseries`, or any change
  to the `NewtonBackend` protocol, `MockNewtonBackend` or `ArchetypeNewtonBackend`.
- The action runtime, capability resolver and verifier (`src/newton_mcp/action/` stays
  as-is beyond documenting how to regenerate its schema).
- The `sse` transport, even though `mcp 2.2.0` supports it. Only `stdio` and
  `streamable-http` are accepted values.
- Authentication, TLS, reverse proxy configuration or DNS-rebinding hardening beyond
  the defaults `mcp` applies.
- Publishing the image to any registry, release automation, version bumping, and
  multi-architecture builds.
- Adding a web framework, ASGI app factory, or any HTTP route the `mcp` library does
  not already mount.
- Repository URLs, schema `$id` and the LICENSE holder — already fixed in #17.

## Open questions

- `HOST` and `PORT` are unprefixed and can collide with unrelated variables already
  present in a shell or a PaaS environment; every other project-specific variable in
  `.env.example` is prefixed (`NEWTON_*`). The issue specifies the bare names, so this
  proposal implements them exactly as specified and records the collision risk here.
  If a reviewer prefers, `NEWTON_MCP_HOST` / `NEWTON_MCP_PORT` could be read as a
  higher-precedence override in a follow-up; not doing it now keeps the change minimal.
- `mcp 2.2.0` auto-enables DNS-rebinding protection only when the bind host is
  `127.0.0.1`, `localhost` or `::1`. The container's `0.0.0.0` bind therefore runs
  without it, which is what makes the container reachable at all. This proposal
  documents the exposure rather than passing custom `TransportSecuritySettings`, since
  the issue asks for no auth story. Flagged for reviewer confirmation.
- The issue's acceptance criterion says `docker run` must start "over streamable-http",
  while the transport default is `stdio`. This proposal resolves it by having the
  Dockerfile set `NEWTON_MCP_TRANSPORT=streamable-http`, `HOST=0.0.0.0`,
  `PORT=8000` and `NEWTON_BACKEND=mock` as image-level `ENV` defaults, all
  overridable with `docker run -e`. The library default stays `stdio`.
- A container `HEALTHCHECK` is not specified by the issue. `/mcp` requires a
  protocol-correct POST, so a naive `curl` healthcheck would report unhealthy on a
  working server. This proposal ships no `HEALTHCHECK`; a reviewer may ask for a TCP
  probe instead.
- `mcp 2.2.0` depends on `httpx2>=2.5.0` while this repo depends on `httpx>=0.27,<1`
  for `ArchetypeNewtonBackend`. They are separate distributions and coexist, so
  `uv.lock` will legitimately contain both. No action needed; noted so the lockfile
  diff is not mistaken for a mistake.
