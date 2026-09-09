# Cloudflare MCP Portal compatibility spike: modern protocol, public-client OAuth, and Phase A+B evidence

## Context

Issue #585 is the `mctl-telegram` execution child of `mctlhq/.github#44` under roadmap `mctlhq/.github#35`.

This spike must measure the Cloudflare-facing boundary without duplicating `mctl-telegram#568` and without extending deprecated MCP mechanisms.

A review of the pinned SDK changes an important assumption in the original proposal: `mark3labs/mcp-go v1.0.0` already has a distinct modern `2026-07-28` path. In that path:

- requests are self-describing per request;
- `server/discover` replaces `initialize` as the discovery entry point;
- `initialize` is a removed method for `2026-07-28` and should be rejected;
- no `Mcp-Session-Id` is minted for modern requests;
- `MCP-Protocol-Version`, `Mcp-Method` and, where applicable, `Mcp-Name` are part of the HTTP binding;
- legacy clients may still exercise the older initialize/session flow.

Therefore absence of an explicit `WithStateLess(true)` option is **not** sufficient evidence that the modern path is sessionful. The spike must probe modern and legacy behavior separately.

On OAuth, the current authorization-server metadata advertises `token_endpoint_auth_methods_supported: ["none"]`: mctl is a public-client + PKCE server today. The Cloudflare manual/pre-registered-client path is acceptable only if Cloudflare can operate as such a public PKCE client. The spike must not silently add confidential-client/client-secret semantics just to make the Portal work.

## Goals

1. Produce measured evidence for modern `2026-07-28` behavior through direct mctl and Cloudflare Portal paths.
2. Keep a separate legacy compatibility probe for clients that still use initialize/session semantics.
3. Validate a non-DCR, exact-redirect, pre-registered OAuth client path without weakening redirect policy.
4. Determine whether Cloudflare supports mctl's current public-client (`token_endpoint_auth_method=none`) + PKCE contract.
5. Produce a compatibility matrix that clearly distinguishes in-process code evidence, deployed direct evidence, and Portal evidence.

## User stories

- AS a platform engineer I WANT one repeatable probe that can target direct or Portal endpoints SO THAT compatibility claims come from evidence.
- AS an operator I WANT a pre-registered exact redirect client SO THAT Cloudflare does not depend on deprecated DCR.
- AS a security reviewer I WANT the preferred Portal path to avoid the implicit redirect-host allow-list entirely SO THAT adding Cloudflare does not broaden redirect acceptance.
- AS a reviewer I WANT live-only cells marked as operator evidence SO THAT CI results are never mislabeled as production results.
- AS the `#568` owner I WANT this spike to observe modern stateless behavior without changing Telegram session ownership or replica count.

## Acceptance criteria

### A. Modern MCP `2026-07-28` probe

- WHEN the probe runs in modern mode THE SYSTEM SHALL send a direct modern request, beginning with `server/discover`, without first calling `initialize`.
- EVERY modern request SHALL carry the modern per-request protocol metadata expected by the pinned SDK, including protocol version, client info and client capabilities, plus the required HTTP protocol/method headers.
- WHEN invoking a named capability such as `tools/call`, THE SYSTEM SHALL send `Mcp-Name` consistently with the JSON-RPC body.
- THE SYSTEM SHALL record the result of `server/discover`, including supported protocol versions and server identity metadata where returned.
- THE SYSTEM SHALL call `tools/list` and exactly one structurally read-only tool without using `Mcp-Session-Id`.
- THE SYSTEM SHALL record whether any modern response unexpectedly minted/required `Mcp-Session-Id`; the expected modern behavior is no session id, but the probe records evidence rather than hard-coding a production result.
- THE SYSTEM SHALL explicitly probe `initialize` in modern mode as a **removed-method negative test** and record the HTTP/JSON-RPC rejection. It SHALL NOT use `initialize` to bootstrap modern requests.
- THE SYSTEM SHALL test header/body consistency: missing or mismatched `Mcp-Method` / `Mcp-Name` is a protocol error, not an "echo" experiment.
- THE SYSTEM SHALL treat `server/discover` absence on an older deployed upstream as a measured compatibility result, not as permission to fall back silently inside the modern row.

### B. Legacy compatibility probe

- WHEN the probe runs in legacy mode THE SYSTEM SHALL use the legacy initialize/session flow appropriate to the selected legacy protocol version.
- THE SYSTEM SHALL record whether `Mcp-Session-Id` is minted and required for subsequent legacy calls.
- Legacy behavior SHALL be reported separately from the modern row; no result SHALL combine modern and legacy semantics into one `session_required` boolean without a protocol-mode label.
- No new legacy HTTP+SSE implementation SHALL be added.

### C. Probe safety and reporting

- `tools/call` SHALL only execute a tool whose `tools/list` annotations report `readOnlyHint=true`.
- Default target SHALL be a non-content, read-only identity/status tool such as `get_my_send_status` when available.
- Reports SHALL NOT contain bearer/refresh tokens, authorization codes, message bodies, chat titles, peer identifiers, phone numbers, or full session ids.
- Reports MAY contain protocol versions, method/tool names, status codes, JSON-RPC error codes, annotation flags, boolean observations, counts, and session-id length/presence only.
- Missing bearer token SHALL still allow OAuth metadata and unauthenticated challenge checks; authenticated cells become `skipped`.

### D. Evidence provenance

The compatibility matrix SHALL have distinct rows for:

1. `in-process-current-main` — CI/in-process handler evidence;
2. `direct-deployed` — operator probe against preview or `tg.mctl.ai`;
3. `cloudflare-portal` — operator probe through the configured Portal.

CI SHALL NOT label an `httptest` result as live `tg.mctl.ai` evidence.

Every row SHALL record timestamp/build/ref where known and the selected protocol mode/version.

### E. OAuth for Cloudflare without DCR

- THE preferred Portal path SHALL use a pre-registered client with exact redirect URI matching and SHALL NOT require `/oauth/register`.
- The pre-registered client configuration SHALL be structured and explicit (for example JSON carrying `client_id` and exact `redirect_uris`), not a lossy comma/colon encoding.
- The Portal callback SHALL NOT be added to `OAUTH_ALLOWED_IMPLICIT_HOSTS` or any new additive implicit-host list for the preferred path. Exact client registration is the security boundary.
- Existing implicit/DCR compatibility behavior SHALL remain unchanged for existing clients.
- PKCE-S256, issuer, resource/audience and scope behavior SHALL remain unchanged.
- THE spike SHALL verify that Cloudflare can use a public OAuth client with `token_endpoint_auth_method=none` and PKCE.
- IF Cloudflare requires `client_secret_basic`, `client_secret_post`, or another confidential-client method THEN Phase B SHALL be marked BLOCKED and a separate security-reviewed child issue SHALL decide whether mctl should add confidential-client support. This spike SHALL NOT quietly add it.
- DCR SHALL remain compatibility-only and SHALL NOT be an acceptance dependency.
- CIMD remains the target MCP-native registration direction when supported end-to-end; no new DCR-only product assumption is allowed.

### F. Portal identity and affinity

- WITH `Require user auth=ON`, two distinct corporate users SHALL resolve to two distinct upstream mctl/Telegram principals.
- The Portal admin/sync credential SHALL NOT be reused as an end-user principal.
- The operator procedure SHALL verify that per-user identity survives the Portal path and does not collapse routing onto one shared `sub`.
- Protocol statelessness SHALL NOT be interpreted as permission to increase `mctl-telegram` replicas; MTProto and Local Bridge ownership remain separate concerns.

## Out of scope

- Flipping production `/mcp` transport/session configuration; `#568` owns direct stateless rollout decisions.
- Refactoring `cmd/canary` or the load generator. This spike must not touch the paging probe merely to deduplicate client plumbing; dedup can follow after the probe is validated.
- MCP Tasks, MCP Apps, Gateway/DLP, or Code Mode.
- Adding HTTP+SSE, Roots, Sampling, MCP Logging, or new DCR dependence.
- Adding confidential OAuth client authentication without a separate decision.
- Changing MTProto/Local Bridge ownership, replica count, or HPA semantics.
- Making `mcp-enterprise.mctl.ai` the final tenant security perimeter.

## Open questions to resolve with evidence

- Which modern behaviors are already active in the deployed `tg.mctl.ai` build versus only supported by the pinned SDK/current main?
- Does the configured Cloudflare Portal support public-client + PKCE upstream OAuth with `token_endpoint_auth_method=none`?
- Which exact callback URI does the real Portal display?
- Does Cloudflare preserve/validate modern method/name headers end-to-end?
- Do two Portal users arrive upstream as distinct mctl principals?
