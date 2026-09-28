# Prefer NEWTON_MCP_HOST / NEWTON_MCP_PORT over bare HOST / PORT

## Context

`Settings.from_env()` in `src/newton_mcp/config.py` reads the streamable-http bind
address from the unprefixed variables `HOST` (line 47) and `PORT` (lines 48-54).
`PORT` is a widely used PaaS convention, but `HOST` is a reserved parameter in zsh
that holds the machine hostname. If a developer's shell exports it — or any tool in
the environment sets it — `newton-mcp` with `NEWTON_MCP_TRANSPORT=streamable-http`
binds to that hostname instead of the intended `127.0.0.1`, which is a silent and
confusing failure (and potentially a wider bind than the operator asked for). Every
other project-owned variable in the repo is already namespaced: `NEWTON_BACKEND`,
`NEWTON_MCP_TRANSPORT`, `NEWTON_TEXT_MODEL`, `NEWTON_OMEGA_MODEL`,
`NEWTON_REQUEST_TIMEOUT_SEC`. The bind address is the only exception.

This proposal adds `NEWTON_MCP_HOST` and `NEWTON_MCP_PORT` as the preferred names,
resolved with higher precedence than the bare `HOST` / `PORT`, and keeps the bare
names working as a fallback so that the Docker `ENV` block, the README command line
and any existing operator setup from issue #2 are not broken. Because two variables
can now supply the same setting, the validation errors must name the variable that
actually supplied the rejected value, so an operator can tell which one to fix. The
project's own surfaces — `Dockerfile`, `.env.example`, `README.md`,
`CONTRIBUTING.md` — switch to the prefixed names. Nothing about transport
selection, authentication or network topology changes.

## User stories

- AS a developer running the gateway from a zsh shell I WANT the bind host to come
  from `NEWTON_MCP_HOST` SO THAT my shell's ambient `HOST` parameter cannot silently
  change which interface the server listens on.
- AS an operator who already deployed the container or scripts from issue #2 with
  `HOST` / `PORT` I WANT those names to keep working SO THAT upgrading the gateway
  does not require me to change my deployment in the same step.
- AS an operator who mistyped a port value I WANT the error message to name the exact
  variable I set SO THAT I do not have to guess which of two variables the gateway
  actually read.
- AS a contributor reading the repo's docs I WANT one consistent, prefixed naming
  convention SO THAT I do not have to remember which settings are namespaced.

## Acceptance criteria (EARS)

- WHEN `NEWTON_MCP_HOST` is set to a non-blank value THE SYSTEM SHALL use it as
  `Settings.host`, regardless of whether `HOST` is also set.
- WHEN `NEWTON_MCP_HOST` is absent or blank AND `HOST` is set to a non-blank value
  THE SYSTEM SHALL use `HOST` as `Settings.host`.
- WHEN neither `NEWTON_MCP_HOST` nor `HOST` supplies a non-blank value THE SYSTEM
  SHALL use the default `Settings.host` of `127.0.0.1`.
- WHEN `NEWTON_MCP_PORT` is set to a non-blank value THE SYSTEM SHALL use it as
  `Settings.port`, regardless of whether `PORT` is also set.
- WHEN `NEWTON_MCP_PORT` is absent or blank AND `PORT` is set to a non-blank value
  THE SYSTEM SHALL use `PORT` as `Settings.port`.
- WHEN neither `NEWTON_MCP_PORT` nor `PORT` supplies a non-blank value THE SYSTEM
  SHALL use the default `Settings.port` of `8000`.
- WHILE resolving host and port THE SYSTEM SHALL strip surrounding whitespace from
  the raw value before using it, preserving the current behaviour of
  `config.py` lines 47-48.
- WHILE resolving host and port THE SYSTEM SHALL treat a value that is empty or
  whitespace-only as not supplied, and fall through to the next candidate variable
  and then to the default.
- IF the value that won precedence for the port is not parseable as an integer THEN
  THE SYSTEM SHALL raise `ValueError` whose message names the winning variable
  (`NEWTON_MCP_PORT` or `PORT`) and echoes the rejected raw value.
- IF the value that won precedence for the port parses as an integer outside
  `1..65535` THEN THE SYSTEM SHALL raise `ValueError` whose message names the
  winning variable and echoes the rejected value.
- WHILE `Settings.port` is valid THE SYSTEM SHALL expose it as a Python `int`, as
  `tests/test_config.py::test_host_and_port_overrides` already asserts.
- WHEN the field names of `Settings` are read by callers THE SYSTEM SHALL keep them
  as `host` and `port`, so `main()` in `src/newton_mcp/server.py` (lines 122-125)
  needs no change.
- WHILE `NEWTON_MCP_TRANSPORT` is `stdio` THE SYSTEM SHALL still parse and validate
  host and port exactly as today, so a bad value is reported eagerly rather than
  only when HTTP is enabled.
- WHEN the container image is built THE SYSTEM SHALL declare the bind address via
  `ENV NEWTON_MCP_HOST=0.0.0.0` and `ENV NEWTON_MCP_PORT=8000` in `Dockerfile`,
  replacing the current `HOST` / `PORT` entries.
- WHEN the container is started with no overrides THE SYSTEM SHALL serve
  streamable-http on `0.0.0.0:8000`, so the existing
  `.github/workflows/ci.yml` "Smoke-check streamable-http listens on /mcp" job keeps
  passing unchanged.
- WHEN a reader consults `.env.example`, `README.md` or `CONTRIBUTING.md` THE SYSTEM
  SHALL present `NEWTON_MCP_HOST` / `NEWTON_MCP_PORT` as the documented names and
  mention the bare names only as a documented fallback.

## Out of scope

- Any change to transport selection, the set of supported transports, or the
  `/mcp` path.
- Authentication, TLS, reverse proxying or any other network hardening. The README's
  existing note that the gateway ships no authentication stays as-is.
- Renaming or re-validating any other variable, including `NEWTON_REQUEST_TIMEOUT_SEC`
  (whose `float(...)` conversion on `config.py` line 61 is unguarded — a separate
  concern, not touched here).
- Emitting a deprecation warning or log line when the bare names are used, or setting
  a removal date for them.
- Adding a `.env` file loader (`python-dotenv` or similar). `.env.example` remains
  documentation only; nothing in the repo reads a `.env` file today.
- Changing the `Settings` public field names, adding new public fields, or
  introducing `pydantic-settings`.

## Open questions

- Should a blank `PORT` / `NEWTON_MCP_PORT` be a default or an error? Today a blank
  `HOST` falls back to `127.0.0.1` (`config.py` line 47, covered by
  `test_host_and_port_overrides`), while a blank `PORT` raises
  `ValueError: PORT must be an integer, got ''` because `int("")` fails. This
  proposal makes both fall back to the default, which is required anyway for
  "blank prefixed value falls through to the bare name" to work. Proceeding with the
  symmetric behaviour; it is a small, intentional change to blank-`PORT` handling and
  is listed in `design.md` under Platform impact.
- Should using a bare name emit a one-line deprecation notice on stderr? Left out to
  avoid polluting the `stdio` transport's channel discipline; recorded here so a
  follow-up issue can decide.
- Is there a timeline for removing the bare fallback? Assumed no — the issue asks
  explicitly to keep it working.
- `.env.example` currently ships a `PORT=8000` line that is not read by any code.
  Assumed it stays purely illustrative and just gets renamed.
