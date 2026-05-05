# anthropic-sdk-timeout-default: Upgrade anthropic-sdk-go and enforce diagnose-phase timeout

## Context

`mctl-agent` calls the Anthropic API (Claude) during the `LLMDiagnosis` skill — the fallback skill invoked for all alerts that no other builtin or YAML skill can handle. The current integration uses `anthropic-sdk-go` (vendored or direct HTTP calls). No explicit HTTP timeout has been documented or confirmed in the current diagnose-phase code path.

`anthropic-sdk-go` v1.39.0 (released 2026-05-04) adds a **default 10-minute HTTP client timeout** to all requests. Without a hard timeout, a slow or unresponsive Anthropic API call can block the `LLMDiagnosis` goroutine indefinitely: the ticket stays open, the skill pipeline stalls for that alert, and subsequent alerts targeting the same skill queue up behind it. This is a reliability risk that directly affects the self-healing SLO of `mctl-agent`.

Upgrading to v1.39.0 and explicitly configuring a 5-minute diagnose timeout closes this gap with minimal effort and no public API breakage.

## User stories

- AS the `mctl-agent` service I WANT every Anthropic API call to have a hard deadline SO THAT a slow Claude response does not block the ticket pipeline indefinitely.
- AS a platform engineer I WANT `LLMDiagnosis` to fail fast after a configurable timeout SO THAT the circuit breaker can count the failure and eventually disable the skill until the API recovers.
- AS a developer I WANT the Anthropic SDK version to be current SO THAT I have access to Managed Agents API improvements and the latest authentication options.

## Acceptance criteria (EARS)

- WHEN `LLMDiagnosis` issues an Anthropic API call and the API does not respond within 5 minutes THEN THE SYSTEM SHALL cancel the request and return a timeout error to the skill pipeline.
- WHEN the timeout error is returned THE SYSTEM SHALL increment the skill's failure counter (feeding the existing circuit breaker).
- WHILE a diagnose-phase Anthropic API call is in-flight THE SYSTEM SHALL NOT block other alert tickets from being dispatched to non-LLM skills.
- WHEN `go.mod` is updated to `anthropic-sdk-go` v1.39.0 THE SYSTEM SHALL compile without errors and all existing unit tests SHALL pass.
- IF the `ANTHROPIC_TIMEOUT` environment variable is set THE SYSTEM SHALL use its value (in seconds) as the HTTP client timeout, overriding the default 5-minute value.

## Out of scope

- Switching from the Anthropic SDK to direct HTTP calls (or vice versa).
- Implementing retry logic for Anthropic API failures (the circuit breaker already handles repeated failures).
- Enabling Workload Identity Federation or Interactive OAuth (new SDK auth modes are noted for future use only).
- Removing the `LLMDiagnosis` skill (explicitly prohibited per `context/architecture.md`).
