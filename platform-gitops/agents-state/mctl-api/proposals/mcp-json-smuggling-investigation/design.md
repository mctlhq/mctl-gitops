# Design: mcp-json-smuggling-investigation

## Current state

mctl-api runs an MCP server via `mark3labs/mcp-go` v0.31 at
`https://api.mctl.ai/mcp` (Streamable HTTP, POST + GET). The library handles:

1. **Transport** — HTTP request reading, SSE session management.
2. **JSON-RPC envelope parsing** — deserializing the incoming body into a
   `JSONRPCRequest` struct (or equivalent) containing `jsonrpc`, `method`,
   `params`, and `id` fields.
3. **Tool dispatch** — routing the parsed `method` value to the registered
   tool handler.
4. **Parameter deserialization** — unmarshaling `params` into the tool's
   input schema struct via `encoding/json`.

All four steps rely on Go's standard `encoding/json` package. The documented
behaviour of `encoding/json.Unmarshal` is that field matching is
case-insensitive: a JSON key `"Method"` successfully populates a struct field
named `Method` or `method`. This is the root cause of CVE-2026-27896 in
`modelcontextprotocol/go-sdk`.

Whether `mcp-go` v0.31 is affected depends on two sub-questions:
(a) Does `mcp-go` use `json.Unmarshal` (case-insensitive) or
    `json.NewDecoder` with `DisallowUnknownFields()` plus a strict
    pre-validation step for the envelope?
(b) Even if the envelope is parsed correctly, do individual tool parameter
    structs use tagged lowercase fields consistently, or do any use uppercase
    or mixed-case tags that could be exploited?

Neither question is answerable without reading `mcp-go`'s source at v0.31 and
replaying live payloads. This proposal structures that work.

Architecture reference: `context/architecture.md` — MCP server, 24 tools
(11 read + 13 write), Streamable HTTP, OAuth 2.0 PKCE, `admins` tenant,
cross-tenant write blast radius for identity and workflow tools.

## Proposed solution

The investigation proceeds in two sequential phases; the patch phase is
conditional on the audit outcome.

### Phase 1: Audit (mandatory)

1. **Static code review of `mcp-go` v0.31** — read the JSON-RPC envelope
   parsing code (look for `json.Unmarshal`, `json.NewDecoder`, struct tags,
   and any pre-validation logic). Document the exact deserialization path
   from raw HTTP body to dispatched tool handler.

2. **Payload replay via MCP Inspector** — against the staging MCP endpoint,
   send crafted requests with smuggled field names in both the envelope and
   in tool `params`. Variants to test:
   - `"Method"` instead of `"method"` (route bypass attempt)
   - `"Params"` instead of `"params"` (parameter injection)
   - `"Id"` instead of `"id"` (response-correlation confusion)
   - Mixed-case tool parameter keys for at least two write tools
     (`trigger_workflow`, one identity tool)
   Record HTTP status codes, JSON-RPC error codes, and whether the tool
   handler was invoked.

3. **Finding document** — a written verdict ("affected" / "not affected")
   with line-level evidence from the static review and replay results,
   stored in this proposal folder as `audit-finding.md`.

### Phase 2: Patch (conditional on "affected" verdict)

If Phase 1 concludes mctl-api IS vulnerable:

4. **Strict envelope parser** — wrap `mcp-go`'s HTTP handler with a
   middleware that reads the raw request body, performs a strict
   case-sensitive pre-parse of the JSON-RPC envelope fields using
   `json.NewDecoder` with `DisallowUnknownFields()` and explicit struct tags
   (`json:"method"` etc.), and rejects any request where a canonical field
   name is not exactly lowercase. Return a JSON-RPC parse-error
   (`-32700`) for rejected requests.

   This approach wraps rather than replaces `mcp-go`, preserving ADR 0001.
   The middleware sits between the HTTP router (chi/v5) and `mcp-go`'s
   `ServeHTTP` handler.

5. **Tool parameter hardening** — audit `mcp-go`'s struct tags for all 24
   tool input types. If any tool parameter struct uses field tags that are
   not strictly lowercase, open a targeted patch or upstream issue.

If Phase 1 concludes mctl-api is NOT vulnerable:

6. **Documentation and regression guard** — add a code comment in the MCP
   handler registration block referencing CVE-2026-27896 and the specific
   `mcp-go` code path that prevents the attack. Add a CI test that replays
   the smuggling payloads and asserts they are rejected or ignored correctly
   (see Tasks), pinned to `mcp-go` v0.31.

## Alternatives

**A. Assume not-affected without auditing and add only a WAF rule.**
WAF rules based on field-name case are bypassable (Unicode normalization,
percent-encoding). Without code-level verification we cannot rule out
exploitation paths that bypass network controls entirely. Rejected — the audit
cost is low and the blast radius (write tools, cross-tenant) is high.

**B. Pre-emptively apply strict deserialization without auditing.**
Applying the middleware blindly may introduce subtle breakage in legitimate
MCP clients that rely on case-insensitive field handling (unlikely given the
spec, but possible with non-conformant clients). Doing the audit first ensures
the patch is applied only where needed and that the regression test set covers
real behaviour before and after. Rejected as the sole approach; retained as
Phase 2 action if Phase 1 confirms vulnerability.

**C. Replace mark3labs/mcp-go with modelcontextprotocol/go-sdk (which has
the fix in v1.3.1).**
Prohibited by ADR 0001. The go-sdk migration would require re-validating all
24 tool schemas, rewriting transport configuration, and re-testing OAuth 2.0
PKCE. Even if ADR 0001 were waived, the scope of that change far exceeds a
targeted patch. Rejected.

## Platform impact

**Migrations**
None for Phase 1 (audit only). Phase 2 (if triggered) adds a middleware
wrapper to the existing MCP HTTP handler; no database, CRD, or Vault changes.

**Backward compatibility**
Phase 1 has zero runtime impact. Phase 2 middleware rejects malformed
(non-canonical) envelopes that the MCP spec does not require clients to send.
All conformant MCP clients (Claude.ai connector, MCP Inspector, local Claude
Code sessions) use lowercase field names and will be unaffected. If a
non-conformant client is discovered, it is treated as a client bug and
documented.

**Resource impact**
The middleware adds one `json.NewDecoder` call per MCP request on the hot
path. For the expected request volume on the `admins` tenant this is
negligible (< 1 µs per request). No memory allocation increase is anticipated.
The `labs` tenant does not run mctl-api; no `labs` impact.

**Risks and mitigations**

| Risk | Likelihood | Mitigation |
|---|---|---|
| Audit is inconclusive (mcp-go source is ambiguous) | Low | Replay tests provide empirical evidence independent of source reading |
| Patch middleware incorrectly rejects valid requests from Claude.ai | Low | Regression test against Claude.ai connector in staging before merge |
| mcp-go upstream changes the deserialization path in a future version | Medium | CI replay tests pinned to `mcp-go` version; re-run on every version bump |
| CVE-2026-27896 is already being exploited against the endpoint | Low-Medium | Audit is expedited; no production change required until Phase 2 is triggered |
