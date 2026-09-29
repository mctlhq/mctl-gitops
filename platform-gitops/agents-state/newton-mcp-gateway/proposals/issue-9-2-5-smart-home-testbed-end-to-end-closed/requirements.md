# Smart-home testbed and end-to-end closed-loop demo (examples/smart-home/)

## Context

Every piece of the Direction A pipeline now exists in `src/newton_mcp/` and is unit-tested in
isolation: `action/propose.py` turns an observation into a `PhysicalActionContract`,
`runtime/catalog.py` discovers MCP tools behind a `runtime.yaml` allow-list, `runtime/resolver.py`
ranks candidates, `action/policy.py` decides auto/confirm/deny, `action/approval.py` binds an
approval to one exact action, `runtime/executor.py` calls the tool, `runtime/verifier.py`
re-observes the world, and `runtime/audit.py` writes an append-only JSONL trail. Nothing in the
repository has ever run those pieces *together*: there is no artefact a reviewer can execute that
walks a single observation from "kitchen 29.4 C, occupied" through to a verified physical outcome,
and no committed trace showing the four correlation ids travelling along one action.

This proposal adds that artefact as a self-contained testbed under `examples/smart-home/`: a
`runtime.yaml` + `policy.yaml` pair describing benign, reversible smart-home capabilities, an
in-process fake MCP actuator (`fake_alice.py`) with a simulated room, and a `demo.py` that runs the
whole loop and prints a human-readable trace while writing a JSONL audit. The first real actuator
target is an existing smart-home MCP server ("Alice") chosen because it is real hardware with
benign, reversible actions; real mode is opt-in and never runs in CI. The runtime must remain
actuator-agnostic, so `src/newton_mcp/` gains nothing Alice-specific — everything actuator-specific
lives under `examples/smart-home/`. Both the Physical Action Contract and the action runtime remain
**this project's experimental proposal**, not an Archetype standard, and every result this proposal
produces is **mock-validated** until it has been run against a real Newton account and a real Alice
server.

## User stories

- AS a reviewer of this project I WANT one command that walks an observation through contract,
  resolution, policy, approval, execution and verification SO THAT I can judge the closed-loop
  claim by running it instead of reading seven modules.
- AS a reviewer I WANT a committed `trace.jsonl` from a recorded mock run SO THAT I can see the
  full lifecycle and all four correlation ids without running anything.
- AS a safety reviewer I WANT the failure path (an AC that answers successfully while the room
  never cools) to end `ESCALATED` rather than `SUCCEEDED` SO THAT I can see that digital success is
  not treated as physical success.
- AS a safety reviewer I WANT a temperature outside the configured 20-25 C band to be refused by
  `policy.yaml` before any tool call SO THAT the enforcement point is the operator's policy file,
  not the actuator's own schema.
- AS an operator I WANT a non-idempotent action (a speaker announcement) to be called exactly once,
  never retried SO THAT an unverifiable action cannot be repeated in the physical world.
- AS a maintainer I WANT the demo to run offline, deterministically and without credentials in CI
  SO THAT the closed loop is regression-tested on every pull request.
- AS a maintainer I WANT real Newton and real Alice to be strictly opt-in via env-only credentials
  SO THAT CI can never touch real hardware and no secret enters the repository.

## Acceptance criteria (EARS)

### The demo run

- WHEN `uv run python examples/smart-home/demo.py --mock` is invoked THE SYSTEM SHALL run the full
  chain observation -> `propose_action` (mock Newton backend) -> resolver -> policy -> approval ->
  executor -> verifier, print a step-by-step trace to stdout, append one JSONL audit line per
  accepted lifecycle transition, and end in `ActionState.SUCCEEDED` with exit code 0.
- WHEN the demo runs in `--mock` mode THE SYSTEM SHALL use `MockNewtonBackend` and the in-process
  `fake_alice` MCP server only, opening no socket, spawning no subprocess and reading no credential.
- WHILE running in `--mock` mode THE SYSTEM SHALL label every mock-derived artefact in its printed
  trace (the proposal result's `backend: "mock"`, the contract's `[mock] ` reason prefix, and an
  explicit note that the actuator is a fake), so no output can be read as a live integration.
- WHEN the demo resolves a contract THE SYSTEM SHALL print every candidate with its `score` and
  `why`, and every rejection with its stage and detail, before applying policy.
- WHEN the policy decision is `auto` THE SYSTEM SHALL create an `Approval` via
  `create_approval(...)` with `approved_by = "policy:<policy_version>:<rule name>"`, so there is
  exactly one execution path and no approval-less bypass.
- IF the policy decision is `confirm` AND the demo is in `--mock` mode THEN THE SYSTEM SHALL
  auto-approve and record `approved_by` as an explicitly mock-labelled value.
- IF the policy decision is `confirm` AND the demo is NOT in `--mock` mode THEN THE SYSTEM SHALL
  prompt on stdin and proceed only on an explicit affirmative answer.
- IF the policy decision is `deny` THEN THE SYSTEM SHALL transition the record `PROPOSED -> DENIED`,
  print the policy reason, make no MCP `call_tool` at all, and exit with the documented denied exit
  code.
- WHEN the demo finishes THE SYSTEM SHALL print the terminal `ActionState`, the number of actuator
  tool calls issued, the number of verification observations obtained, all four correlation ids, and
  the audit file path.

### The failure path

- WHEN the demo is invoked with the "AC offline" flag THE SYSTEM SHALL have `fake_alice` answer the
  actuator call with a *successful* result while leaving the simulated room temperature unchanged,
  so the run demonstrates a digital success with no physical effect.
- WHEN the AC-offline run reaches verification THE SYSTEM SHALL obtain at least one observation,
  never satisfy `verification.condition`, transition `VERIFYING -> FAILED`, and — because the
  capability is `idempotent: true` — retry at most `contract.verification.retry_limit` times before
  ending `ESCALATED`.
- WHILE an action's resolved capability is `idempotent: false` (the speaker announcement) THE
  SYSTEM SHALL issue exactly one actuator tool call for the whole run and end `ESCALATED`, never
  issuing a second call.
- IF verification obtains zero observations THEN THE SYSTEM SHALL end `ESCALATED` and never
  `FAILED` (unchanged behaviour of `runtime/verifier.py`, asserted by the demo tests).

### Configuration files

- WHEN `examples/smart-home/runtime.yaml` is loaded with
  `newton_mcp.runtime.load_runtime_config()` THE SYSTEM SHALL validate successfully and declare
  capabilities covering: set AC temperature, light on/off, light brightness, and speaker
  announcement, each with an explicit `idempotent:` value.
- WHILE `examples/smart-home/runtime.yaml` is the loaded allow-list THE SYSTEM SHALL expose the
  device-state read path only as `read_tool: get_room_state` on each actuator capability, and SHALL
  declare no capability whose tool or goal prefix names a lock, oven, alarm, industrial start/stop
  or safety system.
- WHEN `examples/smart-home/policy.yaml` is loaded with `newton_mcp.action.load_policy()` THE
  SYSTEM SHALL validate successfully, carry `default: deny`, and bound the AC temperature argument
  with an inclusive `arg_ranges` entry of `min: 20, max: 25`.
- IF a resolved AC action carries a `target_temperature_c` outside 20-25 THEN THE SYSTEM SHALL
  return `Decision.DENY` from `Policy.evaluate(...)` naming that argument, and no actuator tool
  call SHALL be issued.
- WHILE `fake_alice`'s `set_ac_temperature` input schema accepts any integer THE SYSTEM SHALL leave
  the 20-25 band enforced by `policy.yaml` alone, so the denial is provably the policy's and not a
  `schema_mismatch` rejection in the resolver.
- WHEN `fake_alice` advertises its read tool THE SYSTEM SHALL annotate it `read_only_hint=True` and
  return a mapping whose top-level key `temperature_c` is the path the contract's
  `verification.condition` reads.

### Audit trace

- WHEN the demo runs with an audit path THE SYSTEM SHALL write through
  `newton_mcp.runtime.JsonlAuditSink`, one line per accepted transition, appending rather than
  truncating unless an explicit overwrite flag is given.
- WHILE the committed `examples/smart-home/trace.jsonl` exists THE SYSTEM SHALL keep it a recorded
  mock success run whose lines form the chain `PROPOSED -> AUTHORIZED -> EXECUTING -> EXECUTED ->
  VERIFYING -> SUCCEEDED`, each line carrying non-empty `observation_id`, `action_id`,
  `tool_call_id` and `verification_id`, and containing no credential, no API key and no real device
  identifier or hostname.
- WHEN the demo is invoked with its deterministic flag THE SYSTEM SHALL use a counter-based
  `id_factory` and a fixed, stepped clock so the committed trace can be regenerated by a documented
  command.

### Real mode and isolation

- IF `--real` is given THEN THE SYSTEM SHALL read Newton credentials from `ATAI_API_KEY` /
  `ATAI_API_ENDPOINT` and the Alice MCP endpoint from an environment variable only, never from a
  committed file or a command-line argument, and SHALL fail loudly naming the missing variable when
  one is absent.
- WHILE any test runs THE SYSTEM SHALL never select `--real`, never open a socket and never read a
  credential; CI SHALL exercise `--mock` only.
- WHILE this proposal is implemented THE SYSTEM SHALL add no Alice-specific name, tool shape,
  hostname or import to `src/newton_mcp/`, asserted by a test that greps the package.
- WHEN documentation describes results from this testbed THE SYSTEM SHALL describe them as
  "mock-validated", and SHALL keep describing the Physical Action Contract and the action runtime as
  this project's experimental proposal rather than Archetype behaviour.
- WHILE this change is implemented THE SYSTEM SHALL add no new runtime dependency, so `uv.lock`
  stays byte-unchanged and CI's `uv sync --locked` keeps passing.

### README

- WHEN the root `README.md` is read THE SYSTEM SHALL contain a "Demo" section carrying the exact
  `uv run python examples/smart-home/demo.py --mock` command, a short excerpt of the success trace,
  and a short excerpt of the AC-offline run ending `ESCALATED`, both labelled mock.
- WHEN `examples/smart-home/README.md` is read THE SYSTEM SHALL document the capability set, the
  two paths, every CLI flag and exit code, the regeneration command for `trace.jsonl`, and the
  opt-in real-mode variables.

## Out of scope

- Any change to the Alice smart-home MCP server itself.
- Locks, ovens, alarms, industrial start/stop and any safety-critical device — excluded by the
  epic's hard rules and by the allow-list this proposal ships.
- Home Assistant integration (issue #14).
- A second demo scenario beyond the kitchen cooling loop. The speaker announcement exists as a
  *capability* in `runtime.yaml`/`policy.yaml` and is exercised by `tests/test_demo.py` to prove the
  non-idempotent single-call rule; it is not a second CLI scenario.
- Exposing the runtime or this demo as new MCP tools on `create_server()`, and any wiring of the
  runtime into `newton_mcp.config.Settings`.
- Signed approvals, an authenticated approver, approval revocation or nonce semantics (issue #7
  territory, per `action/approval.py`).
- Any change to `PhysicalActionContract`, `schemas/physical-action-contract.schema.json`, the
  lifecycle table, the policy engine or the verifier's semantics. This proposal composes
  `src/newton_mcp/` as it stands; a needed change there is a finding to report, not work to do here.
- Log rotation, multi-process audit coordination, Temporal, Kubernetes, a database or a UI.

## Open questions

1. **The real Alice server's exact tool names and schemas are not documented anywhere in this
   clone.** `fake_alice.py` therefore defines a plausible shape (`get_room_state`,
   `set_ac_temperature`, `set_light_state`, `set_light_brightness`, `announce`) and
   `examples/smart-home/runtime.yaml` maps to exactly that shape. Proceeding on that basis: the
   fake is the contract for mock mode, and `--real` may require the operator to edit the capability
   mapping. The README states this. The committed `runtime.yaml` uses a deliberately non-resolvable
   placeholder URL (`https://alice.invalid/mcp`, RFC 2606) so the committed file names no real host.
2. **"Read device state" as a capability.** `runtime.yaml` capabilities are actuator capabilities:
   each needs `goal_prefixes` and would be proposed as an *action*. Proceeding by expressing the
   read path as `read_tool: get_room_state` on every actuator capability (which is what the verifier
   actually calls) rather than inventing a standalone read "action". If the reviewer wants a
   contract whose goal is "read the room", that is a separate issue.
3. **"the tool was called once only when the action is non-idempotent"** admits two readings.
   Proceeding with both covered by tests: the AC-offline run (idempotent capability,
   `retry_limit: 1` from the mock contract) issues at most two calls and ends `ESCALATED`, and the
   announcement capability (`idempotent: false`) issues exactly one call and ends `ESCALATED`. If the
   reviewer meant that the AC-offline run itself must issue exactly one call, that is achieved by a
   contract with `retry_limit: 0`, which `MockNewtonBackend` does not currently emit (it returns
   `MOCK_CONTRACT_EXAMPLE` with `retry_limit: 1`).
4. **Wall-clock time in the failure path.** The mock contract's
   `verification.timeout_seconds` is 600, so a real-clock verifier would block CI for ten minutes
   per failed attempt. Proceeding by injecting the `Verifier`'s existing `clock`/`sleep` seam with a
   simulated clock in `--mock` mode (the same technique `tests/runtime/conftest.py::DeterministicClock`
   uses) and the real `anyio` clock in `--real` mode. No `src/` change is needed; the seam already
   exists.
5. **`anyio` is imported across `src/newton_mcp/runtime/` but is not a declared dependency** (it
   arrives transitively through `mcp`). `demo.py` needs `anyio.run`. Proceeding without declaring
   it, to keep `uv.lock` byte-unchanged for CI's `--locked` install; declaring it properly is a
   separate, lock-touching change.
6. **`trace.jsonl` scope.** Proceeding with the committed trace being the *success* run only (one
   `action_id`, six-state chain). The AC-offline excerpt in the README comes from the demo's printed
   stdout trace, because appending two runs into one file would put two unrelated `action_id`s in
   one artefact.
