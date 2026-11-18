# Spike: evaluate Claude Code Code Mode for read-only interactive tool orchestration and governance

## Context

Issue mctlhq/mctl-agents#1096 asks for a research-only evaluation of Anthropic's
Claude Code "Code Mode". It is an experimental, interactive-terminal-only mode in
which the model writes JavaScript that makes several CLI tool calls in one step.
The question is whether it measurably improves MCTL owner/operator research
workflows without weakening per-action authority, policy, evidence or incident
explainability, and what, if anything, carries over to the agent runtime. The
issue is research intake only. It authorizes reading public documentation and
repository code and producing a PROPOSED report and benchmark protocol. It does
not authorize any Code Mode run, any change to developer or organization
settings, or any runtime code.

This matters because the mctl-agents runtime is built on the headless Claude
Agent SDK (`orchestrator/options.py`, `claude-agent-sdk==0.2.174`, bundled CLI
2.1.310). Its governance (policy checkpoint per MCP call, Bash audit, capability
gateway, evidence envelope, usage ledger) is attached to SDK hooks. The official
Code Mode documentation (https://code.claude.com/docs/en/code-mode, fetched
2026-11-18) says Code Mode requires CLI v2.1.323 or later and does not work with
`-p`, the Agent SDK, VS Code, Desktop or cloud sessions. It also refuses to start
when OpenTelemetry export, `DISABLE_TELEMETRY`, an API key helper or a
gateway/custom base URL is configured. Any value is therefore confined to
interactive operator sessions. Those sessions sit outside the governed runtime,
so the spike has to state exactly which MCTL controls do and do not apply there.

## User stories

- AS the platform owner I WANT an evidence-backed compatibility matrix of Code
  Mode against the MCTL runtime surfaces SO THAT I do not approve an integration
  that the vendor does not support headlessly.
- AS a security reviewer I WANT a threat model that maps each Code Mode risk
  (dynamic arguments, shell composition, classifier-on-code, hook failure,
  parallel child calls) to an existing MCTL control or to an explicit gap SO
  THAT no second policy engine is introduced and no gap is silently assumed
  closed.
- AS the benchmark owner (mctlhq/mctl-agents#597) I WANT a pre-registered,
  read-only, three-task, 5-repetition protocol with independent oracles SO THAT
  a later, separately approved run produces comparable numbers without
  duplicating #597's deliverables.
- AS an incident responder I WANT a defined correlation from one Code Mode
  script to each consequential tool call SO THAT an interactive session that
  touches MCTL can still be explained after the fact.

## Acceptance criteria (EARS)

- WHEN the spike report is produced THE SYSTEM SHALL include a compatibility
  matrix covering CLI normal tools, CLI Code Mode, MCTL headless Agent SDK/`-p`,
  mctl-native discover/describe/invoke (ADR 017 gateway), Cloudflare Portal Code
  Mode (mctlhq/.github#63) and API Programmatic Tool Calling. The matrix SHALL
  have rows for runtime/deployment, model eligibility, hooks, limits, billing,
  audit, security and task fit.
- WHEN a matrix cell cites a vendor fact THE SYSTEM SHALL pin the source URL and
  fetch date. WHEN it cites repository behaviour THE SYSTEM SHALL pin the file
  path and the mctl-agents commit (`2227b47427e82bd2f66a7b2c784042cd76691000`
  at intake).
- IF a behaviour was not observed in documentation or code THEN THE SYSTEM SHALL
  mark it `UNKNOWN`. IF a measurement was not executed THEN THE SYSTEM SHALL
  mark it `NOT_RUN`. Neither is ever recorded as PASS.
- THE SYSTEM SHALL state that Code Mode is not applicable to the headless
  DevLoop (Argo/Temporal pods running `ClaudeSDKClient`). It SHALL cite the
  documented surface exclusion and the bundled CLI version 2.1.310 < 2.1.323,
  and SHALL make no claim of CI or headless applicability.
- WHEN the threat model is written THE SYSTEM SHALL cover at least: JS side
  effects, runtime-derived arguments, `cd ... &&` shell composition, tool
  allowlist versus invocation permission, the auto-mode classifier reviewing
  code rather than calls, fail-closed hook behaviour, cross-tenant principal
  propagation, nested/parallel child calls, cancellation and the 10-minute /
  2-hour limits, retry/idempotency, egress, secret exposure, attacker-supplied
  tool output, and script-to-action audit reproducibility. Each entry SHALL map
  to an existing MCTL control (ADR 011, 014, 017, 018, 022/023) or to an
  explicit gap.
- THE SYSTEM SHALL require, for every child call that reaches an MCTL
  consequential action: the actor and tenant, the exact (digested) arguments, an
  action-time policy decision (ADR 014 `decide()` semantics), and a durable audit
  record. IF any of these is unknown at call time THEN the call SHALL be treated
  as DENY.
- WHEN the benchmark protocol is written THE SYSTEM SHALL define three
  synthetic/read-only tasks: (A) multi-file repository research, (B) GitHub CI
  evidence collection from a fixture, (C) aggregation over two or more MCP
  sources using fixture/sanitized data. Each task SHALL have the same pinned CLI
  version, model, prompt, permission profile, identity and fixtures in normal
  CLI and Code Mode, at least 5 repetitions per task per mode, an independent
  oracle, and a negative-test matrix. Every cell starts `NOT_RUN`.
- THE SYSTEM SHALL record, per run, the initial AND total input/output/cache
  tokens, turns, tool invocations, p50/p95 latency, JS/REPL overhead, cost,
  oracle correctness, permission denials and per-child correlation completeness.
  It SHALL keep this baseline separate from unverified vendor claims.
- WHEN the recommendation is written THE SYSTEM SHALL choose exactly one of
  `CLI_ONLY_PILOT`, `FURTHER_RESEARCH`, `DEFER`, `REJECT`. It SHALL name the gate,
  owner, expected cost, required evidence and permission review needed before
  any further benchmark or integration, and SHALL cross-link #597, #181/#151 and
  #63.
- WHILE this proposal is open THE SYSTEM SHALL change no runtime code, no
  settings, no `.claude/` configuration and no deployment. Output is limited to
  documentation and fixtures.

## Out of scope

- Executing any Code Mode or normal-CLI benchmark run. That needs a separate,
  explicit owner GO.
- Setting `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE` in any user, project, managed or
  pod environment, or changing organization settings.
- Bumping `claude-agent-sdk` or the bundled CLI, or changing
  `orchestrator/options.py`, the policy checkpoint, the capability gateway or
  tracing.
- Reopening Cloudflare Portal Code Mode testing (mctlhq/.github#63 is PARK).
- Producing #597's Enterprise MCP benchmark reports, building a JS sandbox or
  gateway, or adding a second policy engine.
- Any MCP write, Telegram message, production GitHub mutation, live user data,
  or private content in telemetry.

## Open questions

- Interactive operator workflows: the repository contains no `.claude/`
  directory, settings file or runbook that defines how owners/operators run
  interactive Claude Code against MCTL. Their current hooks, permission mode and
  MCP connector configuration are `UNKNOWN`. The protocol assumes a dedicated,
  freshly configured benchmark profile rather than an operator's real setup.
- Whether the operator accounts are eligible (subscription or Console, not ZDR
  or HIPAA, and no managed setting forcing the flag to `0`) is `UNKNOWN`. It is
  the first item to verify after an owner GO.
- Telemetry conflict: Code Mode refuses to start with
  `CLAUDE_CODE_ENABLE_TELEMETRY` or `DISABLE_TELEMETRY`. Whether the owner
  accepts a benchmark arm that has no CLI OpenTelemetry export, with evidence
  coming from transcripts and hooks only, is an owner decision. The protocol
  assumes yes, and requires that normal-CLI runs also have export off so the
  arms stay comparable.
- Where the remote mctl MCP server is reached from in interactive sessions
  (direct OAuth connector, or via a gateway that would disable Code Mode) is
  `UNKNOWN`. Task C therefore uses local fixture MCP servers only.
- Who owns the follow-on benchmark execution and budget: #597's owner or this
  issue's author. The proposal assigns it to #597's owner for reporting and
  leaves funding to the owner GO.
