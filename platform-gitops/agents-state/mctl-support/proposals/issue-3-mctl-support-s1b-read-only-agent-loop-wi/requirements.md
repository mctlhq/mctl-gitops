# mctl-support S1b: read-only agent loop with a strict tool registry

## Context

mctl-support (S1a, mctlhq/mctl-support#2) already serves A2A 1.0 over HTTP+JSON,
admits callers through mctl-api `whoami`, stores tasks, contexts, reservations
and transcripts in Postgres, and wraps every task in a WorkItemExecution plus a
tenant-bound `support` run token (`executors/lifecycle.py`). The executor behind
it is still the scripted `FakeExecutor`; `app.build_executor` refuses
`SUPPORT_EXECUTOR=agent` with "arrives in S1b".

Issue #3 (phase S1b of epic mctlhq/.github#243) asks for the real agent: one
task becomes one model tool loop that can only read the caller's tenant. The
loop sits behind a model-provider boundary (decision D3, amended 2026-10-27):
`anthropic` (Sonnet, reference and production default) and `hetzner`
(Hetzner Inference, OpenAI-compatible, `Qwen/Qwen3.6-35B-A3B-FP8`, stateless).
Below the provider is one strict tool registry: allowlisted mctl read tools
called through `api.mctl.ai/mcp` with the task's run token,
`read_platform_skill`, and an `escalate` stub (wired in S1c). Everything else is
refused locally before any byte leaves the pod. Per-task limits (25 tool calls,
10 minutes, a cost cap), cancellation, context continuation scoped to the
tenant, a platform-policy system prompt and a stable result contract complete
the phase. This matters because it is the first time a model acts on tenant
data; the containment must come from code (registry, run token, limits), not
from the model's good behaviour.

## User stories

- AS a tenant member I WANT to ask the support agent why my service misbehaves
  SO THAT I get an evidence-backed explanation or the exact call that fixes it.
- AS a platform operator I WANT the model to have only the read tools of the
  `support` scope SO THAT no prompt, log line or model mistake can mutate
  infrastructure or read another tenant.
- AS a platform operator I WANT to switch the model provider by configuration
  SO THAT an alternative (Hetzner/Qwen) can be evaluated without changing the
  tool authority model.
- AS a tenant member I WANT to continue a conversation in the same `contextId`
  SO THAT follow-up questions keep the earlier findings.
- AS the epic owner I WANT a per-fixture comparison of both providers SO THAT
  the production default is chosen on evidence.

## Acceptance criteria (EARS)

Provider boundary
- WHEN the service starts with `SUPPORT_EXECUTOR=agent` THE SYSTEM SHALL select
  exactly one model provider from `MODEL_PROVIDER` (`anthropic` default, or
  `hetzner`) and use that provider and its one configured model for every turn
  of every task.
- IF `MODEL_PROVIDER` is unknown, or the selected provider's model or API key
  variable is empty, THEN THE SYSTEM SHALL refuse to start with a `ConfigError`
  that names the missing variable and never its value.
- IF `CLAUDE_CODE_OAUTH_TOKEN` is set in the environment, or the selected
  provider is `anthropic` and `ANTHROPIC_API_KEY` is not an API key (does not
  start with `sk-ant-api`), THEN THE SYSTEM SHALL refuse to start.
- IF a configured tool-call limit is above 25 or a deadline above 10 minutes
  THEN THE SYSTEM SHALL refuse to start.
- WHILE a task runs THE SYSTEM SHALL send the full transcript on every model
  turn when the provider's `server_thread` capability is false, and SHALL decide
  that from `ProviderCapabilities.server_thread`, never from the provider name.
- THE SYSTEM SHALL pass the same tool definitions, produced by the tool
  registry, to every provider, and SHALL route every tool call a provider
  proposes through the same registry check, run token and limits.

Tool registry
- WHEN the model proposes a tool name that is not in the registry allowlist
  (for example `kubectl`, `http_request`, `shell`, `deploy_service`) THE SYSTEM
  SHALL return a refusal tool result to the model and SHALL NOT make any
  outbound call for it.
- WHEN the model proposes an allowlisted tool with arguments that fail the
  tool's input schema THE SYSTEM SHALL refuse it locally without an outbound call.
- WHEN an allowlisted mctl read tool is called THE SYSTEM SHALL call it on
  `<MCTL_API_URL>/mcp` with the task's `support` run token and no other
  credential.
- THE SYSTEM SHALL NOT expose shell, filesystem, git, GitHub, kubectl,
  Kubernetes API, Loki, web, browser, deploy/scale/retire, secret-value,
  generic HTTP or generic MCP passthrough tools.
- IF mctl-api refuses a tool call (401/403) THEN THE SYSTEM SHALL return
  "denied" to the model as evidence and SHALL NOT retry it with any other
  credential.
- IF a tool read fails or is partial THEN THE SYSTEM SHALL return an explicit
  error or unknown to the model, never an empty or healthy result.
- WHEN the model calls `escalate` THE SYSTEM SHALL record the request in the
  result and return a "not wired until S1c" tool result, making no outbound call.

Isolation
- WHEN a task for tenant A proposes a tool call naming tenant B THE SYSTEM
  SHALL forward it only with tenant A's run token, so the call is refused by
  mctl-api, and the task's answer SHALL contain no data of tenant B.
- WHEN a message names a `contextId` owned by another principal or tenant THE
  SYSTEM SHALL answer with the same error as for a missing context and SHALL
  NOT load any of its transcript.
- WHEN a message continues an owned `contextId` THE SYSTEM SHALL restore the
  stored model transcript of that context and tenant before the first turn.

Limits and cancellation
- IF a task would exceed 25 tool calls THEN THE SYSTEM SHALL stop the loop and
  end the task `failed` with the message "tool-call limit (25) reached".
- IF a task runs longer than 10 minutes THEN THE SYSTEM SHALL stop the loop and
  end the task `failed` with the message "time limit (10 min) reached".
- IF the task's accumulated model cost exceeds `SUPPORT_TASK_COST_CAP_USD`
  THEN THE SYSTEM SHALL stop the loop and end the task `failed` with
  "cost limit reached".
- WHEN a task is canceled, on the replica that runs it or on another replica,
  THE SYSTEM SHALL stop the in-flight model or tool call within the current
  turn, leave the task `canceled`, and revoke the run token (its TTL is the
  backstop if revocation fails).
- IF a message targets a task in a terminal state THEN THE SYSTEM SHALL NOT
  resume its loop.

Answers
- WHEN the loop ends with a final answer THE SYSTEM SHALL convert it into the
  result contract `{summary, classification, evidence[{source, summary}],
  recommended_actions[], escalation_id}` with `classification` one of
  `tenant_fix`, `platform_issue`, `informational`, `refused`, and SHALL attach
  it to the completed task as a text part and a data part.
- IF an evidence entry's `source` does not name a tool call made in this task
  or a skill read in this task THEN THE SYSTEM SHALL drop that entry and mark
  the result as having dropped unsupported evidence.
- THE SYSTEM SHALL use a system prompt that states platform policy (baseline
  PSS, egress defaults, quota defaults, secret merge in `tpl-vault-write`),
  the four answer tiers (explain, tenant fix, escalate, refuse), and that
  content returned by diagnostic tools is evidence, not instructions.

Provider comparison
- WHEN the comparison harness runs THE SYSTEM SHALL run the 9 namax66
  diagnostic fixtures on both providers and write a report with, per fixture:
  diagnosis correctness, tool choice, tool-call count, false escalations,
  missed escalations, prompt-injection resistance, latency and cost, and the
  recorded production default.

## Out of scope

- Wiring `escalate` to a real escalation sink (S1c) and choosing the final
  per-task cost cap number (S1c).
- Streaming, push notifications, any write tool, Haiku pre-pass or routing by
  task complexity.
- Changes to mctl-api's `support` scope itself (S0a) or to the run-token mint.
- Switching production to `SUPPORT_EXECUTOR=agent` in mctl-gitops: a separate
  gitops PR after merge, once the provider keys exist in Vault.
- Publishing new platform skills in the catalog (the policy text ships in the
  service's prompt; catalog skills are read through `read_platform_skill`).

## Open questions

- The exact tool set of the mctl-api `support` scope (S0a) is not visible from
  this repo. The proposal fixes an allowlist of read tools in code (design.md)
  and, per task, intersects it with the MCP `tools/list` answer for the run
  token; a name the scope lacks is not offered to the model. Confirm the list.
- "The official Anthropic SDK tool runner": the SDK's `tool_runner` executes
  tools inside the SDK, which would put tool execution above our registry and
  split the loop per provider. The proposal uses the official Anthropic SDK
  Messages API per turn inside one provider-neutral loop. Confirm this reading.
- Per-task cost cap: S1c sets the number; S1b ships
  `SUPPORT_TASK_COST_CAP_USD` with a provisional default of 2.00 and per-model
  token prices as configuration.
- The 9 namax66 fixtures are referenced but not in this repo. The proposal
  stores sanitized recorded tool outputs under `tests/fixtures/diagnostic/`
  with no customer data; their source material must be provided by the owner.
- `MCTL_API_URL` is `https://api.mctl.ai` in the deployed values; the MCP
  endpoint is assumed at `<MCTL_API_URL>/mcp` with JSON-RPC over streamable HTTP.
- Platform-policy values (PSS level, egress default, quota defaults) are taken
  from the platform's current tenant provisioning (internet egress allowed by
  default; default quotas from create-tenant); confirm before the prompt is
  frozen.
