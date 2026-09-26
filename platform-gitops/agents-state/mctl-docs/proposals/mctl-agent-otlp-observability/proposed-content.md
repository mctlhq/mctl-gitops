# Proposed content: mctl-agent-otlp-observability

> **Source:** mctl-agent@0c9e8f2

This proposal touches three locations. Each block below states its own
**Apply to** target and mode.

---

## Block 1

> **Apply to:** `mctl-docs/docs/platform/components.md` (UPDATE)
> **Source:** mctl-agent@0c9e8f2

**Before** (excerpt, mctl-agent block, current file):

```markdown
- Can dispatch incidents to external agents such as OpenClaw through signed webhooks
- Creates PRs to `mctl-gitops` with fixes and tracks PR metadata
- Notifies operators through Telegram for updates, review, and approvals
- Full incident lifecycle: detect, analyze, propose fix, review, verify
```

**After:**

```markdown
- Can dispatch incidents to external agents such as OpenClaw through signed webhooks
- Creates PRs to `mctl-gitops` with fixes and tracks PR metadata
- Notifies operators through Telegram for updates, review, and approvals
- Full incident lifecycle: detect, analyze, propose fix, review, verify
- Emits OpenTelemetry traces of ticket processing over OTLP when the
  standard `OTEL_*` environment variables are configured — off by default,
  no behavior change without a collector. See
  [Observability](/reference/troubleshooting#observability).
```

---

## Block 2

> **Apply to:** `mctl-docs/docs/reference/troubleshooting.md` (UPDATE)
> **Source:** mctl-agent@0c9e8f2

**Before** (excerpt, end of `## Self-Healing Agent`, before `## Getting Help`):

```markdown
### Agent PR was not merged

Agent PRs require manual review and approval. Check:
- The PR in the `mctl-gitops` repository on GitHub
- Telegram notifications for operator approval requests
- The incident status via MCP: `"Show me details of incident INC-xxx"`

## Getting Help
```

**After:**

```markdown
### Agent PR was not merged

Agent PRs require manual review and approval. Check:
- The PR in the `mctl-gitops` repository on GitHub
- Telegram notifications for operator approval requests
- The incident status via MCP: `"Show me details of incident INC-xxx"`

## Observability

### Enabling OTLP tracing for mctl-agent

mctl-agent emits one root span per ticket (`mctl_agent.process_ticket`),
with child spans for evidence collection, skill matching, diagnosis, and
the fix, plus a client span per model call. Tracing is configured only
through the standard OpenTelemetry environment variables:

| Variable | Effect |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Set either to enable export to that OTLP gRPC endpoint |
| `OTEL_SDK_DISABLED=true` | Force tracing off even if an endpoint is set |
| `OTEL_TRACES_EXPORTER=none` | Same effect as `OTEL_SDK_DISABLED=true` |
| `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` | Standard resource-attribute overrides, applied after mctl-agent's own defaults |

With no endpoint configured, nothing is installed and the agent runs
exactly as before — this is opt-in, not a breaking change. Spans carry
ids, the model, and token counts; they never carry the prompt, the
completion, or a provider response body. See
[Telemetry Attribute Catalog](/reference/telemetry-attributes) for the
full list of attribute names mctl-agent emits.

### LLM cost/usage metrics

Two Prometheus counters exist independently of tracing (scraped from
mctl-agent's `/metrics` endpoint):

| Metric | Labels | Meaning |
|---|---|---|
| `mctl_agent_llm_tokens_total` | `model`, `skill`, `ticket_type`, `direction` | Tokens reported by the model provider, by direction (`input`/`output`). Uses the provider's own counts, never an estimate. |
| `mctl_agent_llm_requests_total` | `model`, `skill`, `outcome` | Model calls, by outcome (`ok`/`error`). |

**Use these counters for cost/usage dashboards today, not trace
attributes.** The platform OpenTelemetry Collector's redaction pattern
currently matches any key containing `token`, so `gen_ai.usage.input_tokens`
and `gen_ai.usage.output_tokens` arrive on spans masked as the literal
string `****` — a present attribute with a value of the wrong type, not a
missing one. This is a tracked Collector configuration defect
(`mctlhq/mctl-gitops#1332`), not a mctl-agent bug; the Prometheus counters
are unaffected by it.

## Getting Help
```

---

## Block 3

> **Apply to:** `mctl-docs/docs/reference/telemetry-attributes.md` (UPDATE)
> **Source:** mctl-agent@0c9e8f2

### Diff A — opening paragraph

**Before:**

```markdown
One caveat that `shipped` does not cover: no MCTL service has a tracer,
exporter or propagator installed yet — that is the epic's own remaining
work. The shipped attributes are written onto a span only when one already
exists in the context, so today they are code that would emit rather than
data in a backend. `shipped` means the name is settled and renaming it
costs a migration; it does not mean anything is queryable yet.
```

**After:**

```markdown
One caveat that `shipped` does not cover: most MCTL services still have no
tracer, exporter or propagator installed — that is the epic's own
remaining work. `mctl-agent` is the first exception (`internal/telemetry/telemetry.go`,
mctlhq/mctl-agent#38): it installs a tracer when `OTEL_EXPORTER_OTLP_ENDPOINT`
(or `_TRACES_ENDPOINT`) is configured, and stays a no-op otherwise. For
every other service, the shipped attributes are still written onto a span
only when one already exists in the context — code that would emit rather
than data in a backend. `shipped` means the name is settled and renaming it
costs a migration; it does not mean every producer's attributes are
queryable in a backend yet (see the redaction warning below for
`gen_ai.usage.*` specifically).
```

### Diff B — "Span attributes — incident agent" table

**Before:**

```markdown
| Attribute | Type | Status | Meaning |
|---|---|---|---|
| `mctl.ticket.id` | string | reserved | The mctl-agent ticket being processed. One per incident, so a join key. |
| `mctl.ticket.type` | string | reserved | The ticket's classification, e.g. `pod_crashloop`, `resource_limit`, `argocd_app_degraded`. Bounded by the agent's classifier (`internal/ticket`). |
| `mctl.skill.name` | string | reserved | The skill a span ran or evaluated, e.g. `oomkilled`, `llm_diagnosis`. Bounded by the skill registry (`internal/skill/builtin`). |
| `mctl.diagnosis.confidence` | string | reserved | `HIGH`, `MEDIUM` or `LOW`, as the skill reported it. |
| `mctl.diagnosis.fixable` | boolean | reserved | The skill asserted that a fix can be proposed. |
| `mctl.ticket.outcome` | string | reserved | How processing ended: `pr_created`, `fix_proposed`, `escalated`, `failed`. Bounded. |
```

**After:**

```markdown
| Attribute | Type | Status | Meaning |
|---|---|---|---|
| `mctl.ticket.id` | string | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | The mctl-agent ticket being processed. One per incident, so a join key. |
| `mctl.ticket.type` | string | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | The ticket's classification, e.g. `pod_crashloop`, `resource_limit`, `argocd_app_degraded`. Bounded by the agent's classifier (`internal/ticket`). |
| `mctl.skill.name` | string | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | The skill a span ran or evaluated, e.g. `oomkilled`, `llm_diagnosis`. Bounded by the skill registry (`internal/skill/builtin`). |
| `mctl.diagnosis.confidence` | string | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | `HIGH`, `MEDIUM` or `LOW`, as the skill reported it. |
| `mctl.diagnosis.fixable` | boolean | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | The skill asserted that a fix can be proposed. |
| `mctl.ticket.outcome` | string | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | How processing ended: `pr_created`, `fix_proposed`, `escalated`, `failed`. Bounded. |
```

Note: `mctl.repository.name` and `mctl.pr.number` (defined earlier, in the
"correlation identity" table) are also now emitted by this producer for the
fix pull request (`internal/fixer/github.go`); leave their existing rows'
`reserved` status as-is unless another producer is confirmed —
`<TODO: confirm with author of 0c9e8f2 whether mctl-agent is the first
producer of these two specific attributes, or whether another service
already ships them, before changing their status>`.

### Diff C — `gen_ai.*` table

**Before:**

```markdown
| Attribute | Type | Status | Meaning |
|---|---|---|---|
| `gen_ai.operation.name` | string | reserved | Upstream convention, e.g. `chat`, `invoke_agent`. Bounded. |
| `gen_ai.provider.name` | string | reserved | Upstream convention. Bounded. |
| `gen_ai.request.model` | string | reserved | The concrete model. Bounded, and the dimension cost is grouped by. |
| `gen_ai.usage.input_tokens` | int | reserved | Token count in. Currently masked — see the warning below. |
| `gen_ai.usage.output_tokens` | int | reserved | Token count out. Currently masked — see the warning below. |
```

**After:**

```markdown
| Attribute | Type | Status | Meaning |
|---|---|---|---|
| `gen_ai.operation.name` | string | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | Upstream convention, e.g. `chat`, `invoke_agent`. Bounded. |
| `gen_ai.provider.name` | string | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | Upstream convention. Bounded. |
| `gen_ai.request.model` | string | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | The concrete model. Bounded, and the dimension cost is grouped by. |
| `gen_ai.usage.input_tokens` | int | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | Token count in. Currently masked — see the warning below. |
| `gen_ai.usage.output_tokens` | int | shipped (`mctl-agent`, `internal/telemetry/telemetry.go`) | Token count out. Currently masked — see the warning below. |
```

Also update the sentence immediately below the table from "All five are
`reserved`: no MCTL service emits `gen_ai.*` today." to "All five are now
`shipped` by `mctl-agent` (`internal/telemetry/telemetry.go`); no other
service emits `gen_ai.*` yet."

---
