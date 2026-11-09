# Multi-tenant Glovo MCP account connections and provider adapter, with a gated real-account pilot

## Context

Issue #1227 asks for the product path of the Glovo assistant to be multi-tenant from its
first usable version. The target is one public MCP endpoint, `https://glovo.mctl.ai/mcp`
(hostname approved, not provisioned). It carries a separate Glovo account connection for
each authenticated MCTL principal within each tenant. The current artefacts are the #1184
spike proposal (status `implemented`, PR #1187 still OPEN and unmerged), with its fake
accounts and loopback mock API and the verdict `MOCK_ONLY_PENDING_CONNECTOR`, and the
#1225 runtime-boundary proposal (status `proposed`, recommending `REUSE_EXISTING` on
.github#324). Neither is a real user-facing Glovo connection. The only known path to
authenticated basket access is the unofficial MIT project `denya/glovo-skill`. Its
`session.json` is local, single-user and bootstrapped through Chrome, and cannot be
moved into a shared hosted server.

This proposal covers M0 in full: the design, connector feasibility, the frozen identity
and connection contract, the closed MCP tool schemas, the connection and secret state
machine, the threat model and the go/defer decision. It also specifies M1 (a
multi-tenant core with a FAKE provider) precisely enough to build. M1 is built only
after its gates clear and a separate approval. M2 (a real-account pilot) and M3
(multi-user activation) are defined only as gates. This proposal executes nothing that
touches a real Glovo account, a public hostname or production.

Recorded decision: **`GO_FAKE_MULTITENANT`** (M1 may proceed after gates G1 and G2 and
its own approval). **`GO_REAL_PILOT` is not granted.** The real-provider path is
**`BLOCKED_PROVIDER_ACCESS`** until gate G3 (a sanctioned or legally reviewed access path)
clears.

## AMEND 2026-11-08 — action approvals, tenancy and readiness (normative)

**M0 remains documentation/tests only; NO M1 coding or real account connection is authorized by approving this proposal.**

1. **Never treat human-input clarification as approval.** The existing `docs/contracts/mctl-api-human-input.md` states that answering `hir_...` does NOT authorize a side effect. Before *every* externally observable provider basket mutation, mctl-api MUST create/resolve the canonical WorkItem/Execution `wi_/we_`, issue an `ActionApprovalRequest` (`aar_`) bound to that execution and the exact `(tenant_id, owner_principal_id, order_id, glovo_connection_id, install_id, install_revision, basket_fingerprint, mutation_intent_hash)`. Only a verified human identity, not the requesting agent, may decide it. On execution, enforce live identity+tenant+install+connection+fingerprint/policy/budget revalidation and the existing single-use **approval receipt gate** (reserve/consume/mark outcome on success or safe failure). Wrong owner, execution, revision, fingerprint, tenant, expired or replayed receipt = NO PROVIDER WRITE. A clarification answer or the existence of an automation schedule is NEVER sufficient.
2. **G2 must reference an actual, separately approved mctl-api implementation**, not only mctl-api#948: PR #950 merged the canonical `AutomationDefinition` contract (docs/schemas/harness), but did NOT deliver Glovo-scoped principal/tenant selection, connection registry, authenticated MCP subject delegation, per-owner order index, `aar_` request/receipt integration or live permission checks. Until these are implemented, merged, independently reviewed and exercised with cross-tenant and same-tenant-different-user negative tests, the M1 integration and M3 rollout are BLOCKED.
3. **Credential revocation terminology must be honest.** Deleting an AES-GCM ciphertext while a stable per-connection HKDF key can still be re-derived from a surviving master key is **not cryptographic erasure**. Prefer a truly independent random per-connection DEK wrapped by a KEK, with revocation destroying every active key copy and limiting backup/snapshot retention, or classify it only as best-effort data/session deletion. Do not claim hard crypto-shredding without proving the key lifecycle, cache eviction and backup behaviour.
4. Temporal control and lower-trust provider MUST be in **separate Temporal namespaces**, with no provider permission on control or DevLoop. A plain Workflow Activity cannot cross namespaces. Require an approved Nexus bridge or authenticated mctl-api message/results bridge with exact SDK+server compatibility, replay and identity fencing. No trust from task-queue names alone.
5. **Account connection and real provider readiness:** `glovo_connect_account` in M1 is **fake/synthetic only** and must be clearly labelled as such to test consumers. Real user credentials must never be taken from MCP prompts or put into a shared hosted `session.json`. G3 requires documented authorized/legally reviewed access, independently validated Montenegro availability and phone-basket continuity; otherwise `BLOCKED_PROVIDER_ACCESS`. No checkout/order/payment tool or silent basket write.
6. **Identity contract:** `https://glovo.mctl.ai/mcp` is a separate OAuth protected resource; verify issuer/audience and how an MCTL `prn_` principal maps to current surface/Telegram claims. If personal scope is unsupported per .github#309, **reject**, never fall back to `labs` or `mctl`. Source repository choice G1 remains owner-controlled at .github#324.

## User stories

- AS an MCTL principal in tenant A I WANT to connect my own Glovo account to
  `glovo.mctl.ai/mcp` SO THAT my assistant can read my history and prepare a basket,
  and nobody in tenant A or any other tenant can use that connection.
- AS a second principal in the same tenant I WANT my own independent Glovo connection
  SO THAT sharing a tenant never means sharing a Glovo account.
- AS the platform owner I WANT the connection, secret, install and authorization model
  to be multi-tenant before any pilot SO THAT the pilot cohort is only an allowlist and
  not a different architecture.
- AS a security reviewer I WANT closed tool schemas, a written threat model and negative
  isolation tests SO THAT I can approve M1 and later M2 on evidence.
- AS a user I WANT every basket change to need my explicit per-action approval, and no
  checkout or payment tool to exist, SO THAT the assistant can never spend my money.
- AS an operator I WANT kill switches at each layer and no regression to `tg.mctl.ai`
  SO THAT the Glovo work can be switched off without touching the Telegram product.

## Acceptance criteria (EARS)

M0 deliverables (this proposal's execution scope):

- THE SYSTEM SHALL contain `docs/adr/0010-glovo-multitenant-connections.md` (status
  Proposed). It records the system boundary, the identity chain, the connection and
  secret state machine, the authorization checkpoints, the decision
  `GO_FAKE_MULTITENANT` and the gates G0-G6 defined in design.md.
- THE SYSTEM SHALL contain `docs/reports/glovo-connector-feasibility.md` with an
  evidence table whose rows are: Glovo Discover MCP, `denya/glovo-skill` v0.2.1, an
  official or partner API, account/session lifecycle, mobile basket continuity,
  Montenegro coverage, applicable terms and license obligations. Each cell is labelled
  `SOURCE` (with link and date), `OBSERVED` or `UNVERIFIED`.
- THE SYSTEM SHALL contain `docs/contracts/glovo-mcp-tools.json`, a closed JSON Schema
  set (`additionalProperties: false` on every object) for exactly seven tools:
  `glovo_auth_status`, `glovo_connect_account`, `glovo_get_order_history`,
  `glovo_preview_reorder`, `glovo_get_basket`, `glovo_prepare_order` and
  `glovo_order_status`.
- THE SYSTEM SHALL contain `docs/agent-runtime/glovo-threat-model.md`. It covers account
  bootstrapping, session storage and rotation, CSRF, SSRF, remote-browser trust, host
  egress, abuse, token expiry, confused deputy, replay and cross-tenant access, and
  gives each threat a mitigation and a named test ID.
- WHEN `go test ./docs/...` runs THE SYSTEM SHALL fail if `glovo-mcp-tools.json` names
  a tool outside the seven-tool allowlist, contains a tool whose name or description
  matches `place|pay|checkout|purchase|submit_order`, or contains an input schema that
  is not closed or that accepts any of these properties: `tenant`, `tenant_id`,
  `principal`, `principal_id`, `namespace`, `task_queue`, `workflow_id`, `url`,
  `endpoint`, `cookie`, `session`, `password` or `token`.
- WHEN `go test ./docs/...` runs THE SYSTEM SHALL fail if the ADR, the threat model or
  the report contains a string shaped like a credential (a JWT, a `Cookie:` or
  `Set-Cookie:` header, or a long hex or base64 value). The check reuses the key list
  of `internal/audit/redact.go` where applicable.
- WHILE the M0 change is merged THE SYSTEM SHALL leave the root `go.mod`, the server
  image (`Dockerfile`), the worker image (`Dockerfile.agent-worker`), the release
  workflows and `tg.mctl.ai` behaviour unchanged.

Identity and authorization contract (frozen in M0, enforced from M1):

- THE SYSTEM SHALL key every Glovo connection by `(tenant_id, principal_id,
  provider='glovo', provider_account_ref)` and identify it by an opaque server-generated
  `glovo_connection_id` (`gcn_` prefix, 128-bit random). It SHALL store the principal,
  the tenant membership, the assistant install and revision, the connection, the
  provider identity and each secret as separate records.
- WHEN an MCP request arrives at `glovo.mctl.ai/mcp` THE SYSTEM SHALL derive the
  principal from the validated access token (audience `https://glovo.mctl.ai/mcp`)
  and resolve the tenant through mctl-api membership. It SHALL NOT read either from
  tool arguments.
- IF the principal belongs to more than one tenant and the request carries no
  server-issued tenant selection bound to its token THEN THE SYSTEM SHALL refuse with
  `ambiguous_tenant`.
- IF the resolved scope is `personal:<principal>`, or is otherwise unsettled by
  .github#309, THEN THE SYSTEM SHALL refuse with `scope_unsupported`.
- THE SYSTEM SHALL NOT fall back to the hosting workspace (`labs`), to `mctl`, or to a
  deployment-wide setting such as `MCTL_WORK_ITEM_TENANT` when it resolves an end
  user's tenant.
- THE SYSTEM SHALL re-run the authorization check (principal active, membership active,
  install active, revision equal, connection `active` and owned by the principal in
  that tenant) at five points: MCP ingress, workflow start, before each provider write,
  at handoff open, and on every signal or consent. IF any part fails THEN THE SYSTEM
  SHALL refuse with a typed code (`not_authorized`, `stale_install`, `no_connection`,
  `connection_revoked`) and SHALL NOT call the provider.
- WHEN a connection is revoked, its install is uninstalled, or its install is reinstalled
  at a new revision THE SYSTEM SHALL make every in-flight workflow bound to the old
  `(connection_id, install_revision)` fail its next checkpoint, and SHALL NOT let a
  reinstall revive the old connection or its consents.
- THE SYSTEM SHALL NOT let any user or tool argument choose the Temporal namespace, task
  queue, workflow ID or delegated principal. Workflow IDs are derived server-side as
  `glovo-order/<tenant_id>/<order_id>`.

Connection and secret lifecycle:

- THE SYSTEM SHALL move a connection only through the states `pending_handoff`,
  `pending_provider`, `active`, `expired`, `revoked` and `failed`, using the transitions
  in design.md. Any other transition SHALL be refused.
- WHEN `glovo_connect_account` is called THE SYSTEM SHALL return only a single-use,
  short-lived (at most 10 minutes) out-of-band handoff URL on an MCTL-controlled origin,
  plus the connection's state. The URL carries a 256-bit token of which only the hash is
  stored. THE SYSTEM SHALL NOT ask for, accept or return a Glovo password, cookie,
  session file or OTP through MCP, chat, GitHub or logs.
- THE SYSTEM SHALL keep provider credential material only in AES-256-GCM sealed blobs,
  with a key derived per `(tenant_id, connection_id)` through HKDF from a
  Glovo-specific master key (a new HKDF info label, separate from
  `mctl-telegram-session-v2` in `internal/crypto/aesgcm.go`). Only the provider worker
  may unseal them.
- THE SYSTEM SHALL keep session material out of Temporal histories, logs, tool replies,
  prompts, audit payloads and GitHub. Histories carry only opaque IDs.
- THE SYSTEM SHALL NOT describe the consumer-login handoff as OAuth unless Glovo
  officially supports OAuth for third parties. The tool and docs call it a "delegated
  account connection".

Per-action consent and order safety:

- WHEN `glovo_prepare_order` succeeds THE SYSTEM SHALL return a preview with a basket
  fingerprint and an expiry, and SHALL NOT change the provider basket.
- THE SYSTEM SHALL change the provider basket only after a canonical `aar_` ActionApprovalRequest, human decision and live single-use approval receipt bound to `(tenant_id, owner_principal_id, execution_id, order_id, fingerprint, install_revision, connection_id, mutation_intent_hash)`. A `hir_` clarification answer is never approval. A replayed, expired, wrong-execution, cross-tenant, stale or mismatched receipt SHALL be refused with `consent_invalid` before any write.
- THE SYSTEM SHALL expose no tool, activity or adapter method that places an order, pays,
  books a delivery slot or checks out.
- IF the provider answers with an error, a protocol change, a timeout or an
  unrecognised shape THEN THE SYSTEM SHALL report `CONNECTOR_UNAVAILABLE` and SHALL NOT
  fabricate a success.
- WHILE no provider-confirmed evidence exists THE SYSTEM SHALL report the order outcome
  as `OUTCOME_UNKNOWN`.

Gating:

- WHILE gate G3 (sanctioned or legally reviewed provider access) is not recorded THE
  SYSTEM SHALL ship only the fake provider adapter, and any real adapter SHALL be
  absent from the build.
- THE SYSTEM SHALL treat each of the following as a separate human approval, none of
  which this proposal grants: M1 build, image publication, GitOps deploy, DNS or TLS for
  `glovo.mctl.ai`, a real-account login, a provider basket write, and pilot activation.

## Out of scope

- Any real Glovo login, real session, real basket write, purchase, payment, checkout or
  delivery-slot booking.
- Provisioning `glovo.mctl.ai`, DNS, TLS, ingress, Temporal namespaces, Kubernetes
  namespaces, NetworkPolicies or Vault paths (these belong to mctl-gitops, under #2456
  and #2457).
- mctl-api implementation of tenant resolution, connection index or Automation Control
  Plane endpoints (mctl-api#948). This proposal writes the contract mctl-api must
  satisfy, not its code.
- Temporal client authentication (mctl-gitops#2456).
- Repository creation for a separate provider-adapter repo (only if a #1225 promotion
  trigger fires).
- Personal-scope semantics (.github#309). They fail closed here.
- Changes to the existing Telegram assistant install (`agent_profiles`) or to the
  `hr-recruiter` assistant.

## Open questions

- Authorization server for `glovo.mctl.ai/mcp`. This proposal assumes the MCTL platform
  authorization server (mctl-api, which issues `prn_` principals) is the issuer, and
  that `glovo.mctl.ai` is an OAuth protected resource (RFC 9728) with its own audience.
  It is not `tg.mctl.ai`'s Telegram-identity authorization server (ADR 0004). The issue
  says "OAuth/MCTL principal", but the issuer and the token claim names are not
  confirmed.
- Principal identifier format. The issue says `prn_`. The pinned mctl-api contracts in
  this repo (`docs/contracts/mctl-api-human-input.md`) use `github:<login>` actor refs.
  The mapping between them was not observed.
- Runtime ownership verdict on .github#324 is not recorded. #1225 recommends
  `REUSE_EXISTING` (the provider adapter in mctl-telegram as its own Go module and
  image). M1's repo placement follows that recommendation and is gated on it (G1).
- Whether Glovo offers any official or partner API giving delegated, per-user basket
  access, and its terms. This is unknown and needs owner or legal outreach (G3).
- Whether a basket written through the consumer web API appears on the same account in
  the mobile app (mobile basket continuity). UNVERIFIED.
- Montenegro account and store coverage for any of the paths. UNVERIFIED.
- Where the out-of-band connection handoff page is hosted (`glovo.mctl.ai/connect/...`
  or an mctl-api or portal origin), and whether any remote-browser bootstrap is
  acceptable at all. The design defaults to "no remote browser in M1; the decision is
  deferred to G3".
- Whether the pilot allowlist lives in mctl-api (per principal) or in the facade's
  config. The default is mctl-api, so that the facade holds no identity list.
