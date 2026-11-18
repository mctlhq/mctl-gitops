# Spike #1096: evaluate interactive Claude Code Code Mode for read-only operator research, without weakening per-action governance

## Context

Issue mctlhq/mctl-agents#1096 asks for a research-only spike. The question is
whether Anthropic's opt-in, terminal-interactive Claude Code "Code Mode"
measurably improves MCTL owner/operator research workflows. In Code Mode the
model writes JavaScript that calls the normal CLI tools (issue cites
code.claude.com/docs/en/code-mode, CLI >= 2.1.323). The spike must also show
the improvement costs nothing in exact per-action authority, policy, evidence
or incident explainability, and say what, if anything, carries over to the
mctl-agents runtime. The issue reports, without verification here, that Code
Mode does not run under `-p`, the Agent SDK, desktop/cloud, browser remote
control or the VS Code panel.

This matters because every DevLoop agent in this repo runs headless through
the Agent SDK. `orchestrator/run_issue_investigator.py`, `run_implementer.py`,
`run_shepherd.py` and the other runners use `ClaudeSDKClient`, and the CLI is
pinned through `claude-agent-sdk==0.2.174` in `pyproject.toml`. Governance
depends on per-call `PreToolUse` hooks in `orchestrator/options.py`
(`_PolicyCheckpointHook`, `_audit_pre_tool_use`, `_ReadOnlyDirsHook`,
deadline guards), on `orchestrator/policy_checkpoint.py` (ADR 014), on the
CapabilityGateway (`orchestrator/capability_gateway.py`, ADR 017) and on
durable decision records (`orchestrator/decision_records.py`). A mode that
composes many tool calls from one model-authored script changes the unit
those controls see. The spike has to record evidence and a decision memo,
and change no runtime code.

## User stories

- AS the platform owner I WANT a pinned, source-cited compatibility matrix of
  the six tool-orchestration surfaces SO THAT I know where Code Mode can and
  cannot run before I authorize any experiment.
- AS a security reviewer I WANT a threat model and a negative-test matrix
  tying every child tool call of a Code Mode script to an actor, tenant,
  exact arguments, action-time policy decision and durable audit record SO
  THAT adoption cannot quietly weaken per-action governance.
- AS the owner of the #597 benchmark I WANT a governed, read-only, 3-task
  x 2-mode x >=5-rep protocol that reuses the #597 counting rules SO THAT a
  later approved run produces results comparable with my reports rather than
  a competing benchmark.
- AS an incident responder I WANT to know what the `Ctrl+O` REPL transcript,
  hooks and telemetry show for a Code Mode script SO THAT I can reconstruct
  which action came from which script line.
- AS the platform owner I WANT a recommendation memo
  (`CLI_ONLY_PILOT` / `FURTHER_RESEARCH` / `DEFER` / `REJECT`) with named
  gates, owner, cost and blockers SO THAT the next step is an explicit,
  separately approved decision.

## Acceptance criteria (EARS)

- WHEN the spike report is written THE SYSTEM SHALL pin every external source
  (URL, retrieval date, CLI version named by the source) and every inspected
  repository revision (mctl-agents commit, mctl-gitops path) it relies on.
- WHEN a capability claim comes only from vendor documentation or news and
  has not been observed THE SYSTEM SHALL label it `VENDOR_CLAIM` or `UNKNOWN`
  and never `OBSERVED` or `PASS`.
- THE SYSTEM SHALL provide a surface matrix covering CLI normal tools, CLI
  Code Mode, MCTL headless Agent SDK / `-p`, mctl-native
  discover/describe/invoke (CapabilityGateway), Cloudflare Portal Code Mode
  and API Programmatic Tool Calling. It SHALL cover these dimensions:
  deployment/runtime, model/account eligibility, hook semantics, limits,
  billing, audit, security and suitable task types.
- THE SYSTEM SHALL state that Code Mode is not applicable to the in-cluster
  headless DevLoop unless official documentation pinned in the report says
  otherwise.
- THE SYSTEM SHALL include a duplicate/ownership map that names #597 as the
  owner of benchmark reports, records the #63 PARK result (audit M8 FAIL) as
  a different executor, not reopened here, and cross-links #242/#517,
  #181/#151, #35/#165 and #343.
- THE SYSTEM SHALL include a threat model covering at least: JS side effects,
  runtime-derived arguments, `cd ... &&` shell composition, allowlist vs
  per-invocation permission, the auto-mode code-level classifier, fail-closed
  hooks, cross-tenant principal propagation, nested/parallel child calls,
  cancellation/timeouts, retry/idempotency, egress, secret exposure,
  attacker-supplied tool output, and script-to-action audit reproducibility.
- THE SYSTEM SHALL define, for every child tool call of a script, the
  required per-child actor/tenant, exact argument digest, action-time policy
  decision and durable audit record. It SHALL map each to the existing MCTL
  mechanism (`execution_identity.Actor`/`Scope`,
  `policy_checkpoint.args_digest_of`, `decision_records`) or mark it as a gap.
- IF any per-child requirement cannot be shown to hold THEN THE SYSTEM SHALL
  treat the call as denied/unknown (fail closed) in the design, and the
  recommendation SHALL NOT be better than `FURTHER_RESEARCH` for that
  surface.
- THE SYSTEM SHALL provide a machine-readable benchmark protocol for three
  synthetic/read-only tasks: (A) repository research across many files,
  (B) GitHub CI evidence collection from fixtures, (C) aggregation of 2+
  MCP sources from sanitized fixtures. Each task SHALL have an independent
  success oracle, defined failure cases, >=5 reps per mode, and identical
  pinned CLI version/model/prompt/profile/identity/fixtures across modes.
- THE SYSTEM SHALL require the protocol to record initial and total
  input/output tokens, turns, tool invocations, p50/p95 latency, JS
  startup/overhead, cost, correctness, permission denials and per-child
  correlation. It SHALL reuse the counting rules of `tools/capability_bench.py`.
- WHILE no separate explicit owner GO for execution exists THE SYSTEM SHALL
  mark every result cell and every negative-test cell `NOT_RUN`.
- THE SYSTEM SHALL record a recommendation that names its gate, owner,
  expected cost, required evidence and permission review.
- THE SYSTEM SHALL NOT change runtime code, hooks, profiles, settings,
  dependencies, gitops, organization/developer settings or Cloudflare
  configuration.

## Out of scope

- Running any Code Mode or normal-CLI experiment, or enabling Code Mode in any
  developer, organization or CI environment (needs a separate owner GO).
- Any change to `orchestrator/`, `agents/`, `pyproject.toml`/`uv.lock`, the
  Dockerfile, execution profiles or mctl-gitops.
- Reopening the Cloudflare Portal Code Mode A/B (#63), changing the portal,
  or any paid Cloudflare change.
- Building a JS sandbox, a second policy engine or a new gateway.
- Producing #597's benchmark reports. This spike only defines a protocol that
  feeds them.
- Live user data, production GitHub mutations, MCP writes or Telegram messages
  as fixtures.
- Recording a final `decision.verdict` in the SpikeDefinition manifest. The
  owner does that by hand (`orchestrator/spike_issue.py`).

## Open questions

- Interactive operator workflows are not in this repository: no `.claude/`
  directory, settings or hooks exist in the clone at `2227b47`. Their
  inventory is UNKNOWN until an owner gives a path or a sanitized settings
  export. The design proceeds with the in-repo headless inventory and marks
  the interactive column UNKNOWN.
- The Code Mode documentation was not fetched by this investigator run. All
  Code Mode behaviour cited here comes from the issue body (checked by the
  issue author 2026-11-18). Task 1 must re-fetch and pin it.
- Can a `PreToolUse` hook see that a call is a Code Mode child, and its
  parent script id? This is UNKNOWN. Without it, per-child correlation to a
  script cannot be proven, so the design treats it as a hard blocker for
  anything beyond `FURTHER_RESEARCH`.
- Code Mode's interaction with OpenTelemetry export and `DISABLE_TELEMETRY` is
  UNKNOWN; it must be verified against the pinned CLI.
- Who owns the eventual execution GO: the #1096 issue author or the #597
  owner? The design assumes the #597 owner co-signs the protocol.
- Account/model eligibility for the operator accounts is not observed (same
  gap as spike #917's "Plan tier: not observed").
