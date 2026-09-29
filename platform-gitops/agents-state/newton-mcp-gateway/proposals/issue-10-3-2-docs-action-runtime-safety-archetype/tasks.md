# Tasks: issue-10-3-2-docs-action-runtime-safety-archetype

> **Amended at owner review (2026-09-29).** The link-only test becomes a docs-consistency test
> (`tests/test_docs_consistency.py`): relative links, `demo.py` flags, `uv run` targets and env
> var names in the doc corpus are checked against the real parser, `pyproject.toml`, env
> lookups and `.env.example`. `examples/smart-home/README.md` joins the corpus. The confirmed
> Archetype table cites a concrete public doc page per row, the upload ceiling is written
> "512 MB", and `task-verification` is described as its public page describes it.

- [ ] 1. Build a claims-to-source index for the doc set: for every constant, state, symbol and env
      var the three documents will name, record the file and line in `src/` that defines it
      (`contract.py`, `conditions.py`, `runtime/config.py`, `runtime/catalog.py`,
      `runtime/resolver.py`, `action/policy.py`, `action/approval.py`, `runtime/lifecycle.py`,
      `runtime/audit.py`, `runtime/executor.py`, `runtime/verifier.py`, `config.py`, `server.py`).
      Keep it as working notes, not a committed file.
      — DoD: a list covering at least `ALLOWED_TRANSITIONS`, `Risk`, `Decision`,
      `MAX_CONDITION_DEPTH`, `MAX_TOOL_PAGES`, `BASE_SCORE`/`GOAL_WEIGHT`/`LOCATION_BONUS`/
      `READ_TOOL_BONUS`, `DEFAULT_SERVER_TIMEOUT_SECONDS`, `DEFAULT_CALL_TIMEOUT_SECONDS`,
      `DEFAULT_POLL_INTERVAL_SECONDS`, `DEFAULT_READ_TIMEOUT_SECONDS`, `SECRET_KEY_PATTERNS`,
      `CONSERVATIVE_POLICY_VERSION`, the `Verification` defaults, and the three runtime env vars,
      each with its exact current value.

- [ ] 2. Audit `docs/action-runtime.md` against the index from task 1 and correct every mismatch
      (depends on 1). Check in particular the `ALLOWED_TRANSITIONS` block, the score formula, the
      resolver filter-chain order, the `Policy.evaluate()` order, the approval binding payload, the
      redaction substring list (the doc writes "..." where `SECRET_KEY_PATTERNS` has eleven
      entries), and every env var name.
      — DoD: no claim in the file contradicts `src/`; every constant printed in the file equals the
      value in the module that defines it; the existing "this project's experimental proposal" and
      "mock-validated only" blockquote is unchanged or strengthened, never weakened.

- [ ] 3. Add a "Contract v0.2 at a glance" section to `docs/action-runtime.md`, before
      "Verification conditions" (depends on 1). Field tables for `PhysicalActionContract`,
      `Target`, `Verification` and `Evidence` with types and defaults; the `Risk` ladder
      (`read_only`, `low`, `medium`, `high`, `critical`); the `^0\.2$` version pin and the
      no-v0.1-migration-shim note; pointers to `schemas/physical-action-contract.schema.json` and
      to `CONTRIBUTING.md` for the regeneration command.
      — DoD: every field, type and default in the section matches
      `src/newton_mcp/action/contract.py`; the existing "Verification conditions (contract v0.2)"
      section keeps all of its current detail.

- [ ] 4. Add an "Adding an MCP actuator by configuration only" section to
      `docs/action-runtime.md`, after "Verifier" (depends on 1). A worked `runtime.yaml` +
      `policy.yaml` example using a safe capability class, the three env vars to set, and the
      actuator-side checklist tied to the gate that rejects each omission (`tool_missing`,
      `schema_mismatch`, no observation, `read_only_hint=False`, `idempotent` required for any
      retry). Close with "no file under `src/newton_mcp/` is edited" and a pointer to
      `examples/smart-home/README.md`'s "Why a real Alice server is not drivable yet".
      — DoD: the section names no capability outside the demo-safe set; every rejection reason it
      names exists in `src/newton_mcp/runtime/resolver.py` or `runtime/verifier.py`; a reader can
      follow it without editing any Python file.

- [ ] 5. Write `docs/safety.md` (depends on 1). Seven sections per `design.md`: status blockquote;
      action-class defaults table (moved from `docs/architecture.md:70-77`, with denied classes
      kept as `deny` rows and each allowed row cross-referenced to the example rule that realises
      it); numeric defaults table; invariants, each with the enforcing code location and the
      failure it prevents; demo-safe actions plus the never-permitted classes; known limitations;
      non-goals.
      — DoD: the file exists, states the "this project's experimental proposal" wording in its
      opening block, contains both tables, states at least the six invariants named in
      `requirements.md`, lists locks/ovens/alarms/industrial start-stop/safety systems as never
      permitted, and records every limitation named in `requirements.md` rather than omitting any.

- [ ] 6. Reduce `docs/architecture.md`'s `## Safety defaults` section to the heading plus a
      one-line pointer to `docs/safety.md` (depends on 5). Keep the heading text so any existing
      anchor still resolves.
      — DoD: the action-class table exists in exactly one file in the repository
      (`docs/safety.md`); `grep -rn "unlock door" docs/` returns one file; nothing else in
      `docs/architecture.md` changes.

- [ ] 7. Write `docs/archetype-integration.md` (depends on 1). Part 1: confirmed from Archetype
      public docs, as a table with a source column, restricted to endpoints, request/response
      fields, event types, model families and env var names the code already cites
      (`/query`, `/v0.5/files`, `/v0.5/files/base64`, `DataEvent`/`EventType`, `Newton::c2_...`,
      `OmegaEncoder::...`, 768-dim, `ATAI_API_KEY`/`ATAI_API_ENDPOINT`, the Agents API
      blueprint → bundle → run concepts). Every row cites a concrete docs.archetypeai.app page
      (Agents rows: `core-concepts/agents/overview.md`, `api.md`, the five blueprint pages and the
      `api-reference/agents/*` pages listed in design §3), the upload ceiling is "512 MB", the
      Agents API is stated as not wired into this gateway (#13), and `task-verification` is
      described per its public page (SOP compliance from video) with its suitability for
      verifying a commanded physical outcome stated as not confirmed.
      Part 2: proposed by this project, each row naming its module. Part 3: the four open questions
      for Archetype engineers (Newton Agents' external-
      system integration model; sink/action connectors in the node registry; confidence and
      provenance in outputs; post-action verification support), each paired with what this project
      assumes today and the module that assumption lives in. Close with the
      no-reverse-engineering and not-affiliated statements.
      — DoD: no endpoint, parameter or model id appears that is not already present in `src/` with
      a cited public doc page; the confirmed and proposed parts are visually separate; all four
      open questions are phrased as questions and each names the module carrying the current
      assumption.

- [ ] 8. Update `README.md` (depends on 2, 3, 4, 5, 7). Add a `## Documentation` section before
      `## Development` linking `docs/architecture.md`, `docs/action-runtime.md`, `docs/safety.md`,
      `docs/archetype-integration.md`, `docs/newton-api-notes.md` and
      `examples/smart-home/README.md`, one line each. Refresh the status block (lines 14-18) to
      three explicit claims: MCP server and mock backend functional; real Newton adapter
      implemented against public docs and not validated against a live account; action runtime and
      smart-home testbed mock-validated only, no live actuator. Refresh the
      confirmed-versus-proposed table (lines 222-231) to attribute the lifecycle/`UNKNOWN` state
      machine, the JSONL audit trail, the executor and the verifier to this project, and add a row
      pointing at `docs/archetype-integration.md`.
      — DoD: every `docs/` file and `examples/smart-home/README.md` is reachable from the README;
      the status block uses "mock-validated" and "not validated against a live account" and claims
      no live validation anywhere; the table's source attributions are each defensible against
      `docs/archetype-integration.md` part 1.

- [ ] 9. Add `tests/test_docs_consistency.py` (depends on 8), exactly as design §5: corpus
      `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `docs/*.md`, `examples/smart-home/README.md`;
      four checks — relative links resolve; `--flags` in commands that invoke
      `examples/smart-home/demo.py` are accepted by its `_build_parser()`; `uv run <name>` targets
      are a `[project.scripts]` key, a `[tool.<name>]` tool or `python` + existing script/`-c`/`-m`;
      `NEWTON_*`/`ATAI_*` names are read by code (ast-collected lookups, `_resolve` tuples,
      `*_ENV_VAR` constants) or assigned in `.env.example`. Standard library only, no network.
      Fix any doc the test flags (including `examples/smart-home/README.md`), never the test.
      — DoD: the module passes on the updated tree; each of the four checks fails on its own
      deliberate scratch break (T1–T4), then reverts; no entry added to `pyproject.toml`.

- [ ] 10. Marketing-language and hard-rules pass over the full diff (depends on 2, 3, 4, 5, 6, 7,
      8). Remove superlatives about the project, any claimed adoption, partnership, endorsement or
      benchmark, and any buyer-facing call to action. Confirm no mention of mctl.ai or DevLoop, no
      emoji, English only, and that every document's opening block carries the "this project's
      experimental proposal" wording.
      — DoD: `grep -rin "mctl\|devloop" README.md docs/` returns nothing; no document claims a live
      Newton or live actuator validation; each of `docs/action-runtime.md`, `docs/safety.md`,
      `docs/archetype-integration.md` contains the proposal disclaimer in its first ten lines.

- [ ] 11. Scope check and green build (depends on 9, 10).
      — DoD: `git diff --stat` touches only `README.md`, `docs/action-runtime.md`,
      `docs/architecture.md`, `docs/safety.md`, `docs/archetype-integration.md` and
      `tests/test_docs_consistency.py` (plus `examples/smart-home/README.md` only if task 9 flagged
      it) — nothing under `src/newton_mcp/`, `schemas/`, or any other file under `examples/`;
      `uv sync --locked --group dev && uv run pytest -q` is green.

## Tests

- [ ] T1. `tests/test_docs_consistency.py::test_relative_links_resolve` — every relative link and
      backticked repo path in the corpus resolves. Bites on a link to `docs/does-not-exist.md`.
- [ ] T2. `tests/test_docs_consistency.py::test_demo_commands_use_real_flags` — every `--flag` in a
      command invoking `examples/smart-home/demo.py` is a `_build_parser()` option. Bites on
      `--mock --no-such-flag` in a README code block; a `--word` in prose does not trip it.
- [ ] T3. `tests/test_docs_consistency.py::test_uv_run_targets_exist` — every `uv run <name>` is a
      `[project.scripts]` key, a `[tool.<name>]` tool, or `python` + existing path/`-c`/`-m`. Bites
      on `uv run newton-mpc` and on `uv run python examples/smart-home/nope.py`.
- [ ] T4. `tests/test_docs_consistency.py::test_env_vars_are_read_by_code` — every
      `NEWTON_*`/`ATAI_*` name in the corpus is ast-collected from real lookups or assigned in
      `.env.example`. Bites on an invented `NEWTON_FOO`, and still bites when `NEWTON_FOO` is
      added only to a comment under `src/`.
- [ ] T5. Regression: `uv run pytest -q` is fully green, in particular
      `tests/test_action_contract.py` (the committed JSON schema is untouched by this change) and
      `tests/test_demo.py` (the demo and its trace are untouched).
- [ ] T6. Manual claim-diff review, recorded in the PR description: for each of
      `ALLOWED_TRANSITIONS`, the resolver score constants, the resolver rejection-reason order, the
      `Policy.evaluate()` order, the approval binding payload, the four verifier escalation gates,
      the `Verification` defaults, and the three runtime env var names, state the `src/` file and
      line the doc claim was checked against. This is the mechanism for acceptance criterion 1;
      no automated test can replace it.
- [ ] T7. Manual wording review, recorded in the PR description: confirm each of the three
      documents carries the proposal disclaimer, that no document claims live validation, and that
      no marketing language or mctl.ai reference is present.

## Rollback

Documentation-only plus one test, so rollback is a plain revert with no state to unwind.

- Full rollback: `git revert <merge commit>`. No migration, no generated artefact, no persisted
  state, no dependency change. `src/newton_mcp/`, `schemas/` and `examples/` were never touched, so
  no runtime behaviour can regress.
- Partial rollback if only the new test is unwanted (for example if the owner reads "no new code"
  strictly): delete `tests/test_docs_consistency.py`. The three documents and the README changes stand
  on their own; acceptance criterion 3 and the command checks revert to a manual check.
- Partial rollback if the `docs/architecture.md` edit is unwanted: restore its
  `## Safety defaults` table from git history. `docs/safety.md` then duplicates it, which is worse
  but not broken; prefer instead to move the canonical copy back into `architecture.md` and leave
  the pointer in `docs/safety.md`, so the table still exists in exactly one place.
- If a doc claim is found to be wrong after merge, the fix is a follow-up documentation PR, not a
  revert: no consumer depends on these files programmatically apart from `tests/test_docs_consistency.py`,
  which checks link targets and never content.
