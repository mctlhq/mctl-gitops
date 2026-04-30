# Tasks: mcp-json-smuggling-investigation

## Phase 1 — Audit

- [ ] 1. Read and document `mcp-go` v0.31 JSON-RPC envelope parsing code —
  locate the HTTP handler entry point, trace the path from raw body read to
  `method`/`params`/`id` extraction, and identify every call to
  `json.Unmarshal`, `json.NewDecoder`, or third-party JSON libraries. Note
  all struct tags on envelope and tool-parameter types.
  DoD: A written `audit-finding.md` document exists in this proposal folder
  with: (a) the full call-stack from HTTP body to tool dispatch, (b) struct
  definitions and tags for the JSON-RPC envelope types in `mcp-go` v0.31,
  (c) a preliminary verdict ("likely affected" / "likely not affected").

- [ ] 2. Prepare smuggling payload corpus (depends on 1) — create a set of
  crafted JSON-RPC request bodies with smuggled field names in both the
  envelope and tool params. Minimum variants:
  - Envelope: `"Method"`, `"Params"`, `"Id"`, `"Jsonrpc"` (title-case)
  - Envelope: `"METHOD"`, `"PARAMS"` (upper-case)
  - Tool params for `trigger_workflow`: at least two parameter key variants
  - Tool params for one identity write tool: at least two parameter key variants
  DoD: A `payloads/` directory exists in this proposal folder containing the
  corpus as JSON files; each file is named `<variant>.json` with a comment
  block describing the expected behaviour.

- [ ] 3. Replay payloads against staging MCP endpoint (depends on 2) — use
  MCP Inspector (or `curl`) to send each payload in the corpus to the staging
  `https://api.mctl.ai/mcp` endpoint. Record HTTP status code, JSON-RPC
  response code, and whether the tool handler was invoked (check audit logs).
  DoD: A replay results table is added to `audit-finding.md` with one row
  per payload variant showing: payload name, HTTP status, JSON-RPC response,
  tool-handler invoked (yes/no/unknown). Replay is run by a team member other
  than the author.

- [ ] 4. Finalise audit verdict (depends on 3) — based on static review and
  replay results, update `audit-finding.md` with a definitive verdict:
  "affected" or "not affected", with evidence citations.
  DoD: `audit-finding.md` contains a VERDICT section with a clear one-line
  conclusion, evidence links, and a recommended next step (proceed to Phase 2
  or proceed to documentation task 7).

## Phase 2a — Patch (execute only if verdict is "affected")

- [ ] 5. Implement strict envelope-parsing middleware (depends on 4, verdict
  = "affected") — write an HTTP middleware that wraps `mcp-go`'s
  `ServeHTTP`. The middleware reads the raw body, decodes the JSON-RPC
  envelope using `json.NewDecoder` with `DisallowUnknownFields()` and
  explicit lowercase struct tags, rejects non-canonical field names with a
  JSON-RPC parse-error (`-32700`), and passes the request to `mcp-go`
  unmodified if validation passes.
  DoD: Middleware is implemented and unit-tested; `mcp-go`'s `ServeHTTP` is
  not modified; all 24 tool calls succeed with canonical lowercase envelopes
  in integration tests; smuggled-field requests return `-32700`.

- [ ] 6. Audit tool-parameter struct tags in `mcp-go` v0.31 (depends on 5)
  — verify that every tool input struct registered with `mcp-go` uses
  strictly lowercase `json:` tags. Open a patch or upstream issue for any
  non-lowercase tag found.
  DoD: A checklist of all 24 tool input types is documented; any non-lowercase
  tags are either patched in a fork or have an upstream issue filed with a link
  in the task comments.

## Phase 2b — Documentation guard (execute only if verdict is "not affected")

- [ ] 7. Add code comment and CI regression guard (depends on 4, verdict =
  "not affected") — add a comment block in the MCP handler registration
  code referencing CVE-2026-27896 and citing the specific `mcp-go` code path
  (file + line) that prevents the attack. Add a CI test that replays the
  payload corpus and asserts that all smuggled-field requests are rejected or
  produce no tool invocation.
  DoD: Comment is committed and references this proposal; CI test is added
  under `_test.go`; test passes on the current `mcp-go` v0.31 and is
  documented as a regression guard for future `mcp-go` upgrades.

## Tests

- [ ] T1. Static audit — `audit-finding.md` documents the full deserialization
  call-stack with line references to `mcp-go` v0.31 source.
- [ ] T2. Replay coverage — all payload variants in the corpus are replayed
  and results recorded; no variant is left untested.
- [ ] T3. (If affected) Middleware unit tests — for every envelope-level
  smuggled field variant, the middleware returns HTTP 200 with a JSON-RPC
  `-32700` body; for all canonical variants, the tool handler is invoked.
- [ ] T4. (If affected) Regression integration test — all 24 MCP tools
  respond correctly to canonical lowercase requests after the middleware is
  deployed to staging.
- [ ] T5. CI replay guard — the payload corpus is run in CI on every
  `mcp-go` version bump and results are asserted against the expected
  behaviour documented in `audit-finding.md`.

## Rollback

Phase 1 (audit) introduces no production changes; no rollback is required.

Phase 2 middleware (if deployed):

1. The middleware is registered as a chi sub-router middleware wrapping only
   the `/mcp` route. To roll back, remove the middleware registration and
   redeploy via the GitOps pipeline (image tag revert or code revert PR).
2. ArgoCD rolling update with `PodDisruptionBudget` (`minAvailable: 1`)
   ensures at least one healthy replica serves traffic during rollback.
3. The middleware does not modify any persistent state (no database writes,
   no Vault changes), so rollback is instantaneous once pods are replaced.
4. If rollback is required, open a post-mortem issue documenting which
   legitimate client triggered the rejection before re-attempting the patch.
