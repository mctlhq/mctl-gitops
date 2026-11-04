# Design: issue-293-spike-telegram-openai-compatible-functio

## Current state
- Spikes in this repository have two parts. One is a `SpikeDefinition` manifest under `roadmap/spikes/`, validated against `roadmap/schemas/spike-definition.schema.json` and by `spike_semantic_errors` in `roadmap/scripts/validate.py`: a verdict must be one of `outcomes`, dates must be calendar dates, and follow-ups must be unique and not the spike's own issue. The other is a report under `docs/spikes/`. The schema forbids `decision` unless `lifecycle: decided`, and requires `timebox` when `lifecycle: active`.
- The convention, seen in the comments of `roadmap/spikes/edge-config-kv-instant.yaml` and `agent-client-compatibility.yaml`, is that the agent writes a proposed verdict in the report only. The owner records the `decision` block. Decided examples are `hetzner-inference-benchmark.yaml` and `mctl-support-runtime.yaml`, both decided by `mashkovd` and both with `followUps`.
- Report style: `docs/spikes/edge-config-kv-instant.md` uses evidence pins (40-hex), evidence tags `[CODE]`/`[DEPLOYED]`/`[DOC]`, and "unknown (not observed)" for anything unmeasured. That is never read as absent or zero. It quotes no secrets.
- Related prior evidence: `docs/spikes/mctl-support-runtime.md` has an addendum that runs a tool loop on Hetzner's Anthropic-compatible endpoint (Qwen3.6-35B-A3B-FP8). It found a Hetzner 400 "No user query found in messages" under one Python runner default. That is the Anthropic surface, not OpenAI `/v1/chat/completions`, and is relevant only as a hint about message-shape quirks. `roadmap/spikes/hetzner-inference-benchmark.yaml` (decided `ADOPT_EXPERIMENTAL_PROVIDER`) covers mctl-agents workloads, not the Telegram tool loop.
- `AGENTS.md` lists every spike report under `# Spikes`.
- No file in the clone mentions `telegram-openai-tool-loop`, `OpenAIRunner`, `custom-hetzner` or `custom-nebius`, so this is new content.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-support/values.yaml`: `MODEL_PROVIDER: nebius`, `NEBIUS_MODEL: zai-org/GLM-5.1`, `NEBIUS_BASE_URL` set to the Cloudflare AI Gateway `.../mctl-support/custom-nebius/v1`, and prices `MODEL_INPUT_USD_PER_MTOK: "1.40"` / `MODEL_OUTPUT_USD_PER_MTOK: "4.40"`. These match the issue's price table. The ExternalSecret maps `nebius-api-key` and `hetzner-api-key` from `secret/data/platform/mctl-support/model` and the gateway bearer from `secret/data/platform/mctl-support/ai-gateway`. The comments name Hetzner via `<gateway>/custom-hetzner/v1` as a non-production fallback and say the gateway keeps no logs (mctl-gitops#2262 Phase B). So the custom providers, keys and run token the spike needs already exist. Note that they are scoped to mctl-support's gateway (`mctl-support` gateway id), not to an mctl-telegram gateway.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image tag `0.121.1`, `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`, `AGENT_TURN_QUIET: "3s"`, `AGENT_TURN_MAX_WAIT: "15s"`, `AGENT_UNCLAIMED_ROUTE_AFTER: "5m"`. The worker runs off-cluster on the owner's always-on host. No `AGENT_OPENAI_*` or model keys are present, so the managed runtime is not deployed.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: image tag `main-80583cb`, `AGENT_ENABLED`/`AGENT_KILL_SWITCH` as in production, and no OpenAI or model keys.
- `mctl_get_service_status(labs, mctl-telegram-preview)`: Healthy, Synced, image `main-80583cb`, host `tg-preview.mctl.ai`, has a database.
- Not observed: the mctl-telegram source (`buildToolSet`, mcp-go version, C1 harness, ADR 0008, the `audit_logs` schema), the gateway's live logging and cache settings, and the Vault contents. These are recorded under Open questions in requirements.md.

## Proposed solution
The work is a docs-and-manifest change in `mctlhq/.github`, backed by measurements taken in mctl-telegram. No runtime code is merged.

1. **Manifest** `roadmap/spikes/telegram-openai-tool-loop.yaml`:
   - `metadata.name: telegram-openai-tool-loop`, `owner: mctlhq/mctl-telegram`. The owner can be changed to `mctlhq/.github` to match carrier spikes.
   - `spec.title`, `spec.question` (the issue's question verbatim, condensed), `lifecycle: proposed`, `github.issue: {repository: mctlhq/.github, number: 293}`.
   - The four outcomes, `timebox.decisionBy: "2026-11-10"`, `execution.devloop: true`, `evidence.report: docs/spikes/telegram-openai-tool-loop.md`.
   - No `decision` block. A header comment states that the owner records the verdict, following `edge-config-kv-instant.yaml`.
2. **Report** `docs/spikes/telegram-openai-tool-loop.md`, with these sections:
   - Header: proposed verdict, a non-claims statement, evidence tags and pins (mctl-telegram commit, mctl-gitops commit, mcp-go version).
   - Smoke test S1, schema pass-through: one row per tool (11 rows) with columns tool, JSON Schema keywords used, valid OpenAI `parameters` (y/n), per-provider accept/reject, and notes. The test marshals `mcplib.Tool.InputSchema` and checks it is an object schema with `type: object` and `properties`. It flags keywords known to be fragile on OpenAI-compatible servers: `$ref`/`$defs`, `oneOf`/`anyOf`, `additionalProperties`, missing `required`, `format`, and `null` types.
   - Smoke test S2, tool calling: 5 fixtures x 3 models, with columns fixture id, called `get_context`, proposed, `complete_agent_job`, hallucinated names, argument parse errors, and turns.
   - Smoke test S3, gateway headers: per provider, the gateway log total before and after, and the cache-hit count. This uses gateway analytics counts only, no bodies.
   - Smoke test S4, `audit_logs.user_id`: the FK definition, whether NULL is allowed, and the recommendation.
   - Full run: per model, HarnessVersion, suite digest, classification (n/32), leaks, binding violations, wrong auto-sends, p50/p95 latency, cost per fixture (from `usage`), and 429 count. A cell that was not run says "not run", never 0.
   - Cost ledger: Nebius cumulative spend against the USD 5 cap.
   - Decision rule, verdict per model (one line each), proposed outcome, follow-ups per outcome, and re-open triggers.
3. **Decision rule** (deterministic, stated in the report). A model passes when its full C1 run has score >= 29/32 and leaks = binding violations = wrong auto-sends = 0 with unmodified schemas.
   - Both a Hetzner model and Nebius pass: `GO_HETZNER_DEV_NEBIUS_PROD`.
   - Only Nebius passes, or Hetzner passes but its latency exceeds the proposed threshold: `GO_NEBIUS_ONLY`.
   - The gate is missed only because schema rejection or argument-shape errors trace to S1-flagged keywords: `NEEDS_SCHEMA_ADAPTER`.
   - Otherwise: `NOT_A_FIT`.
   - Without a full run, the report proposes a provisional outcome from S1 and S2 and says that it is provisional.
4. **Execution guardrails**:
   - Keys come from Vault `secret/platform/mctl-support/model` and the gateway run token from Vault. Keys are never stored in files.
   - Headers on every request: `cf-aig-collect-log: false` and `cf-aig-skip-cache: true`.
   - Hetzner runs with `AGENT_OPENAI_MIN_INTERVAL=6s` (10 req/60s per key).
   - Nebius spend is tracked from `usage` after each fixture, with a hard stop at USD 5.
   - Artefacts hold counts, ids, timings and token numbers only.
5. **Index**: add an entry under `# Spikes` in `AGENTS.md`.

## Alternatives
- **Write the decision block directly with the measured verdict.** Dropped because the repository convention (`edge-config-kv-instant.yaml` comment: "an agent does not record its own approval") reserves the decision for the owner, and the schema needs `lifecycle: decided` for it.
- **Run the full C1 suite via an ad-hoc script now, not the slice-3 runner.** Dropped as the primary path. The issue requires the runner interface so that the measured loop is the one that ships. An ad-hoc loop would measure a different system. It is acceptable only for the smoke test.
- **Adapt schemas pre-emptively in `buildToolSet`.** Dropped because it presupposes the `NEEDS_SCHEMA_ADAPTER` outcome and violates "the spike does not merge runtime code". It is the follow-up for that outcome.
- **Use the Anthropic-compatible Hetzner surface** (as in the `mctl-support-runtime.md` addendum). Dropped because the ADR's managed runner targets `/v1/chat/completions`, and Nebius GLM-5.1 is reached through the OpenAI-compatible custom provider.

## Platform impact
- No migrations, no gitops changes and no runtime changes. The repository gains one manifest, one report and one `AGENTS.md` line.
- Cost: at most USD 5 on Nebius. Hetzner is free but rate-limited, so the full suite takes about 32 fixtures x several turns x 6 s per model, roughly tens of minutes.
- Risk: Hetzner runs share keys with mctl-support's non-production fallback, and 429s could affect that path. Mitigation: the 6 s interval, and no runs while mctl-support is on Hetzner (it is on Nebius per values).
- Risk: Nebius runs share the key and gateway with production mctl-support (`MODEL_PROVIDER: nebius`). Mitigation: low concurrency (1), the USD 5 cap, and a check of the mctl-support ledger before and after.
- Risk: content leak through gateway logs. Mitigation: verify S3 before any C1 fixture runs. If logging is not honoured, stop and report.
- Risk: slice 3 is not ready by 2026-11-10. Mitigation: a provisional verdict from the smoke tests, with the gap stated in the report.
- Backward compatibility: the new manifest must keep the issue binding #293 unique among spikes and must not be an epic root. `validate.py` checks both.
