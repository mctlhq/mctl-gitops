# Upgrade anthropic-sdk-go to v1.43.0 (cache diagnostics and structured-output fix)

## Context

mctl-agent uses the Anthropic Go SDK for the LLMDiagnosis builtin skill — the fallback
diagnose path that calls Claude when no deterministic Go skill matches an alert. The
existing `anthropic-sdk-v141-upgrade` proposal targets v1.41.0; as of 2026-05-13 the
latest release is v1.43.0, which introduces two improvements directly relevant to the
service:

1. **Cache diagnostics beta** — new response fields expose prompt-cache hit/miss counts
   per request. mctl-agent has no visibility into whether its system-prompt is being
   cached efficiently; cache misses directly inflate Anthropic API cost and diagnose
   latency. Wiring these fields into the existing skill-metrics SQLite table gives the
   platform the first signal of prompt-cache efficiency.

2. **Structured-output schema transformation bug fix** — v1.41.0–v1.42.x contained a bug
   where certain JSON schemas passed to tool definitions were silently transformed
   incorrectly, potentially causing malformed tool-call payloads. LLMDiagnosis constructs
   tool schemas for evidence-gathering; a silent transformation bug could produce wrong
   diagnose results without any error surfacing.

The JSON encoder optimization (also in v1.43.0) is a free throughput gain requiring no
code changes.

## User stories

- AS a platform operator I WANT cache diagnostics reported per LLMDiagnosis call SO THAT
  I can observe prompt-cache efficiency and adjust the system prompt to maximise cache hits.
- AS a developer I WANT the structured-output schema transformation bug fixed SO THAT
  LLMDiagnosis tool schemas are sent to the Anthropic API exactly as constructed in code.
- AS a platform engineer I WANT the Anthropic SDK JSON encoder optimized SO THAT diagnose
  request serialization contributes less CPU overhead.

## Acceptance criteria (EARS)

- WHEN LLMDiagnosis completes a diagnose call, THE SYSTEM SHALL record the cache
  input-tokens and cache read-tokens from the response's usage field into the
  skill-metrics SQLite table (or a dedicated cache-diagnostics row).
- WHEN LLMDiagnosis constructs a tool schema with nested objects or arrays, THE SYSTEM
  SHALL transmit the schema to the Anthropic API without silent transformation (regression
  test against the v1.41.x bug).
- WHEN the SDK is upgraded, THE SYSTEM SHALL compile and pass all existing tests without
  modification to LLMDiagnosis business logic.
- IF cache diagnostics beta fields are absent from an API response (e.g. feature not
  enabled on the account), THE SYSTEM SHALL handle missing fields gracefully without
  panicking or logging errors.

## Out of scope

- Changes to LLMDiagnosis matching logic or confidence scoring.
- Enabling managed-agents or multi-agent features (v1.41.0 addition — not relevant to the
  current single-agent diagnose model).
- Webhook handling features added in v1.41.0 (separate concern).
- Go toolchain or other dependency upgrades.
