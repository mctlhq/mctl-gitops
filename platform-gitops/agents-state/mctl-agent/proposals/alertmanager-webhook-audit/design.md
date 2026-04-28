# Design: alertmanager-webhook-audit

## Current state

`POST /api/v1/alerts` is handled by a chi/v5 route registered at startup. The handler reads the
request body and decodes it into a fixed Go struct that mirrors the AlertManager webhook schema
as of v0.31.x or earlier (exact location: `internal/webhook/` or equivalent package). The struct
covers the standard fields: `version`, `groupKey`, `status`, `receiver`, `groupLabels`,
`commonLabels`, `commonAnnotations`, `externalURL`, and the `alerts` slice (each with `status`,
`labels`, `annotations`, `startsAt`, `endsAt`, `generatorURL`).

AlertManager v0.32.0 adds at minimum:

- `silenceAnnotations` — per-alert map of annotation key/value pairs set by matching silences.
- `matcherSets` — list of matcher groups for multi-matcher silences.

Because the struct does not declare these fields, their behavior on decode depends on how
`json.Decoder` is configured. If `DisallowUnknownFields` is active (even transiently), the
decode returns an error and the handler likely returns a non-2xx status, causing AlertManager to
retry and eventually give up. If unknown fields are silently ignored (the Go default), the data
is lost with no log trace — making silent drops invisible.

Neither outcome is acceptable for a service where this endpoint is the single entry point for all
self-healing.

## Proposed solution

The fix has four parts, all contained within `internal/webhook/` (and the Prometheus metrics
registration):

### Part 1: Struct audit and extension

Compare the current Go webhook struct against the AlertManager v0.32.0 webhook payload
documentation and source (`prometheus/alertmanager`, tag `v0.32.0`, `template/template.go` and
`api/v2/models/`). Add any new fields as optional pointer or slice fields with `json:",omitempty"`
tags. Minimum additions:

```go
// On the top-level webhook payload struct:
SilenceAnnotations map[string]string `json:"silenceAnnotations,omitempty"`

// On the inner Alert struct:
SilenceAnnotations map[string]string `json:"silenceAnnotations,omitempty"`
MatcherSets        [][]Matcher       `json:"matcherSets,omitempty"`
```

Existing fields and their tags are left unchanged, preserving v0.31.x compatibility.

### Part 2: Unknown-field logging in production, strict mode in tests

In production the decoder uses the default permissive mode. Unknown field detection is layered on
top using a two-pass approach:

1. Decode into `json.RawMessage` first.
2. Unmarshal into a `map[string]json.RawMessage`.
3. Compare top-level keys against the known field set; log any extras at `slog.Warn`.
4. Unmarshal from the raw bytes into the typed struct.

This adds minimal overhead (two JSON passes on a small webhook body) and gives full observability
without blocking processing.

In test mode (`build tag: test` or via a handler option) `DisallowUnknownFields` is set so tests
catch schema drift early.

### Part 3: Silence annotation persistence

When `SilenceAnnotations` is non-empty on a decoded alert, the ticket evidence map is extended
with a `silence_annotations` key whose value is the serialized annotation map. No schema
migration is required — the evidence column in SQLite is already a free-form JSON blob.

### Part 4: Parse-error metric

Register a Prometheus counter `alertmanager_payload_parse_errors_total` (label: `reason`) during
handler init. Increment it before returning HTTP 400 on any parse failure. Expose it at the
existing `/metrics` endpoint (assuming a standard Prometheus HTTP handler is already mounted;
if not, that wiring is included in Task 4).

## Alternatives

### (a) Full JSON Schema validation

Validate the incoming payload against a JSON Schema document derived from the AlertManager
OpenAPI spec. This provides maximum strictness but introduces a schema-validation library
dependency, requires the schema file to be kept in sync with AlertManager releases, and is
significantly more complex than a struct audit for a single internal endpoint. Rejected as
overkill.

### (b) Ignore and wait for a production failure

Given that `POST /api/v1/alerts` is the sole self-healing entry point, a silent parse failure
would suppress all self-healing for all routed alert types with no visible error. The risk
exposure window between the AlertManager upgrade and discovery could be hours to days. Rejected.

### (c) Automate AlertManager schema tracking via Renovate

A valid long-term improvement: Renovate could open a PR whenever `prometheus/alertmanager`
releases a new version, triggering a schema review. This does not address the immediate v0.32.0
drift and is a separate infrastructure concern. Noted as a follow-up but out of scope here.

## Platform impact

- **Migrations:** None. The `silenceAnnotations` data is stored in an existing free-form JSON
  evidence column; no DDL changes are needed.
- **Backward compatibility:** v0.31.x payloads do not include the new fields; the `omitempty`
  pointer fields default to nil and the code paths for silence annotation storage are not
  triggered. Routing and diagnosis are unchanged.
- **Resource impact:** The two-pass JSON decode adds negligible CPU overhead (webhook bodies are
  typically under 4 KB). Memory allocation per request increases by at most a few hundred bytes
  for the intermediate `map[string]json.RawMessage`. This proposal has zero impact on the `labs`
  tenant memory limit.
- **Risks and mitigations:**
  - Risk: the two-pass decode introduces a regression for malformed but previously-tolerated
    payloads. Mitigation: table-driven tests cover malformed, partial, v0.31.x, and v0.32.0
    payloads (Task 3).
  - Risk: the Prometheus counter registration conflicts with an existing metric name. Mitigation:
    grep the codebase for `alertmanager_payload` before registering; rename if needed.
- **Rollback:** Revert the struct changes and the two-pass decoder logic. AlertManager v0.31.x
  and v0.32.x share all common fields; the wire format for the fields that existed before v0.32.0
  is unchanged, so reverting the Go struct has no impact on parsing those shared fields.
