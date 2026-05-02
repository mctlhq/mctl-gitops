# Design: alertmanager-webhook-v032

## Current state
The `POST /api/v1/alerts` handler (see `context/architecture.md` — API endpoints) deserialises the AlertManager webhook body into an internal Go struct. The struct was defined against the pre-v0.32 AlertManager webhook format:

```
{
  "version": "4",
  "groupKey": "...",
  "status": "firing|resolved",
  "receiver": "...",
  "groupLabels": {...},
  "commonLabels": {...},
  "commonAnnotations": {...},
  "externalURL": "...",
  "alerts": [
    {
      "status": "firing|resolved",
      "labels": {...},
      "annotations": {...},
      "startsAt": "...",
      "endsAt": "...",
      "generatorURL": "...",
      "fingerprint": "..."
    }
  ]
}
```

AlertManager v0.32.0 changes:
1. **Webhook payload templating**: the `groupLabels`, `commonLabels`, `commonAnnotations`, and per-alert `annotations` values can now contain template-expanded strings (rather than raw label values). The JSON keys are unchanged, but values may contain rendered template output. This is backward-compatible at the JSON level.
2. **Multiple matcher set silences**: the silence object's `matchers` field changes from `[]Matcher` to `[][]Matcher` (array of arrays) to express OR-logic between matcher sets. If the handler currently unmarshals silence data, it will fail on the new format.

## Proposed solution

**Change 1 — Audit and version-annotate the webhook struct**

Review the existing `AlertManagerWebhook` (or equivalent) Go struct. Add a comment citing the AlertManager version it was validated against. Example:

```go
// AlertManagerPayload represents the AlertManager webhook payload.
// Validated against AlertManager v0.32.x schema (2026-05-02).
// See: https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
type AlertManagerPayload struct { ... }
```

**Change 2 — Harden JSON deserialisation with unknown-field logging**

Replace `json.Unmarshal` (which silently drops unknown fields) with a two-pass approach:
1. First unmarshal into the typed struct.
2. Then unmarshal into `map[string]json.RawMessage` and compare keys against the known set.
3. Log a WARNING via `slog` for any key not in the known set.

This is low-cost insurance against future schema drift.

**Change 3 — Fix silence matcher struct (if used)**

If the service parses silence objects (e.g. to suppress duplicate tickets), update the `Matcher` field from:
```go
Matchers []Matcher `json:"matchers"`
```
to:
```go
Matchers [][]Matcher `json:"matchers"` // v0.32.x: multiple matcher sets (OR logic)
```

Add a migration shim that flattens `[][]Matcher` to `[]Matcher` for services that only need a flat view.

**Change 4 — Startup log of schema version**

In the handler initialisation, emit:
```go
slog.Info("alertmanager webhook handler ready", "alertmanager_schema_version", "v0.32")
```

**Change 5 — Table-driven integration tests**

Add test fixtures for:
- A v0.31.x payload (regression baseline).
- A v0.32.x payload with a template-expanded annotation value.
- A v0.32.x payload with a multiple-matcher-set silence.
- A payload with an unknown top-level field (expects WARNING log, not 400).

## Alternatives

**A — Ignore the schema change until the platform actually upgrades AlertManager**
Defers risk. Rejected: the platform is already running v0.32.1 (2026-04-29); the upgrade may already have happened or is imminent. Discovering the breakage in production is worse than fixing it proactively.

**B — Use `json.Decoder` with `DisallowUnknownFields`**
Would return HTTP 400 on any unrecognised field. Rejected: AlertManager may add optional fields in patch releases; strict rejection would cause outages for minor upgrades. Warning-and-continue is the correct posture.

**C — Adopt a schema-generated struct from the AlertManager OpenAPI spec**
Would give strong typing guarantees but introduces a code-generation step and a new build-time dependency. Over-engineered for a struct with ~15 fields. Rejected.

## Platform impact

**Migrations:** None. The change is entirely within the handler; no database schema, API contract, or external integration changes.

**Backward compatibility:** Full. The new struct correctly parses both v0.31.x and v0.32.x payloads.

**Resource impact:** Negligible — the two-pass JSON approach adds one extra `json.Unmarshal` call per request. At expected alert volumes (< 100 req/min), this is immeasurable. No impact on `labs` tenant.

**Risks and mitigations:**
- *Risk:* The silence matcher change is in a code path not covered by existing tests, causing a runtime panic.  
  *Mitigation:* The integration tests (Change 5) must cover the new matcher format; add `recover()` in the silence-processing path as a safety net.
- *Risk:* Template-expanded annotation values contain characters that break downstream label parsing.  
  *Mitigation:* The existing label sanitiser (if any) should already handle arbitrary strings; verify in the integration test with a template value containing special characters.
