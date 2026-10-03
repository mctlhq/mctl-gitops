# Docs: action runtime, safety, and Archetype integration (pre-public-release doc set)

> **Amended at owner review (2026-09-29).** The link-only test becomes a docs-consistency test
> (`tests/test_docs_consistency.py`): relative links, `demo.py` flags, `uv run` targets and env
> var names in the doc corpus are checked against the real parser, `pyproject.toml`, env
> lookups and `.env.example`. `examples/smart-home/README.md` joins the corpus. The confirmed
> Archetype table cites a concrete public doc page per row, the upload ceiling is written
> "512 MB", and `task-verification` is described as its public page describes it.

## Context

`newton-mcp-gateway` is about to go public and be shown to Archetype engineers. The code is
already there: `src/newton_mcp/runtime/` (catalog, resolver, executor, verifier, lifecycle,
audit, runtime config) and `src/newton_mcp/action/` (contract v0.2, conditions, policy,
approval, propose) are implemented and mock-validated, and `examples/smart-home/` composes
them into a runnable demo. What is missing is a reader-facing doc set that (a) describes
exactly what that code does, (b) states the safety argument as invariants a reviewer can
check, and (c) separates what is confirmed from Archetype's public documentation from what is
this project's own experimental proposal — plus the open questions an Archetype engineer is
actually the right person to answer.

Issue #10 asks for three documents and a README refresh. `docs/action-runtime.md` already
exists and is detailed (it is referenced from `src/newton_mcp/action/contract.py:6` and from
`src/newton_mcp/runtime/config.py:5`), so the work there is an audit-against-source pass plus
two missing sections: a consolidated contract v0.2 reference and a "plug in a new MCP actuator
by config only" recipe. `docs/safety.md` and `docs/archetype-integration.md` do not exist at
all. The safety defaults table currently lives only in `docs/architecture.md` (lines 68-83),
which is the wrong home for it and a drift risk once a second doc restates it. The README has
no documentation index: it links `docs/action-runtime.md`, `docs/newton-api-notes.md` and
`examples/smart-home/README.md` inline, and never links `docs/architecture.md` at all.

This matters because the repo's credibility with the intended reader rests entirely on the
claims being checkable. A doc that overstates validation status, or that reads like a pitch,
destroys the thing the repo is for. The hard rules in `AGENTS.md` (mock labelling, public
documentation only, "this project's proposal" wording, no mctl.ai dependency) are the
acceptance bar, not a style preference.

## User stories

- AS an Archetype engineer reading this repo for the first time I WANT a single page that
  separates confirmed Archetype behaviour from this project's proposal, with the open
  questions stated plainly SO THAT I can tell in one pass what I am being asked to comment on
  and what is already settled.
- AS a reviewer of a pull request in this repo I WANT every runtime claim in the docs to name
  the real symbol, state, env var or default it describes SO THAT I can verify the doc against
  `src/` without guessing what was meant.
- AS a safety reviewer I WANT the safety defaults, the invariants and the demo-safe action list
  in one document SO THAT I can audit the safety argument without reading five modules and two
  YAML examples.
- AS an operator wiring a new MCP actuator I WANT a config-only recipe SO THAT I can add a
  capability by editing `runtime.yaml` and `policy.yaml` without touching `src/newton_mcp/`.
- AS the repo owner I WANT the README status line to be truthful about live validation SO THAT
  nothing in the repo can be read as claiming a working live Newton or live actuator
  integration before one has been run with real credentials.

## Acceptance criteria (EARS)

### Document set

- WHEN the change is complete THE SYSTEM SHALL contain `docs/action-runtime.md`,
  `docs/safety.md` and `docs/archetype-integration.md`, all three in English, with no emoji.
- WHILE any of the three documents exists THE SYSTEM SHALL carry, in that document's own
  opening block, an explicit statement that the Physical Action Contract and the action runtime
  are this project's experimental proposal and not an Archetype standard.
- WHILE any of the three documents exists THE SYSTEM SHALL contain no marketing language: no
  superlatives about the project, no claimed adoption, partnership, endorsement or benchmark,
  and no call to action aimed at a buyer.
- WHILE any document in this repository describes a result produced by the runtime THE SYSTEM
  SHALL label that result mock-validated, and SHALL NOT state or imply that a live Newton
  account or a live MCP actuator server has been exercised.
- WHILE any of the three documents exists THE SYSTEM SHALL NOT mention, pitch or depend on
  mctl.ai or any DevLoop tooling.

### `docs/action-runtime.md`

- WHEN `docs/action-runtime.md` describes the contract THE SYSTEM SHALL document contract v0.2
  as it is defined in `src/newton_mcp/action/contract.py`: the `version` pattern `^0\.2$`, every
  field of `PhysicalActionContract` (`goal`, `reason`, `confidence`, `target`, `constraints`,
  `risk`, `reversible`, `requires_confirmation`, `verification`, `evidence`), the `Risk` members
  (`read_only`, `low`, `medium`, `high`, `critical`), the `Verification` defaults
  (`timeout_seconds=300`, `retry_limit=0`), and the structured `Condition` shape from
  `src/newton_mcp/action/conditions.py` including `MAX_CONDITION_DEPTH = 8`.
- WHEN `docs/action-runtime.md` describes discovery THE SYSTEM SHALL state that
  `CapabilityCatalog.refresh()` issues `list_tools` only and never `call_tool`, that the
  per-server cycle is bounded by `server_timeout_seconds`
  (`DEFAULT_SERVER_TIMEOUT_SECONDS = 10.0`), and SHALL name the problem kinds the catalog can
  record (`server_unavailable`, `tool_missing`, `read_tool_missing`).
- WHEN `docs/action-runtime.md` describes resolution THE SYSTEM SHALL list the ordered filter
  chain of `Resolver.resolve()` with the rejection reasons in the order the code applies them,
  and SHALL reproduce the score formula with the constants as they appear in
  `src/newton_mcp/runtime/resolver.py` (`BASE_SCORE = 0.50`, `GOAL_WEIGHT = 0.20`,
  `LOCATION_BONUS = 0.20`, `READ_TOOL_BONUS = 0.10`).
- WHEN `docs/action-runtime.md` describes policy THE SYSTEM SHALL document
  `Policy.evaluate()`'s four-step order (critical denies first, first matching rule wins,
  `default`, then the `requires_confirmation` confirmation ceiling), the `Decision` members,
  the `PolicyRule` predicate order and defaults (`max_risk=low`, `min_confidence=0.0`,
  `decision=auto`), the inclusive semantics of `arg_ranges`, and that a failed `arg_ranges`
  check denies immediately rather than falling through.
- WHEN `docs/action-runtime.md` describes approval binding THE SYSTEM SHALL name the exact
  bound payload `{server_identity, tool_name, args, action_id, policy_version, expires_at}`,
  state that `server_identity` there is `candidate.server_binding_identity` (the
  `resolved_identity@sha256:transport_fingerprint` form from `ServerConfig`), state that
  `approved_by`/`approved_at`/`approval_id` are deliberately not bound, and state that the
  binding is context binding and not authentication.
- WHEN `docs/action-runtime.md` describes the lifecycle THE SYSTEM SHALL reproduce
  `ALLOWED_TRANSITIONS` from `src/newton_mcp/runtime/lifecycle.py` exactly, including the
  `UNKNOWN` state, and SHALL state that `UNKNOWN -> EXECUTING` and `PROPOSED -> EXECUTING` do
  not exist and why, and that a `FAILED -> EXECUTING` retry requires `verified_failure=True`.
- WHEN `docs/action-runtime.md` describes the retry rule THE SYSTEM SHALL state it as one rule
  — verify before retrying, never re-send a non-idempotent action whose outcome is unknown —
  and SHALL state the two conditions `run_action()` requires for a retry
  (`candidate.idempotent` and `record.attempt <= contract.verification.retry_limit`) and that a
  run always ends in exactly one of `SUCCEEDED` or `ESCALATED`.
- WHEN `docs/action-runtime.md` describes audit THE SYSTEM SHALL name `AuditEvent`,
  `MemoryAuditSink` as the default, `JsonlAuditSink`'s append-per-write behaviour, the four
  correlation ids (`observation_id`, `action_id`, `tool_call_id`, `verification_id`), the
  `args`/`args_digest` pair, `load_audit_sink()`'s reading of `NEWTON_MCP_AUDIT_PATH`, and
  `redact_args()`'s key-name-only, deliberately over-eager redaction with its documented gap.
- WHEN `docs/action-runtime.md` explains how to add an actuator THE SYSTEM SHALL provide a
  config-only recipe that adds a `servers:` entry and a `capabilities:` entry to `runtime.yaml`
  plus a rule to `policy.yaml`, SHALL state that no file under `src/newton_mcp/` is edited, and
  SHALL name the concrete obligations the new actuator must meet for the runtime to work:
  an allow-listed tool whose `input_schema` the rendered arguments validate against, a
  `read_tool` returning a JSON object (`structured_content`, or a single text block parsed as
  a JSON object) if the action is to be verifiable at all, and `read_only_hint` not `False` on
  that read tool.
- IF a claim in `docs/action-runtime.md` cannot be traced to a symbol, constant, state or env
  var in `src/` THEN THE SYSTEM SHALL either correct the claim or remove it.

### `docs/safety.md`

- WHEN `docs/safety.md` is written THE SYSTEM SHALL contain a safety defaults table mapping
  action classes to decisions, consistent with `examples/policy.example.yaml`,
  `examples/smart-home/policy.yaml` and `Policy.conservative()`.
- WHEN `docs/safety.md` states the invariants THE SYSTEM SHALL state at least: `critical` risk
  denies before any rule is consulted; an approval binds to one exact action over
  `{server_identity, tool_name, args, action_id, policy_version, expires_at}` and expires at
  `expires_at`; a tool-call timeout yields `UNKNOWN` and must be verified or escalated, never
  re-executed; a non-idempotent action is never retried; a verified `FAILED` retries only
  within `retry_limit`; a run with zero observations escalates and is never reported as a
  verified failure.
- WHEN `docs/safety.md` lists demo-safe actions THE SYSTEM SHALL list only lights, HVAC within
  configured bounds, speaker announcements and benign routines, and SHALL name the excluded
  classes explicitly (locks, ovens, alarms, industrial start/stop, safety systems) as never
  permitted in any example, test or doc in this repository.
- WHILE `docs/safety.md` exists THE SYSTEM SHALL record the known limitations rather than omit
  them: the keyless binding is not authentication, there is no approval revocation or
  single-use semantics, `redact_args()` misses a secret passed under a benign key name, a stdio
  transport fingerprint cannot distinguish a credential rotation from an endpoint change, the
  gateway ships no authentication, and the verifier's documented worst-case deadline overrun is
  one in-flight poll (up to `read_timeout_seconds`).
- WHEN `docs/safety.md` states a non-goal THE SYSTEM SHALL name it as a non-goal of this repo
  and not as future work that is promised.
- WHEN `docs/safety.md` becomes the canonical home of the safety defaults table THE SYSTEM
  SHALL ensure the table is not duplicated in `docs/architecture.md`; that section SHALL
  instead point to `docs/safety.md`.

### `docs/archetype-integration.md`

- WHEN `docs/archetype-integration.md` is written THE SYSTEM SHALL separate, in two clearly
  labelled parts, what is confirmed by Archetype's public documentation
  (docs.archetypeai.app, `/llms.txt`) from what this project proposes.
- WHILE `docs/archetype-integration.md` describes Archetype behaviour THE SYSTEM SHALL cite
  only publicly documented endpoints, request/response field names, model families and
  environment variable names, and SHALL NOT invent an endpoint, a parameter or a model id.
- WHEN `docs/archetype-integration.md` states the open questions THE SYSTEM SHALL state at
  least four, each as a question an Archetype engineer can answer, covering: the integration
  model of Newton Agents with external systems; sink/action connectors in the node registry;
  confidence and provenance in Newton outputs; and support for post-action verification.
- WHEN each open question is stated THE SYSTEM SHALL state what this project currently assumes
  in the absence of an answer and which module that assumption lives in, so the question is
  answerable without reading the whole repo.
- WHILE `docs/archetype-integration.md` exists THE SYSTEM SHALL state that no private endpoint
  was reverse-engineered and no access control was circumvented.

### README

- WHEN the README is updated THE SYSTEM SHALL contain a documentation index linking every file
  under `docs/` (`architecture.md`, `action-runtime.md`, `safety.md`,
  `archetype-integration.md`, `newton-api-notes.md`) and `examples/smart-home/README.md`.
- WHILE the README's status block exists THE SYSTEM SHALL state that the MCP server and mock
  backend are functional, that the real Newton adapter is implemented against public
  documentation but not validated against a live account, and that the action runtime is
  mock-validated only with no live actuator — using the words "mock-validated" and not
  "validated" for anything that has not been run with real credentials.
- WHEN the README's confirmed-versus-proposed table is refreshed THE SYSTEM SHALL keep every
  row's source attribution accurate and SHALL add a row for the lifecycle, audit trail,
  executor and verifier as this project's proposal.
- IF a relative link in `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, any file under `docs/` or
  `examples/smart-home/README.md` names a path THEN THE SYSTEM SHALL ensure that path exists in
  the repository.
- IF a fenced code block or inline code span in that corpus invokes `examples/smart-home/demo.py`
  THEN THE SYSTEM SHALL ensure every `--flag` in that command is an option string accepted by
  the demo's own argument parser (`_build_parser()`). A `--word` in prose, or in a command that
  does not invoke `demo.py`, is not checked.
- IF a command in that corpus runs `uv run <name>` THEN THE SYSTEM SHALL ensure `<name>` is
  either a key of `[project.scripts]` in `pyproject.toml`, a tool configured by a `[tool.<name>]`
  table there (for example `pytest` via `[tool.pytest.ini_options]`), or `python` followed by a
  script path that exists in the repository (`python -c` / `python -m` are accepted as-is).
- IF that corpus names an environment variable with the `NEWTON_` or `ATAI_` prefix THEN THE
  SYSTEM SHALL ensure the name is either read by the code — a string literal passed to
  `env.get(...)`, `os.environ.get(...)`, `os.environ[...]` or `os.getenv(...)`, a name in a tuple
  passed to `newton_mcp.config._resolve(...)`, or the value of a module constant ending in
  `_ENV_VAR` — or assigned in `.env.example` (including a commented `# NAME=` example). A name
  that only appears in a comment or docstring under `src/` does not count.

### Verification of the change itself

- WHEN the change is complete THE SYSTEM SHALL keep `uv run pytest` green.
- WHEN the change is complete THE SYSTEM SHALL NOT modify any file under `src/newton_mcp/`,
  `schemas/` or `examples/`, with one exception: `examples/smart-home/README.md` MAY be edited
  only to correct a mismatch the docs-consistency test reports.

## Out of scope

- New runtime or library code. No module under `src/newton_mcp/` changes, no new MCP tool, no
  behaviour change. The only code artefact this proposal contemplates is one test module that
  checks the doc corpus against the code (see Open questions) — and nothing else.
- The outreach email to Archetype (issue #16).
- Authenticated streamable-http transport (issue #28) and structured read-only state on the
  real Alice server (`mctlhq/mctl-alice#47`). Both are referenced as known gaps, neither is
  fixed here.
- Signed approvals, an authenticated approver, approval revocation or nonce semantics. These
  remain documented non-goals.
- Running Newton Agent bundles, or any change to the Newton backends
  (`src/newton_mcp/newton/`).
- A generated API reference, a docs site, a diagram toolchain, or any docs build step.
- Rewriting `docs/architecture.md` beyond replacing its duplicated safety defaults table with
  a pointer to `docs/safety.md`.

## Open questions

- The issue lists "New code" as out of scope, but acceptance criterion 3 ("README links
  resolve") and the reproducibility of every documented command have no mechanical guard without
  one. Resolved at owner review: add exactly one test module, `tests/test_docs_consistency.py`,
  covering links, `demo.py` flags, `uv run` targets and env var names (see the acceptance
  criteria above). It touches no package code, uses the standard library only (`ast`, `re`,
  `shlex`, `tomllib`, `pathlib`, `importlib`) and matches `AGENTS.md`'s "tests for every
  behaviour".
- `docs/architecture.md` is not in the issue's "files likely touched" list, yet it currently
  owns the safety defaults table that `docs/safety.md` is being asked to contain. Proceeding
  with: `docs/safety.md` becomes canonical and `docs/architecture.md`'s "Safety defaults"
  section is reduced to a one-line pointer. The alternative — two copies of the table — was
  rejected as a guaranteed drift. If the owner prefers architecture.md untouched, the table
  should still exist in only one place.
- The issue says `docs/action-runtime.md` "is already referenced from `action/contract.py`",
  which reads as though the file may not exist. It does exist and is substantial. Proceeding
  with: treat this as an audit-and-extend pass, not a rewrite, and preserve its existing
  structure and wording wherever the code still matches.
- "The safety defaults table" is not specified in the issue. Proceeding with the action-class
  to decision shape already in `docs/architecture.md` lines 70-77, extended with a second table
  of the runtime's numeric defaults (server/call/read timeouts, poll interval, `retry_limit`,
  `timeout_seconds`, `MAX_CONDITION_DEPTH`) since those are also safety-relevant defaults a
  reviewer will want in one place.
- Whether `/llms.txt` should be quoted or only cited in `docs/archetype-integration.md`.
  Proceeding with: cite it as a source, quote no more than short field or concept names, and
  never paste a block that could go stale silently.
- Whether the open questions should also be filed as GitHub issues so an Archetype engineer can
  answer them in public. Proceeding with: keep them in the document only; issue #16 owns any
  outreach mechanics.
