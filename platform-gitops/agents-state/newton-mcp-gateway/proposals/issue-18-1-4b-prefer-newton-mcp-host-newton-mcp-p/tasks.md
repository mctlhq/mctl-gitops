# Tasks: issue-18-1-4b-prefer-newton-mcp-host-newton-mcp-p

- [ ] 1. Add the precedence helper and the name tuples to `src/newton_mcp/config.py`:
      module-level `HOST_VARS = ("NEWTON_MCP_HOST", "HOST")` and
      `PORT_VARS = ("NEWTON_MCP_PORT", "PORT")`, plus a private
      `_resolve(env, names, default) -> tuple[str, str]` returning
      `(source_variable_name, stripped_value)` for the first candidate whose value is
      present and not whitespace-only, falling back to `(names[0], default)`.
      — DoD: helper is fully type-hinted, has a docstring stating that blank means
      "not supplied", is not exported in any `__all__`, and `uv run pytest -q` still
      passes with the existing suite untouched.

- [ ] 2. Rewrite the host/port block of `Settings.from_env()` (currently
      `config.py` lines 47-54) to use `_resolve` (depends on 1). Host: discard the
      source name. Port: keep it and interpolate it into both `ValueError` messages
      in place of the hardcoded `"PORT"`, so they read
      `f"{port_var} must be an integer, got {port_raw!r}"` and
      `f"{port_var} must be in 1-65535, got {port}"`.
      — DoD: `Settings` field names and types are unchanged (`host: str`,
      `port: int`); `src/newton_mcp/server.py` and `tests/conftest.py` are not
      modified; the two pre-existing `match="PORT"` assertions in
      `tests/test_config.py::test_invalid_port_raises` still pass unchanged.

- [ ] 3. Update the module docstring at the top of `config.py` to state the naming
      rule: project-owned variables are `NEWTON_*`-prefixed, `NEWTON_MCP_HOST` /
      `NEWTON_MCP_PORT` are preferred with bare `HOST` / `PORT` retained as a
      lower-precedence fallback, and `ATAI_API_KEY` / `ATAI_API_ENDPOINT` stay
      unprefixed because Archetype's docs define them (depends on 2).
      — DoD: docstring mentions both new names and the fallback, and contradicts
      nothing in `AGENTS.md`.

- [ ] 4. Update the `Dockerfile` runtime-stage `ENV` block: replace `HOST=0.0.0.0`
      with `NEWTON_MCP_HOST=0.0.0.0` and `PORT=8000` with `NEWTON_MCP_PORT=8000`.
      Leave `NEWTON_BACKEND=mock`, `NEWTON_MCP_TRANSPORT=streamable-http`,
      `EXPOSE 8000`, `USER newton` and the `ENTRYPOINT` untouched.
      — DoD: `docker build -t newton-mcp-gateway:local .` succeeds and
      `docker run --rm -p 8000:8000 newton-mcp-gateway:local` answers on
      `http://127.0.0.1:8000/mcp` with a non-`000` HTTP status.

- [ ] 5. Update `.env.example`: rename the trailing block to
      `NEWTON_MCP_HOST=127.0.0.1` / `NEWTON_MCP_PORT=8000`, and replace the existing
      "these are unprefixed and can collide with unrelated ambient variables" comment
      with the new rule — prefixed names win, bare `HOST` / `PORT` still work as a
      fallback, `HOST` collides with zsh's own `HOST` parameter, and the image sets
      `NEWTON_MCP_HOST=0.0.0.0`.
      — DoD: no bare `HOST=` or `PORT=` assignment remains in the file; the
      `NEWTON_BACKEND`, `ATAI_*`, model and `NEWTON_MCP_TRANSPORT` blocks are
      byte-identical to before.

- [ ] 6. Update `README.md` and `CONTRIBUTING.md` (depends on 4). In `README.md`,
      change the streamable-http example command to use `NEWTON_MCP_PORT=8000`. In
      `CONTRIBUTING.md`, change the `streamable-http` table row to name
      `NEWTON_MCP_HOST` / `NEWTON_MCP_PORT` (default `127.0.0.1:8000`) and note the
      bare fallback, and change the image-override paragraph to
      `NEWTON_MCP_HOST=0.0.0.0`, `NEWTON_MCP_PORT=8000`. Then re-grep the whole tree
      for `\bHOST\b` and `\bPORT\b` and confirm the only survivors are the intentional
      fallback mentions in `config.py`, `.env.example`, `CONTRIBUTING.md` and the
      tests.
      — DoD: grep output reviewed and clean; `docs/architecture.md` and
      `.github/workflows/ci.yml` remain unmodified; the README's
      "ships no authentication" warning is unchanged.

- [ ] 7. Add the tests below to `tests/test_config.py` (depends on 2) and run
      `uv sync --locked --group dev && uv run pytest -q`.
      — DoD: full suite green, no existing test deleted or weakened, `uv.lock` and
      `pyproject.toml` unmodified.

## Tests

All tests go in `tests/test_config.py` and use the existing injectable-dict style
(`Settings.from_env({...})`) — never `monkeypatch.setenv`, so nothing depends on the
ambient process environment.

- [ ] T1. `test_prefixed_host_and_port_win_over_bare`:
      `from_env({"NEWTON_MCP_HOST": "0.0.0.0", "HOST": "evil.example", "NEWTON_MCP_PORT": "9100", "PORT": "1"})`
      yields `host == "0.0.0.0"` and `port == 9100`.
- [ ] T2. `test_prefixed_host_and_port_alone`:
      `from_env({"NEWTON_MCP_HOST": "0.0.0.0", "NEWTON_MCP_PORT": "9001"})` yields
      `host == "0.0.0.0"`, `port == 9001`, `isinstance(port, int)`.
- [ ] T3. `test_bare_host_and_port_still_work`: the pre-existing
      `test_host_and_port_overrides` behaviour is preserved —
      `from_env({"HOST": "0.0.0.0", "PORT": "9001"})` yields `0.0.0.0` / `9001`.
      Keep the original test as-is and add this only if it strengthens the assertion
      (e.g. asserting the bare names still win when no prefixed name is set at all).
- [ ] T4. `test_blank_prefixed_falls_through_to_bare`:
      `from_env({"NEWTON_MCP_HOST": "  ", "HOST": "0.0.0.0", "NEWTON_MCP_PORT": "", "PORT": "9002"})`
      yields `host == "0.0.0.0"` and `port == 9002`.
- [ ] T5. `test_blank_everywhere_uses_defaults`:
      `from_env({"NEWTON_MCP_HOST": "", "HOST": "", "NEWTON_MCP_PORT": "", "PORT": ""})`
      yields `host == "127.0.0.1"` and `port == 8000`. This pins the one intentional
      behaviour change (blank `PORT` no longer raises).
- [ ] T6. `test_port_error_names_the_supplying_variable`: four cases —
      `{"NEWTON_MCP_PORT": "eighty"}` raises `ValueError` matching
      `r"^NEWTON_MCP_PORT must be an integer"`; `{"PORT": "eighty"}` raises matching
      `r"^PORT must be an integer"`; `{"NEWTON_MCP_PORT": "0"}` and
      `{"NEWTON_MCP_PORT": "70000"}` raise matching
      `r"^NEWTON_MCP_PORT must be in 1-65535"`. Use anchored patterns so the prefixed
      and bare messages cannot be confused for each other.
- [ ] T7. `test_prefixed_port_error_wins_over_valid_bare`:
      `from_env({"NEWTON_MCP_PORT": "nope", "PORT": "8000"})` raises naming
      `NEWTON_MCP_PORT` — the precedence winner is validated, not silently skipped in
      favour of the valid fallback.
- [ ] T8. Regression: `test_transport_and_network_defaults`,
      `test_host_and_port_overrides` and `test_invalid_port_raises` pass unmodified.
- [ ] T9. Container check (manual / CI): `docker build` then
      `docker run --rm -p 8000:8000 <image>` serves `/mcp`, i.e. the unchanged
      `.github/workflows/ci.yml` docker job stays green with the renamed `ENV` entries.

## Rollback

The change is confined to six files — `src/newton_mcp/config.py`,
`tests/test_config.py`, `Dockerfile`, `.env.example`, `README.md`,
`CONTRIBUTING.md` — with no dependency, lockfile, schema or generated-artifact
change, so `git revert <merge-commit>` on `main` restores the previous behaviour
completely and needs no follow-up step.

Partial rollback options, if only one symptom shows up:

- Bind address wrong in the container only: re-add `HOST=0.0.0.0` and `PORT=8000`
  to the `Dockerfile` `ENV` block, or start the container with
  `-e HOST=0.0.0.0 -e PORT=8000`. The bare fallback still resolves, so this works
  against the new code without touching `config.py`.
- Precedence itself is the problem: reorder `HOST_VARS` / `PORT_VARS` in
  `config.py` to put the bare names first. One-line change, no other edits.
- Blank-`PORT` defaulting is judged unacceptable: drop `""` from the port
  candidate set by passing the raw (unstripped-for-emptiness) value through for
  `PORT_VARS` only, and delete T5. This is the only behaviour delta that a
  deployment could depend on.

Nothing is persisted and no external system is mutated, so there is no data or state
to reconcile after a revert. Operators who had already switched to the prefixed names
would need to switch back to `HOST` / `PORT`; that is the only operator-visible
consequence of a rollback.
