# Design: issue-18-1-4b-prefer-newton-mcp-host-newton-mcp-p

## Current state

Configuration is a single frozen dataclass, `Settings`, in
`src/newton_mcp/config.py`. There is no settings framework — `Settings.from_env()`
is a classmethod that reads a `dict[str, str]` (defaulting to `os.environ`) and
returns the dataclass. That injectable `env` argument is what makes the existing
tests in `tests/test_config.py` pure and fast; every test calls
`Settings.from_env({...})` with an explicit dict, never touching the process
environment.

The two fields this issue is about are declared at `config.py` lines 30-31:

```python
host: str = "127.0.0.1"
port: int = 8000
```

and resolved at lines 47-54:

```python
host = env.get("HOST", "127.0.0.1").strip() or "127.0.0.1"
port_raw = env.get("PORT", "8000").strip()
try:
    port = int(port_raw)
except ValueError:
    raise ValueError(f"PORT must be an integer, got {port_raw!r}") from None
if not 1 <= port <= 65535:
    raise ValueError(f"PORT must be in 1-65535, got {port}")
```

Two details matter. First, the `or "127.0.0.1"` on the host line means a blank
`HOST` already falls back to the default; the port line has no equivalent, so a
blank `PORT` reaches `int("")` and raises `PORT must be an integer, got ''`.
Second, both branches hardcode the variable name in the error string, which is
correct only while exactly one variable can supply the value.

Every other project-owned variable read in the same method is already namespaced:
`NEWTON_BACKEND` (line 36), `NEWTON_MCP_TRANSPORT` (line 42), `NEWTON_TEXT_MODEL`
(line 59), `NEWTON_OMEGA_MODEL` (line 60), `NEWTON_REQUEST_TIMEOUT_SEC` (line 61).
Only `ATAI_API_KEY` / `ATAI_API_ENDPOINT` are deliberately unprefixed, because
`AGENTS.md` requires them to match Archetype's published names. `HOST` / `PORT` are
the sole project-owned exception, and `HOST` is the one that collides with a zsh
built-in parameter.

The only consumer of these fields is `main()` in `src/newton_mcp/server.py`
lines 119-125:

```python
if settings.transport == "streamable-http":
    server.run(transport="streamable-http", host=settings.host, port=settings.port)
else:
    server.run(transport="stdio")
```

`create_server()` never reads `host`/`port`, and `tests/conftest.py` builds
`Settings()` with all defaults, so nothing else in the tree depends on how these
two values are sourced.

The names also appear in four non-code places:

- `Dockerfile` runtime stage `ENV` block: `HOST=0.0.0.0`, `PORT=8000`, alongside
  `NEWTON_BACKEND=mock` and `NEWTON_MCP_TRANSPORT=streamable-http`.
- `.env.example`: a trailing block whose comment explicitly flags the problem
  ("These are unprefixed and can collide with unrelated ambient variables").
- `README.md` line 76: `NEWTON_BACKEND=mock NEWTON_MCP_TRANSPORT=streamable-http PORT=8000 uv run newton-mcp`.
- `CONTRIBUTING.md` lines 33 and 35-36: the transport table row "binds `HOST`/`PORT`
  (default `127.0.0.1:8000`)" and the paragraph describing the image-level overrides.

`docs/architecture.md` mentions no bind address and needs no change.
`.github/workflows/ci.yml` starts the container with `docker run -d -p 8000:8000`
and polls `http://127.0.0.1:8000/mcp`; it relies on the image's `ENV` defaults but
never names `HOST` or `PORT` itself, so it is an unchanged end-to-end check that the
renamed `ENV` entries still produce a `0.0.0.0:8000` bind.

## Proposed solution

Add one small private helper to `config.py` that resolves a value from an ordered
list of candidate variable names and reports *which* name supplied it. Keeping the
source name is the whole point: it is what lets the port validation errors satisfy
the issue's second acceptance criterion.

```python
def _resolve(env: dict[str, str], names: tuple[str, ...], default: str) -> tuple[str, str]:
    """Return (source_variable_name, stripped_value) for the first non-blank candidate.

    Blank and whitespace-only values are treated as "not supplied" so a blank
    prefixed variable falls through to the bare fallback and then to the default.
    When nothing is supplied, the first (preferred) name is reported as the source
    so that any downstream message names the variable an operator should set.
    """
    for name in names:
        raw = env.get(name)
        if raw is not None and raw.strip():
            return name, raw.strip()
    return names[0], default
```

`from_env()` then becomes:

```python
HOST_VARS = ("NEWTON_MCP_HOST", "HOST")
PORT_VARS = ("NEWTON_MCP_PORT", "PORT")

_, host = _resolve(env, HOST_VARS, "127.0.0.1")
port_var, port_raw = _resolve(env, PORT_VARS, "8000")
try:
    port = int(port_raw)
except ValueError:
    raise ValueError(f"{port_var} must be an integer, got {port_raw!r}") from None
if not 1 <= port <= 65535:
    raise ValueError(f"{port_var} must be in 1-65535, got {port}")
```

The tuples are module-level constants so the docs, the tests and any future issue
have a single place to read the precedence order from. Host needs no validation
beyond the strip, so its source name is discarded with `_` — an explicit marker that
the helper's two-value return is used asymmetrically on purpose, rather than an
oversight.

Why a helper rather than inline `env.get("NEWTON_MCP_HOST") or env.get("HOST") or ...`:
the naive chained-`or` form loses the source name, which is exactly what the error
messages need, and it silently mishandles whitespace-only values. The helper is nine
lines, has no dependencies, and keeps `from_env()` shorter than it is today. This
matches the repo's stated preference in `AGENTS.md` for "small, explicit code over
frameworks".

`Settings`' public shape is unchanged: fields stay `host: str` and `port: int`, so
`server.py` `main()`, `tests/conftest.py`'s `Settings()` fixture and every existing
call site compile and behave identically. Nothing new is added to the frozen
dataclass — in particular no `host_source` / `port_source` fields, which would leak
an implementation detail into a public type for no consumer's benefit.

Error-message compatibility is preserved by construction: the two existing
assertions `pytest.raises(ValueError, match="PORT")` in
`tests/test_config.py::test_invalid_port_raises` use a regex *search*, and
`"PORT"` is a substring of `"NEWTON_MCP_PORT"`, so those tests pass whichever
variable supplied the bad value. New tests will assert the precise name.

Non-code changes, all mechanical:

- `Dockerfile`: `HOST=0.0.0.0 \ PORT=8000` becomes
  `NEWTON_MCP_HOST=0.0.0.0 \ NEWTON_MCP_PORT=8000`. `EXPOSE 8000` is unchanged.
- `.env.example`: the trailing block is rewritten to `NEWTON_MCP_HOST=127.0.0.1` /
  `NEWTON_MCP_PORT=8000`, and its comment is rewritten from "these are unprefixed and
  can collide" to a statement of the new rule: prefixed names are preferred, the bare
  `HOST` / `PORT` remain a lower-precedence fallback, and `HOST` in particular
  collides with zsh's `HOST` parameter — which is why the prefixed name exists.
- `README.md` line 76: `PORT=8000` becomes `NEWTON_MCP_PORT=8000`.
- `CONTRIBUTING.md`: the transport table row becomes "binds `NEWTON_MCP_HOST` /
  `NEWTON_MCP_PORT` (default `127.0.0.1:8000`; bare `HOST` / `PORT` still accepted as
  a fallback)", and the image-override paragraph names
  `NEWTON_MCP_HOST=0.0.0.0`, `NEWTON_MCP_PORT=8000`.

No other file in the tree references these names.

## Alternatives

**Rename outright and drop `HOST` / `PORT`.** Smallest diff and no precedence logic
at all, but it breaks the `docker run` and `uv run` invocations that issue #2 just
documented, and any operator who copied them. The issue explicitly asks to keep the
bare names as a fallback, so this is ruled out by scope.

**Keep `PORT` as the preferred name and only prefix the host.** `PORT` is a genuine
PaaS convention, and `PORT` has no shell collision, so one could argue only `HOST`
is broken. Dropped for two reasons: asymmetric naming for a single logical setting
(`NEWTON_MCP_HOST` plus `PORT`) is exactly the inconsistency this issue exists to
remove, and the issue's scope names both variables. The PaaS convention is still
honoured — `PORT` remains a working fallback.

**Adopt `pydantic-settings` with `AliasChoices`.** It expresses "prefixed wins, bare
falls back" declaratively and would also cover the unguarded
`float(env["NEWTON_REQUEST_TIMEOUT_SEC"])`. Dropped: it adds a runtime dependency and
a lockfile churn for a nine-line helper, it would rewrite the whole `Settings` class
and every test in `tests/test_config.py` in a change that is supposed to be a
precedence tweak, and its validation errors are `ValidationError` rather than the
`ValueError` the current tests and `main()` expect. `AGENTS.md`'s "small, explicit
code over frameworks" points the same way. Worth revisiting as its own issue if
config grows.

**Read only `os.environ` and resolve precedence at process start in `server.py`.**
Would keep `config.py` untouched, but it moves configuration logic out of the one
module that owns it, and it defeats the injectable-`env` testing style the existing
suite depends on.

## Platform impact

**Migrations.** None in the platform sense — no database, no persisted state, no
GitOps values change. `newton-mcp-gateway` is a library-plus-CLI repo; nothing in
`platform-gitops` deploys it today.

**Backward compatibility.** Existing `HOST` / `PORT` deployments keep working
unchanged; that is the fallback's entire purpose. Two behaviour deltas are worth a
reviewer's attention:

1. *Blank `PORT` now defaults instead of raising.* Today `PORT=""` produces
   `ValueError: PORT must be an integer, got ''`; after this change it falls back to
   `8000`, matching how blank `HOST` already behaves. This is required for
   "blank prefixed value falls through", and it removes an asymmetry, but it does
   trade a loud failure for a silent default in one narrow case. Mitigation: the
   fall-through order is documented in `.env.example` and `CONTRIBUTING.md`, and a
   dedicated test pins the new behaviour so it is deliberate rather than incidental.
2. *A container that previously received `HOST` from the image `ENV` now receives
   `NEWTON_MCP_HOST`.* An operator who overrides only `-e HOST=...` against the new
   image still wins, because the image no longer sets the prefixed name — the bare
   override is the highest-precedence value actually present. An operator who sets
   *both* gets the prefixed one, which is the documented rule.

**Resource impact.** Zero. No new dependency, no new I/O, no change to `uv.lock`,
no change to image size or layer count (the `ENV` block keeps the same number of
entries). `Settings.from_env()` gains at most two extra dict lookups.

**Risks and mitigations.**

- *Risk:* a docs surface is missed and keeps advertising a bare name, leaving the
  repo internally inconsistent. *Mitigation:* the changed set is closed and was
  enumerated by grep — `Dockerfile`, `.env.example`, `README.md`, `CONTRIBUTING.md`;
  `docs/architecture.md` and `.github/workflows/ci.yml` contain no occurrences. Task 6
  re-greps for `\bHOST\b` / `\bPORT\b` as a completion check.
- *Risk:* the Docker `ENV` rename breaks the container's HTTP bind. *Mitigation:* the
  existing CI "Smoke-check streamable-http listens on /mcp" job already boots the
  image and polls `http://127.0.0.1:8000/mcp`; it is untouched and fails loudly if the
  renamed `ENV` entries do not produce the same bind.
- *Risk:* an operator sets both variables to different values and is surprised by
  which one wins. *Mitigation:* the port validation error names the winning variable,
  and precedence is stated in `CONTRIBUTING.md` and `.env.example`.
- *Risk:* precedence regresses in a later refactor. *Mitigation:* the precedence
  tuples are named module constants and the test matrix (T1-T6) covers prefixed-wins,
  bare-fallback, both-set, blank-fall-through and defaults explicitly.

**Security.** Neutral to slightly positive. The concrete pre-change hazard is a
streamable-http process inheriting an ambient `HOST` and binding to a hostname —
i.e. a routable interface — instead of `127.0.0.1`. Preferring a namespaced variable
removes that accidental-wide-bind path. The gateway still ships no authentication;
the README's warning about exposing it to untrusted networks stands verbatim and is
not weakened or expanded by this change.

**Hard-rule compliance.** No Archetype endpoint, parameter or model id is invented or
touched; `ATAI_API_KEY` / `ATAI_API_ENDPOINT` keep their documented unprefixed names
per `AGENTS.md`. Mock labelling is untouched. No Physical Action Contract wording
changes. No Temporal, Kubernetes, DB, auth platform or UI is introduced. No mctl.ai
reference is added to the repo. Every new behaviour is covered by a test, in Pydantic
v2 / typed-code style consistent with the existing module.
