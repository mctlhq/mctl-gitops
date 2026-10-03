# Tasks: issue-2-1-4-repo-hygiene-and-transports-uv-lock

- [ ] 1. Generate and commit `uv.lock` with `uv lock`, then confirm
      `uv sync --locked --group dev && uv run pytest -q` passes on a clean checkout —
      DoD: `uv.lock` is tracked by git, `.gitignore` still does not exclude it, and the
      locked sync installs `mcp 2.2.x` (which brings `uvicorn`, `starlette`,
      `sse-starlette` transitively, so no dependency is added to `pyproject.toml`).
      `pyproject.toml` is not edited by this task.

- [ ] 2. Add transport settings to `src/newton_mcp/config.py` (depends on 1) — DoD: a
      module-level `Transport = Literal["stdio", "streamable-http"]` alias next to the
      existing `Backend` alias; `Settings` gains `transport: Transport = "stdio"`,
      `host: str = "127.0.0.1"`, `port: int = 8000`, all defaulted so `Settings()` in
      `tests/conftest.py` keeps working; `from_env` parses `NEWTON_MCP_TRANSPORT` with
      `.strip().lower()` and raises `ValueError` naming the variable, the accepted
      values and the rejected value on anything else; `HOST` is stripped and falls back
      to `127.0.0.1` when empty; `PORT` is parsed with a `try/except ValueError` that
      re-raises a message naming `PORT`, and is range-checked to 1-65535. The existing
      six fields and their defaults are unchanged.

- [ ] 3. Dispatch on transport in `newton_mcp.server.main()` (depends on 2) — DoD:
      `main()` calls `Settings.from_env()` once, passes the result into
      `create_server(settings)`, calls `server.run(transport="stdio")` with no other
      kwargs for stdio, and
      `server.run(transport="streamable-http", host=settings.host, port=settings.port)`
      for streamable-http. `create_server`'s signature, the lifespan, both tool
      definitions and their `read_only_hint` annotations are untouched.

- [ ] 4. Add `.dockerignore` (depends on 1) — DoD: excludes `.git/`, `.github/`,
      `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.env`, `dist/`, `tests/`,
      `docs/`, `examples/`, and `*.md` with a `!README.md` re-include (hatchling needs
      the readme named in `pyproject.toml`).

- [ ] 5. Add the multi-stage `Dockerfile` (depends on 1, 3, 4) — DoD: builder stage on
      `python:3.12-slim` with the `uv` binary copied from a pinned
      `ghcr.io/astral-sh/uv:<version>` image; `UV_COMPILE_BYTECODE=1`,
      `UV_LINK_MODE=copy`; dependency layer via
      `uv sync --locked --no-dev --no-install-project` before `src/` is copied, then
      `uv sync --locked --no-dev`. Runtime stage on the same base, non-root user
      created with `useradd`, `COPY --from=builder` of `/app/.venv` only, **root-owned
      (no `--chown`)**, followed by `RUN chmod -R go-w /app` (no `uv` in the runtime
      image), `ENV PATH="/app/.venv/bin:$PATH"`,
      `PYTHONUNBUFFERED=1`, `NEWTON_BACKEND=mock`,
      `NEWTON_MCP_TRANSPORT=streamable-http`, `HOST=0.0.0.0`, `PORT=8000`,
      `EXPOSE 8000`, `USER <user>`, `ENTRYPOINT ["newton-mcp"]`. No `HEALTHCHECK`.

- [ ] 6. Update `.github/workflows/ci.yml` (depends on 1, 5) — DoD: the `test` job's
      install step is `uv sync --locked --group dev`; a second independent `docker` job
      builds the image and runs the image assertions from T7, T7b and T8. Both jobs are
      green on the PR.

- [ ] 7. Add `NEWTON_MCP_TRANSPORT`, `HOST` and `PORT` to `.env.example` (depends on 2)
      — DoD: the three variables are present with the file's existing commented style,
      documenting the defaults (`stdio`, `127.0.0.1`, `8000`) and noting that the
      container image overrides transport and host.

- [ ] 8. Verify and extend `README.md` (depends on 3, 5) — DoD: the existing Claude
      Desktop / Claude Code JSON snippet was actually executed
      (`uv --directory <path> run newton-mcp`) and either confirmed working verbatim or
      corrected, with the finding stated in the PR description; a new short section
      shows the checkout streamable-http command and the `docker build` /
      `docker run -p 8000:8000` pair, both naming the `/mcp` endpoint path; one
      sentence states that the container binds `0.0.0.0` for the container network,
      ships no authentication, and must not face an untrusted network unproxied. The
      "mock-validated" status wording, the mock-labelling statement and the
      "this project's proposal" framing of the Physical Action Contract are all
      preserved.

- [ ] 9. Add `CONTRIBUTING.md` (depends on 1, 3) — DoD: covers setup
      (`uv sync --group dev`), tests (`uv run pytest`), how to refresh the lock
      (`uv lock`, `uv lock --upgrade-package <name>`), the two transports and their
      env vars, and regeneration of
      `schemas/physical-action-contract.schema.json` from
      `PhysicalActionContract.model_json_schema()` with the reason (the equality
      assertion in `tests/test_action_contract.py`). Hard rules are a pointer to
      `AGENTS.md`, not a copy.

## Tests

- [ ] T1. `tests/test_config.py`: `Settings.from_env({})` yields
      `transport == "stdio"`, `host == "127.0.0.1"`, `port == 8000`, and the three
      existing assertions in the file still pass unchanged.
- [ ] T2. `tests/test_config.py`: `{"NEWTON_MCP_TRANSPORT": " Streamable-HTTP "}`
      normalizes to `"streamable-http"`; `{"NEWTON_MCP_TRANSPORT": "stdio"}` stays
      `"stdio"`.
- [ ] T3. `tests/test_config.py`: `pytest.raises(ValueError, match="NEWTON_MCP_TRANSPORT")`
      for `{"NEWTON_MCP_TRANSPORT": "websocket"}` — asserts the message names the
      variable, not just that something raised.
- [ ] T4. `tests/test_config.py`: `{"HOST": "0.0.0.0", "PORT": "9001"}` yields
      `host == "0.0.0.0"` and `port == 9001` as an `int`; `{"HOST": ""}` falls back to
      `127.0.0.1`.
- [ ] T5. `tests/test_config.py`: `pytest.raises(ValueError, match="PORT")` for
      `{"PORT": "eighty"}` and for `{"PORT": "0"}` and `{"PORT": "70000"}`.
- [ ] T6. `tests/test_mcp_server.py`: `main()` with the server's `run` mocked
      (monkeypatch `MCPServer.run` to record `(transport, kwargs)`) and a patched
      environment dispatches to `("stdio", {})` when `NEWTON_MCP_TRANSPORT` is unset,
      and to `("streamable-http", {"host": ..., "port": ...})` carrying the values from
      `HOST` / `PORT` when it is set. Both cases assert the stdio call passes no `host`
      or `port`. No socket is opened and no real transport starts.
- [ ] T7. CI image assertion: `docker run --rm --entrypoint id <image> -u` prints a
      non-zero uid.
- [ ] T7b. CI image assertion: running as the image's default (non-root) user,
      `docker run --rm --entrypoint sh <image> -c 'touch /app/.venv/.w'` FAILS
      (non-zero exit), and `stat -c %U /app/.venv` prints `root` — the runtime user has
      no write access to the application directory.
- [ ] T8. CI smoke check: start the image with `-d -p 8000:8000`, poll
      `http://127.0.0.1:8000/mcp` until an HTTP status code is returned (not a
      connection refusal), then stop the container. The check asserts that a status was
      returned, never that it is 200 — a bare GET to `/mcp` is not a valid MCP request
      and legitimately answers 4xx.
- [ ] T9. Regression: the full `uv run pytest -q` suite, including
      `tests/test_action_contract.py`'s schema-sync assertion and the existing
      `tests/test_mcp_server.py` tool-surface and `read_only_hint` assertions, is green
      after every change.

## Rollback

Every change is additive and confined to one PR, so `git revert` of the merge commit
restores the previous state completely — there is no persistent state, no wire format
and no published artifact to unwind.

Partial rollbacks, in decreasing likelihood:

- *Transport regression.* Users are unaffected by default: with `NEWTON_MCP_TRANSPORT`
  unset, `main()` takes the same stdio path as today. Anyone hitting a problem unsets
  the variable and is back on the previous behaviour with no redeploy.
- *Container problems.* Delete or stop the container; the checkout-based stdio and
  streamable-http paths are independent of it. Reverting `Dockerfile` and
  `.dockerignore` alone leaves tasks 1-3 intact and working.
- *Lockfile problems.* Revert `.github/workflows/ci.yml` to `uv sync --group dev` to
  unblock CI immediately without deleting `uv.lock`, then fix the lock separately. If
  the lock itself resolved something broken, `uv lock --upgrade-package <name>` and
  re-commit rather than deleting the file.
- *Docs only.* `README.md`, `CONTRIBUTING.md` and `.env.example` carry no runtime
  behaviour and can be reverted in isolation at any time.
