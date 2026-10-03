# Design: issue-10-3-2-docs-action-runtime-safety-archetype

> **Amended at owner review (2026-09-29).** The link-only test becomes a docs-consistency test
> (`tests/test_docs_consistency.py`): relative links, `demo.py` flags, `uv run` targets and env
> var names in the doc corpus are checked against the real parser, `pyproject.toml`, env
> lookups and `.env.example`. `examples/smart-home/README.md` joins the corpus. The confirmed
> Archetype table cites a concrete public doc page per row, the upload ceiling is written
> "512 MB", and `task-verification` is described as its public page describes it.

## Current state

### What `docs/` contains today

`docs/` holds exactly three files. There is no `docs/safety.md` and no
`docs/archetype-integration.md` anywhere in the repository, and nothing references either name.

- `docs/action-runtime.md` (478 lines). Already the most detailed document in the repo. Opens with
  a blockquote (lines 3-12) that states the package is "**this project's experimental proposal**
  for Direction A", "not an Archetype standard", and that every result is "**mock-validated**
  only". Sections: Why this exists, `runtime.yaml`, the catalog, server identity in an approval
  binding, the resolver (filter chain + score formula), argument templates, policy, verification
  conditions (contract v0.2), approval binding, lifecycle/correlation ids/audit, executor,
  verifier, the retry rule (`run_action()`), and "What this package does not do". It is referenced
  from `src/newton_mcp/action/contract.py:6`, `src/newton_mcp/runtime/config.py:5`,
  `src/newton_mcp/runtime/config.py:102`, `src/newton_mcp/action/policy.py:9` (indirectly, via the
  same philosophy note), `src/newton_mcp/runtime/audit.py:13`, `.env.example` (three times),
  `examples/runtime.example.yaml`, `examples/policy.example.yaml` and
  `examples/smart-home/README.md`.
- `docs/architecture.md` (84 lines). Terminology attributed to Archetype (Newton C / Omega
  encoders / Physical Agent / Newton Agents blueprints `osm`, `anomaly-discovery`,
  `rare-event-detection`, `task-verification`, `manual-generation`), Direction B and Direction A
  diagrams, the lifecycle summary, "Digital success is not physical success", and — lines 68-83 —
  a `## Safety defaults` section holding the only action-class-to-decision table in the repo plus
  the `critical`-risk and approval-binding paragraph. The README does not link this file at all.
- `docs/newton-api-notes.md`. Traceability notes for the `/query` and Files API fields
  `newton_analyze_image` sends, each attributed to a public doc page, plus a "Not validated
  against a live account" section and an explicit note that `NEWTON_MAX_IMAGE_BYTES` is
  transport-shaped rather than a documented Archetype limit.

### The code the docs must match

Everything the issue asks to document is implemented:

- Contract: `src/newton_mcp/action/contract.py` — `PhysicalActionContract` with
  `version: str = Field(default="0.2", pattern=r"^0\.2$")`, `Risk` (`read_only`, `low`, `medium`,
  `high`, `critical`), `Target` (`extra="allow"`), `Verification`
  (`timeout_seconds: int = 300, ge=1`; `retry_limit: int = 0, ge=0`), `Evidence`, `reversible=True`,
  `requires_confirmation: bool | None = None`. `src/newton_mcp/action/conditions.py` — the
  structured `Condition` via a callable Pydantic `Discriminator`, `MAX_CONDITION_DEPTH = 8`, and a
  pure `evaluate()`.
- Config: `src/newton_mcp/runtime/config.py` — `RUNTIME_CONFIG_ENV_VAR =
  "NEWTON_MCP_RUNTIME_CONFIG"`, every model `extra="forbid"`, `ServerConfig.resolved_identity` /
  `.transport_fingerprint` / `.binding_identity`, `_canonical_url()`, `CapabilityConfig`
  (`goal_prefixes` min_length 1 with a blank-prefix validator, `read_tool`, `read_arguments`,
  `idempotent: bool = False`), `RuntimeConfig._validate_references()` (duplicate name, duplicate
  resolved identity, undeclared server, duplicate `(server, tool)` pair).
- Catalog: `src/newton_mcp/runtime/catalog.py` — `DEFAULT_SERVER_TIMEOUT_SECONDS = 10.0`,
  `MAX_TOOL_PAGES = 1000`, `CatalogEntry.read_only_hint: bool | None`,
  `default_client_factory`.
- Resolver: `src/newton_mcp/runtime/resolver.py` — `BASE_SCORE = 0.50`, `GOAL_WEIGHT = 0.20`,
  `LOCATION_BONUS = 0.20`, `READ_TOOL_BONUS = 0.10`, and the ordered rejection chain.
- Policy: `src/newton_mcp/action/policy.py` — `POLICY_PATH_ENV_VAR = "NEWTON_MCP_POLICY_PATH"`,
  `CONSERVATIVE_POLICY_VERSION = "builtin.conservative.v1"`, `Decision` (`auto`/`confirm`/`deny`),
  `ValueRange` (inclusive, at least one bound, `min <= max`), `PolicyRule` (`max_risk=Risk.LOW`,
  `min_confidence=0.0`, `decision=Decision.AUTO`), `Policy.default = Decision.DENY`,
  `Policy.conservative()` (low auto at `min_confidence=0.8`, medium confirm, default deny), and
  `evaluate()`'s critical-first / first-match / default / confirmation-ceiling order.
- Approval: `src/newton_mcp/action/approval.py` — `compute_binding`, `create_approval`,
  `verify_approval`, `hmac.compare_digest`, `args_digest`.
- Lifecycle and audit: `src/newton_mcp/runtime/lifecycle.py` (`ActionState`, `ALLOWED_TRANSITIONS`,
  `transition()`, `new_action_record()`, four correlation ids, `IllegalTransition`) and
  `src/newton_mcp/runtime/audit.py` (`AUDIT_PATH_ENV_VAR = "NEWTON_MCP_AUDIT_PATH"`,
  `SECRET_KEY_PATTERNS` of eleven substrings, `REDACTED = "[redacted]"`, `_MAX_VALUE_CHARS = 500`,
  `MemoryAuditSink` default, `JsonlAuditSink`, `load_audit_sink()`).
- Executor and verifier: `src/newton_mcp/runtime/executor.py`
  (`DEFAULT_CALL_TIMEOUT_SECONDS = 30.0`, `Executor.execute()`, `run_action()`, `ExecutorError`,
  `ApprovalRejected`) and `src/newton_mcp/runtime/verifier.py`
  (`DEFAULT_POLL_INTERVAL_SECONDS = 5.0`, `DEFAULT_READ_TIMEOUT_SECONDS = 10.0`,
  `observation_from_result()`, the four pre-poll escalation gates including
  `read_only_hint is False`).
- Server: `src/newton_mcp/server.py` registers four tools, each
  `ToolAnnotations(read_only_hint=True, open_world_hint=True)` (lines 63, 97, 128, 214).
- Settings: `src/newton_mcp/config.py` — `NEWTON_BACKEND`, `ATAI_API_KEY`, `ATAI_API_ENDPOINT`
  (default `https://api.u1.archetypeai.app/v0.5`), `NEWTON_TEXT_MODEL`, `NEWTON_OMEGA_MODEL`,
  `NEWTON_REQUEST_TIMEOUT_SEC` (90.0), `NEWTON_MCP_TRANSPORT`, `NEWTON_MCP_HOST`/`HOST`,
  `NEWTON_MCP_PORT`/`PORT`, `NEWTON_MAX_IMAGE_BYTES` (8 MiB, ceiling
  `DOCUMENTED_MAX_UPLOAD_BYTES`, 512 MB as documented). The three runtime paths
  (`NEWTON_MCP_RUNTIME_CONFIG`, `NEWTON_MCP_POLICY_PATH`, `NEWTON_MCP_AUDIT_PATH`) are
  deliberately not in `Settings`.
- Demo-safe actions: `examples/runtime.example.yaml` (`set_target_temperature`,
  `set_light_state`, `announce`), `examples/policy.example.yaml` (`policy_version: "example.v1"`,
  `default: deny`, comfort band 20-25 C), `examples/smart-home/runtime.yaml` and
  `examples/smart-home/policy.yaml` (`policy_version: "smart-home.v1"`, brightness 0-100,
  `announce` requires confirm). Both example YAMLs already carry a header comment naming the
  forbidden classes.

### The gaps this issue closes

1. No standalone safety document. The safety argument is spread across
   `docs/architecture.md:68-83`, the "What this package does not do" list in
   `docs/action-runtime.md:460-472`, the module docstrings, and the two example YAML headers.
2. No Archetype-integration document, and therefore nowhere in the repo that states the four open
   questions the issue names. Repo-wide, Newton Agents' external-system integration, sink/action
   connectors, node registries, output confidence/provenance and Archetype-side post-action
   verification are simply absent — `task-verification` is named once as a blueprint
   (`docs/architecture.md:10`) and never connected to the runtime's verifier. The word
   "provenance" appears nowhere; `confidence` exists only as a field of *this project's* contract.
3. `docs/action-runtime.md` has no consolidated contract v0.2 reference (v0.2 is described only
   through the "Verification conditions" section) and no "add an actuator by config only" recipe,
   both of which the issue names explicitly.
4. The README has no documentation index, never links `docs/architecture.md`, and its
   confirmed-versus-proposed table (lines 222-231) predates the lifecycle, audit, executor and
   verifier work.
5. Nothing checks that a relative markdown link resolves. No test in `tests/` asserts anything
   about doc content or links.

## Proposed solution

Documentation-only, plus one docs-consistency test. No file under `src/newton_mcp/`, `schemas/` or
`examples/` changes, except that `examples/smart-home/README.md` may be corrected where the test
finds a mismatch.

### 1. `docs/safety.md` (new) becomes the canonical safety document

Structure:

1. **Scope and status blockquote** — same shape as `docs/action-runtime.md:3-12`: this is this
   project's experimental proposal, not an Archetype standard; every result is mock-validated;
   no live actuator, no live Newton credentials.
2. **Safety defaults: action classes.** The table currently at `docs/architecture.md:70-77`,
   moved here verbatim in intent, each row annotated with the example rule that realises it
   (`examples/policy.example.yaml`'s `hvac-within-comfort-band`, `lighting`, `announcements`) or
   with the fact that no rule in this repo grants it. Denied classes stay in the table as rows
   with decision `deny` so a reader sees the forbidden set, not only the allowed one.
3. **Safety defaults: numeric.** A second table of every safety-relevant default with its
   defining constant and module: `Verification.timeout_seconds=300`, `retry_limit=0`,
   `DEFAULT_SERVER_TIMEOUT_SECONDS=10.0`, `DEFAULT_CALL_TIMEOUT_SECONDS=30.0`,
   `DEFAULT_POLL_INTERVAL_SECONDS=5.0`, `DEFAULT_READ_TIMEOUT_SECONDS=10.0`,
   `MAX_CONDITION_DEPTH=8`, `MAX_TOOL_PAGES=1000`, `_MAX_VALUE_CHARS=500`,
   `PolicyRule.max_risk=low`, `PolicyRule.min_confidence=0.0`, `Policy.default=deny`,
   `CapabilityConfig.idempotent=false`, `PhysicalActionContract.reversible=true`. The
   justification for a separate table is that "safety defaults" in an actuator system means
   timeouts and retry ceilings as much as it means allow/deny.
4. **Invariants.** Each stated as a checkable sentence with the code location that enforces it and
   the failure it prevents: `critical` denies before any rule (`Policy.evaluate()` first branch);
   the confirmation ceiling never grants more authority than the operator's rules; `arg_ranges`
   denies immediately instead of falling through; the approval binds exactly
   `{server_identity, tool_name, args, action_id, policy_version, expires_at}` and is re-checked on
   every attempt including retries (`Executor.execute()` step 2); a re-pointed transport
   invalidates every outstanding approval (`ServerConfig.binding_identity`); a timeout yields
   `UNKNOWN` and `ALLOWED_TRANSITIONS` has no `UNKNOWN -> EXECUTING` edge; a synchronous MCP error
   is a completed attempt and still gets verified (no `EXECUTING -> FAILED` edge); `FAILED` is
   reachable only from `VERIFYING`, so it always means a verified failure, and the retry edge
   additionally demands `verified_failure=True`; a retry requires `candidate.idempotent`; zero
   observations escalate rather than report a verified failure; the verifier refuses a read tool
   whose `read_only_hint is False`; the verifier calls `read_tool` with `read_args`, never the
   action's `args`.
5. **Demo-safe actions.** Lights, HVAC within configured bounds, speaker announcements, benign
   routines — cross-referenced to the four capabilities in `examples/smart-home/runtime.yaml`.
   Then the excluded set (locks, ovens, alarms, industrial start/stop, safety systems), stated as
   never permitted in any example, test or document in this repository.
6. **Known limitations.** The keyless binding is context binding, not authentication; no
   revocation and no nonce/single-use; `redact_args()` is key-name-only and over-eager, so a
   secret under a benign key name (`note`) still reaches the log; a stdio transport fingerprint
   covers the full `env` mapping, so it cannot distinguish a credential rotation from an endpoint
   change; the gateway ships no authentication and the container binds `0.0.0.0`; the verifier's
   worst-case deadline overrun is one in-flight poll (up to `read_timeout_seconds`); `announce`
   has no `read_tool` and is therefore never verifiable.
7. **Non-goals.** Signed approvals, an authenticated approver, revocation, an LLM or any
   non-deterministic judge in the verification path, LLM or embedding capability matching,
   long-lived MCP sessions or connection pooling, exposing the runtime as MCP tools, and any
   unsafe actuator class. Each stated as a non-goal of this repository, not as promised future
   work.

`docs/architecture.md`'s `## Safety defaults` section is reduced to a heading plus a one-line
pointer to `docs/safety.md`. The two tables are never duplicated. This is the one edit outside the
issue's "files likely touched" list and is called out in `requirements.md` open questions.

### 2. `docs/archetype-integration.md` (new)

Three parts, deliberately in this order so the reader hits the boundary before the proposal:

1. **Confirmed from Archetype's public documentation.** A table with a `source` column naming the
   doc page, covering only what the code already attributes: `POST {ATAI_API_ENDPOINT}/query` and
   its request fields (`model`, `query`, `system_prompt`, `instruction_prompt`, `file_ids`,
   `events`, `max_new_tokens`, `normalize_input`, `sanitize_response`) and response fields
   (`response.response`, `status`, `query_id`, `inference_time_sec`, `error_msg`, `errors`,
   `detail`); the `DataEvent` shape (`type`, `event_data`, `event_data.contents`) and the event
   types in `models.py`'s `EventType`; `POST /v0.5/files` and `POST /v0.5/files/base64` with the
   `is_valid`/`file_id`/`file_uid` response and the documented 512 MB ceiling; the two model
   families (`Newton::c2_...`, `OmegaEncoder::...`) and the 768-dim per-channel embedding; the
   `ATAI_API_KEY`/`ATAI_API_ENDPOINT` variable names; and the Agents API concepts
   (blueprint → bundle → run, paginated results/events/logs, the five blueprint names). Every row
   cites a concrete page under https://docs.archetypeai.app/ (index: `/llms.txt`), not the site
   root. The Agents API rows cite `core-concepts/agents/overview.md`,
   `core-concepts/agents/api.md`, the five blueprint pages
   (`core-concepts/agents/{anomaly-discovery,manual-generation,osm,rare-event-detection,task-verification}.md`)
   and `api-reference/agents/{create-blueprint,create-bundle,run-bundle,get-agent-results,list-agent-events,get-agent-logs,list-node-registry}.md`,
   and state that the Agents API is not wired into this gateway (issue #13, deferred until after
   first contact). The upload row cites `api-reference/files/upload.md` and `upload-base64.md`
   and writes the ceiling as "512 MB", matching `docs/newton-api-notes.md`. No endpoint,
   parameter or model id appears that is not already in the code or in `docs/newton-api-notes.md`
   with a cited doc page.
2. **Proposed by this project.** The Physical Action Contract v0.2, the `runtime.yaml` capability
   allow-list and catalog, the deterministic resolver and its score, `policy.yaml` and the policy
   engine, the context-bound `Approval`, the `ActionState` lifecycle with `UNKNOWN`, the JSONL
   audit trail, the executor, the verifier and the retry rule, and this gateway's MCP tool
   mapping. Each row says which module owns it and repeats the mock-validated status.
3. **Open questions for Archetype engineers.** The four the issue names, each written as a
   question plus a "what this project assumes today, and where" line so the question is
   answerable without reading the repo:
   - *Integration model of Newton Agents with external systems.* Assumption today: a Newton Agent
     or a `/query` with a strict JSON system prompt emits a contract, and everything downstream is
     outside Newton (`src/newton_mcp/action/propose.py`, `prompts.py`). Question: is there a
     documented, supported way for an Agent run to hand a structured intent to an external system,
     or is polling `results`/`events` the intended boundary?
   - *Sink/action connectors in the node registry.* Assumption today: none exists, so this project
     built its own allow-list and catalog (`src/newton_mcp/runtime/config.py`,
     `runtime/catalog.py`). Question: does the node registry model output sinks or action
     connectors, and if so, would an MCP-client node be expressible there rather than in a
     separate runtime?
   - *Confidence and provenance in outputs.* Assumption today: `PhysicalActionContract.confidence`
     is model-authored and the policy treats it as a floor only
     (`PolicyRule.min_confidence`), with `Evidence.observation_id` carrying provenance this
     project invented, and `sanitize_response=False` kept so `query_id` and timings survive for an
     audit trail (`src/newton_mcp/newton/models.py`). Question: do Newton outputs expose a
     first-class confidence or provenance field this project should consume instead of asking a
     model to self-report one?
   - *Support for post-action verification.* Assumption today: verification is entirely this
     project's (`src/newton_mcp/runtime/verifier.py`), polling a capability's `read_tool` and
     evaluating a structured condition. Public docs: the Task Verification Agent
     (`core-concepts/agents/task-verification.md`) verifies that work is performed according to
     standard operating procedures by observing video data. Stated separately: whether it is
     suitable for verifying that a *commanded physical outcome* occurred is not confirmed by any
     public page. Question: is it, or another Agent, intended for that, and could such a result
     be fed back as a new observation?
   Plus a closing statement that nothing here reverse-engineers a private endpoint or circumvents
   an access control, and that this project is not affiliated with or endorsed by Archetype AI.

### 3. `docs/action-runtime.md` (audit and extend)

Existing structure and wording are preserved wherever the code still matches — this is not a
rewrite. Three changes:

- **Audit pass.** Walk every named symbol, state, constant, default and env var in the document
  against `src/` and correct or delete anything that no longer matches. Concrete items the
  reviewer will check: the `ALLOWED_TRANSITIONS` block (lines 285-293), the score formula
  (lines 156-161), the filter-chain order (lines 141-151), the `Policy.evaluate()` order
  (lines 203-223), the bound payload (lines 256-260), the `SECRET_KEY_PATTERNS` list (line 347 —
  the doc writes "..." where the code has eleven entries, so either enumerate them or say
  "eleven documented substrings, see `SECRET_KEY_PATTERNS`"), and the three env var names.
- **New section: "Contract v0.2 at a glance"**, placed before "Verification conditions". A field
  table for `PhysicalActionContract`, `Target`, `Verification` and `Evidence` with types and
  defaults, the `Risk` ladder, the `^0\.2$` pin and the no-migration-shim note, plus a pointer to
  `schemas/physical-action-contract.schema.json` and the regeneration command's home in
  `CONTRIBUTING.md`. The existing "Verification conditions (contract v0.2)" section keeps its
  detail and loses nothing.
- **New section: "Adding an MCP actuator by configuration only"**, placed after "Verifier". A
  worked example: add a `servers:` entry, add a `capabilities:` entry with `goal_prefixes`,
  `target`, `arguments`, `read_tool`, `read_arguments` and `idempotent`, add a `policy.yaml` rule
  with `tool_name` and `arg_ranges`, set `NEWTON_MCP_RUNTIME_CONFIG` / `NEWTON_MCP_POLICY_PATH` /
  `NEWTON_MCP_AUDIT_PATH`, refresh the catalog. Then the checklist of what the actuator must
  provide for this to work end to end, each item tied to the gate that rejects it otherwise:
  the tool must appear in `list_tools` (else `tool_missing`); rendered arguments must validate
  against its `input_schema` (else `schema_mismatch`); a `read_tool` must exist and return a JSON
  object via `structured_content` or a single JSON-object text block (else the verifier gets no
  observation and the run escalates); the read tool must not declare `read_only_hint=False` (else
  the verifier escalates without calling); `idempotent: true` is required for any retry to be
  possible. Closes with an explicit "no file under `src/newton_mcp/` is edited" and a pointer to
  `examples/smart-home/README.md`'s "Why a real Alice server is not drivable yet" as the worked
  negative example. Finally, a pointer to `docs/safety.md` replaces any temptation to restate the
  defaults table here.

### 4. `README.md`

- **New `## Documentation` section**, placed immediately before `## Development`, linking all five
  `docs/` files and `examples/smart-home/README.md` with a one-line description each. Existing
  inline links stay; this section makes every doc reachable, including `docs/architecture.md`,
  which nothing currently links.
- **Status block (lines 14-18) refreshed** to three explicit claims: the MCP server and mock
  backend are functional; the real Newton adapter is implemented against public documentation and
  is not validated against a live account, activating only with an authorized `ATAI_API_KEY`; the
  action runtime and the smart-home testbed are mock-validated only, with no live actuator. The
  words "mock-validated" and "not validated against a live account" are the load-bearing ones and
  neither is softened.
- **Confirmed-versus-proposed table (lines 222-231) refreshed**: keep the four existing rows,
  split the runtime row so the lifecycle/`UNKNOWN` state machine, the JSONL audit trail, the
  executor and the verifier are each attributed to this project, and add a row pointing at
  `docs/archetype-integration.md` for the open questions. The closing "Nothing here
  reverse-engineers private endpoints" sentence stays.
- The `## Direction A` prose (lines 109-180) is left alone apart from any factual correction the
  audit pass turns up; it is already accurate and already labelled.

### 5. `tests/test_docs_consistency.py` (new, the only code)

One test module, standard library only (`ast`, `re`, `shlex`, `tomllib`, `pathlib`,
`importlib`), no network. **Corpus:** `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, every
`docs/*.md` and `examples/smart-home/README.md`. Four checks, one test function each:

- **Links.** Relative markdown links (`[text](path)`) and backticked repo paths (`` `docs/...` ``,
  `` `examples/...` ``, `` `src/...` ``, `` `tests/...` ``) resolve against the linking file (links)
  or the repo root (backticked paths) to an existing file or directory. Anchors are stripped;
  `http(s)://` and `mailto:` are skipped.
- **`demo.py` flags.** Commands are taken only from fenced code blocks (with `\` continuations
  joined) and inline code spans, and only those that contain `examples/smart-home/demo.py` (or
  start with `demo.py`). Each is tokenised with `shlex`; every token starting with `--` (value
  after `=` dropped) must be in the option strings of the parser returned by the demo module's
  `_build_parser()`, loaded with `importlib.util.spec_from_file_location` as `tests/test_demo.py`
  already does. `--word` in prose is never checked.
- **`uv run` targets.** For each `uv run <name>` in a command (leading `VAR=value` assignments
  skipped): `<name>` is a `[project.scripts]` key, or has a `[tool.<name>]` table in
  `pyproject.toml` (e.g. `pytest`), or is `python` followed by `-c`/`-m` or by a script path that
  exists. Anything else fails with the offending command and file.
- **Env var names.** Every `NEWTON_*`/`ATAI_*` token in the corpus must be in the set the code
  actually reads, collected with `ast` from `src/newton_mcp/**/*.py`: string literals passed to
  `env.get`/`os.environ.get`/`os.getenv` or used as `os.environ[...]` subscripts, the string
  elements of a tuple passed to `_resolve(...)`, and the values of module-level constants whose
  name ends in `_ENV_VAR` (`NEWTON_MCP_RUNTIME_CONFIG`, `NEWTON_MCP_AUDIT_PATH`,
  `NEWTON_MCP_POLICY_PATH`) — plus the names assigned in `.env.example`, including commented
  `# NAME=` lines. Mentions in comments or docstrings do not count, because `ast` only sees code.

Each check must be shown to bite: the implementer breaks it once in a scratch edit (a bad link, an
unknown `--flag` in a `demo.py` command, `uv run newton-mpc`, an invented `NEWTON_FOO`) and
confirms the matching test fails, then reverts. A wrong command in any corpus file, including
`examples/smart-home/README.md`, is fixed in the doc, never by weakening the test.
`pyproject.toml` already sets `testpaths = ["tests"]`, so no configuration change is needed.

### Why this shape

The organising principle is **one home per claim**. The reason the current docs are hard to audit
is not that they are wrong but that the safety argument is restated in four places, so a future
change can make two of them disagree. Moving the defaults table into `docs/safety.md` and leaving
a pointer behind means a reviewer checking "does the doc match the code?" has exactly one place to
look per claim, and a future PR that changes a default has exactly one document to update.

The second principle is **traceability over completeness**. Every sentence in the three documents
is written to name the symbol, constant, state or env var it describes, because the issue's first
acceptance criterion is a reviewer diffing the docs against the source. A claim that cannot be
traced is deleted rather than hedged.

## Alternatives

- **Split the runtime docs into several smaller files (one per module).** Rejected. The safety
  argument in this runtime is cross-module by nature: the `UNKNOWN` state only makes sense with
  the executor's timeout handling and the verifier's escalation gates in view, and the approval
  binding only makes sense with `ServerConfig.binding_identity` beside it. Splitting would
  multiply cross-references and make the audit-against-source pass harder, not easier. The
  existing single `action-runtime.md` plus a safety-invariants view is the better cut.
- **Duplicate the safety defaults table in both `docs/architecture.md` and `docs/safety.md`,
  leaving architecture.md untouched.** Rejected. Two copies of a safety table is exactly the drift
  the docs exist to prevent, and the issue's first acceptance criterion (claims match the code)
  becomes twice as expensive to check. The one-line pointer edit is small and reversible.
- **Fold the Archetype open questions into `README.md` instead of a third document.** Rejected.
  The README is the orientation page for any reader; the open questions are addressed to one
  specific audience and will change as answers arrive. A separate document can be linked from the
  outreach in issue #16 without dragging the whole README along, and keeps the README's
  confirmed-versus-proposed table short.
- **Generate the docs from docstrings (Sphinx/mkdocstrings).** Rejected. It adds a build step and
  a dependency group to a repo whose stated preference is small explicit artefacts, and generated
  prose cannot carry the safety argument — the invariants are claims about absent edges and
  deliberate omissions, which no docstring extractor can state.
- **Add no test and rely on manual review for links and commands.** Rejected at owner review:
  without `tests/test_docs_consistency.py`, acceptance criterion 3 and the reproducibility of every
  documented `demo.py` / `uv run` command and env var name are a human promise; with it, a drift
  is a CI failure.

## Platform impact

- **Migrations.** None. No schema, no persisted state, no database, no API surface. Nothing is
  generated from these documents and nothing generates them.
- **Backward compatibility.** Two link-shaped risks. First, `docs/architecture.md`'s
  `## Safety defaults` section loses its table; any external bookmark to that anchor still
  resolves because the heading is retained with a pointer. Second, nothing in `src/` references
  `docs/safety.md` or `docs/archetype-integration.md` today, so adding them breaks nothing —
  and the new docs-consistency test guards the links added in the other direction.
- **Resource impact.** Negligible. One extra test module adds a few milliseconds of filesystem
  work to `uv run pytest`; CI (`uv sync --locked --group dev && uv run pytest -q`, plus the Docker
  job) is otherwise unchanged. No new dependency: the test uses only `pathlib` and `re`.
- **Risk: a doc claim silently drifts from the code.** The document set is prose, so nothing
  enforces its accuracy the way `tests/test_action_contract.py` enforces the JSON schema.
  Mitigation: every claim names its symbol or constant, so a reviewer can grep for it; the
  audit pass is a named task with a checklist (task 2); and the constants most likely to change
  are collected into one numeric table in `docs/safety.md` rather than scattered in prose.
- **Risk: the repo reads as a pitch to an Archetype engineer.** Mitigation: an explicit
  marketing-language pass (`tasks.md` task 10) with a stated word list — no superlatives about the project, no
  claimed adoption, partnership, endorsement or benchmark, no buyer-facing call to action, no
  mention of mctl.ai — and the "this project's proposal" and "mock-validated" wording preserved in
  every document's opening block.
- **Risk: an open question is phrased as an assertion about Archetype's roadmap.** Mitigation:
  every open question is written as a question, paired with what this project assumes in the
  absence of an answer, and the confirmed section cites only doc pages the code already cites.
- **Risk: the status line overstates validation.** Mitigation: the README status block and all
  three documents use "mock-validated" for anything not run with real credentials, and
  `examples/smart-home/README.md`'s existing "What this is not" section is the reference wording
  the new documents follow.
- **Risk: scope creep into code.** Mitigation: a task-level constraint that `git diff --stat` for
  this change touches only `README.md`, `docs/*.md`, `tests/test_docs_consistency.py` and, only
  if the test finds a mismatch, `examples/smart-home/README.md`, verified as
  `tasks.md` task 11's definition of done.
