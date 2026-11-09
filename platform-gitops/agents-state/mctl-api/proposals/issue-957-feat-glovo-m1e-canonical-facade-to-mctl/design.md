# Design: issue-957-feat-glovo-m1e-canonical-facade-to-mctl

## Amendment 2026-11-09 (b)

Companion edits from the mctl-gitops AMEND PR that fixes mctl-api#985, #986, #988, #989,
#959 and mctl-agents#1059 after their independent reviews. Owner decisions of
2026-11-09 (b): **A**, one physical database for every Glovo store, explicit URLs, no
`AUDIT_DB_URL` fallback, proof of one database (not URL equality), separate schemas and
roles, one lock order; **B**, #986 is the mctl-api store/serve slice of the read
contract that mctl-agents#1059 defines. Where this section and older text disagree, this
section wins; the contradicted passages below are edited to match.

| Driver | Change here |
|---|---|
| Decision A (supersedes D2 and the M11 row) | §6b rewritten: `GLOVO_DB_URL`, `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` set explicitly to one physical database, proven by #985 `control.ProveOneDatabase` (nonce written on one pool, read on the others); `GLOVO_DB_URL` is now part of the transaction; the "different database" branch and its TOCTOU test gate are removed. Schemas and roles per #959's role table |
| One lock order (#985 P2-4, #989 P2-3, #959) | §6b holds the **canonical lock order L1..L6** and the table of which path takes which levels. #985, #988, #989 and #959 reference it and do not restate it |
| #988 P2-7 (two owners of the join-ref table) | §2a: the table is #988's `glovo.join_refs`, minted through #988 `MintJoinRefTx`; the `order` ref is #988's own `ordr_` (the `order_ref` of the order row). #988's internal `pord_` primary key is unexported and never leaves the store |
| #989 P2-4 (second approval authority) | §3 and §6: prepare creates the #988 order and the pending `aar_` through #989 `CreateGlovoApprovalTx`; `IntentHash` comes from #989 `GlovoIntent`. No order `approved` state, no #954 `providerorders` service |
| mctl-agents#1059 approval basket | §3, §5 and §6: the preview and basket `fingerprint` are computed by mctl-api as `"sha256:"+hex(sha256(JCS(approval basket)))` over the #1059 approval-basket projection, prices included; `mctl-basket/v1` and any facade-side fingerprint are gone |
| #1059 / #986 read binding (no echo) | §5: the handler no longer checks echoed binding fields; #986 `FetchReadResult` takes every binding from the stored command row and checks scope, connection and revision; the handler checks kind and schema version only |
| M5/D1 wording | Reads are history, preview and basket. Prepare is a write that consumes a stored preview; it is not a read kind |
| Preview wire field | `POST /previews` keeps the wire field `order_ref` (the facade is unchanged); its value is the `pho_` history-order ref of #1059, not an `ordr_` |

## Amendment 2026-11-09

Resolves the crosswalk mismatches assigned to this slice (M1-M5, M7, M11, M12 in
mctl-gitops `deploy/staged/glovo-m1/CROSSWALK.md`, PR #2545) and the independent review
on mctl-api#957 (comment 6740430430). Sources were re-read at mctl-api `a9ca5814` (merge
of #977, contains #968) and re-checked at mctl-api `ceac9ed6` (main after #984; the
cited files are unchanged except `docs/bridge.md:154,176`), mctl-telegram `27c671d2`
(merge of #1259, the facade) and mctl-gitops `4f2d2d76`. Rows marked **(owner)** record
owner decisions of 2026-11-09, listed in full under "Owner decisions" below. Where this
section and older text disagree, this section wins; every older passage it contradicts
has been edited to match.

| # | Finding | Change |
|---|---|---|
| M1 | Identifier families differ: M1a `prn_` principals and tenant names, the bridge and mctl-agents#1044 `tnr_`/`prr_`/`ordr_` (bridge `command.schema.json` patterns; `EnqueueInput` at `internal/bridge/store.go:205-226`) | New §2a: one mapping table (since (b): #988's `glovo.join_refs`), refs minted by mctl-api only, random (not derived), per-tenant `prr_`; raw `prn_`, tenant names and the internal `pord_` never leave mctl-api in a bridge command or a control-workflow input |
| M2 | Refusal set not closed against the facade (`internal/glovo/mctlapi/mctlapi.go:24-47`, `client.go:252-267` at `27c671d2`) | §4 rewritten as a wire mapping table: every 401/403/404/409 `error` value is in the facade's accepted set or is one of the four codes the facade fix mctl-telegram#1264 will consume (**owner**, D4). Internal reasons go to audit and spans only. Golden fixtures: the facade's `wire.golden.json` vendored byte for byte plus one mctl-api fixture per table row. The `ambiguous_tenant` paragraph is rewritten (review row below) |
| M3 | `/resolve` shape: the merged facade decodes exactly `{scope_ref, tenant, expires_at}` with `DisallowUnknownFields` and refuses an empty `scope_ref` (`client.go:112-128`); it sends `X-Mctl-Scope-Ref` on every other call (`client.go:231-233`) | **(owner)** The facade's `/resolve` handling stays unchanged. `/resolve` returns exactly `{scope_ref, tenant, expires_at}`; `principal_ref` and `contract_version` leave `/resolve` (the version stays on `/compatibility`). New §2b specifies `scope_ref`. The old "No `scope_ref`" decision is withdrawn and task 11 no longer asks the facade to drop `X-Mctl-Scope-Ref`. Additive, no contract version bump |
| M4 | `"replayed": true` in the 200 body breaks the `additionalProperties: false` output schemas | Replay is signalled out of band by the response header `Idempotent-Replayed: true`; the body is byte-identical to the original response |
| M5 | Second wire protocol `glovo-read/v1alpha1` (`grr_` ids) next to #968 | **(owner, D1)** Withdrawn. Reads go through the versioned, additive bridge read extension mctl-api#986 (own proposal and digest). `ReadBridge` stays the in-process seam; its transport implementation is the #986 client. History, preview, basket and prepare answer `not_ready` only until #986 lands; P1 acceptance requires all four working, fake-only |
| M7 | Enqueue path: mctl-agents#1044 assumed an HTTP route; #968 exposes only in-process `Store.Enqueue(ctx, tx pgx.Tx, …)` (`internal/bridge/store.go:478-536`) | **(owner, option b; D3)** Enqueue is in process, inside the dispatch transaction, which is owned by mctl-api#985 (M1b/3, child of #954, own digest) together with the dispatch/cancel routes, the control-worker principal and the `aar_` plus revocation re-check. #957 prepare does **not** enqueue a bridge command. #957 keeps the contracts #985 relies on (§6a) and integration checks against #985. No HTTP enqueue route exists in any slice |
| M11 (superseded by decision A, see the (b) amendment and §6b) | DB topology for the shared `pgx.Tx`: bridge on `COMMERCE_DB_URL` else `AUDIT_DB_URL` (`cmd/api/main.go:1019-1021`), work items on `WORK_ITEMS_DB_URL` else `AUDIT_DB_URL` (`main.go:621-633`), M1a on `GLOVO_DB_URL` without fallback | **(owner, D2)** §6b: Glovo never relies on an `AUDIT_DB_URL` fallback; P1 values set `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` explicitly to one physical database; equal URLs are not proof, a test proves the prepare writes and #985's `Enqueue` share one `pgx.Tx`; missing config or an unproven boundary is `not_ready`. Removing #968's generic fallback is mctl-api#987 |
| M12 | #977 answers `invalid_target` for the Glovo resource on `/oauth/authorize` and `/oauth/token` (`internal/api/oauth_handlers.go:214`, `:523`) | Consent-time tenant selection (task 5) depends on #960's `GLOVO_ENABLED` admission lifting that refusal. Until then `invalid_target` is the expected answer, and a test pins it |
| Start | Nothing started `GlovoControlWorkflow` after prepare | **(owner, D5)** §6c: a transactional workflow-start outbox written in the prepare transaction; a separate dispatcher, owned by this slice, starts the workflow after commit |
| Review P2 | AMEND prose contradicts itself (old design line 81, task A1) | Rewritten as one instruction: a missing or unbound human-selected team grant is 403 `ambiguous_tenant`, which is already in the facade's closed set at `27c671d2` |
| C1/C3 alignment | The old error body `{"error","dependency","request_id"}` and "inline DDL in the commerce-store pattern" contradict the joint contract merged in #2541 | **(owner, kept)** Error body `{"error","error_description"}` with fixed text per code; the request id travels in `X-Request-Id`, the dependency name only on `/compatibility`. Join tables are created by the migration entry point (`ApplySchema` pattern, migration role); the runtime role has DML only |

### Owner decisions 2026-11-09

These replace the open items OPEN-1 to OPEN-5 of the first version of this amendment.

- **D1, reads (was OPEN-1): required for P1.** History, preview and basket (reads) and
  prepare (a write that consumes a stored preview) are part of P1 acceptance, fake-only. They use the versioned, additive bridge read
  extension mctl-api#986, a separate issue with its own proposal and digest; there is no
  second `glovo-read` protocol. This slice consumes #986 through `ReadBridge` and answers
  `not_ready` for those four tools only until #986 lands. Raw read payloads never enter
  Temporal history, signals or logs; mctl-agents#1044 carries refs and digests only.
- **D2, database (was OPEN-2; superseded by owner decision A, 2026-11-09 (b), §6b).** Glovo never uses an `AUDIT_DB_URL` fallback. P1 values
  set `COMMERCE_DB_URL` and `WORK_ITEMS_DB_URL` explicitly to one physical database. Equal
  URL strings are not proof: a test proves that the prepare writes and #985's `Enqueue`
  share one `pgx.Tx`. Missing configuration or an unproven boundary answers `not_ready`.
  If `GLOVO_DB_URL` (connections and revocation) is a different database, the
  revoke-after-approval-before-write test must prove there is no TOCTOU window, otherwise
  the write fence stays blocked. Removing #968's generic fallback is a separate,
  compatible change, mctl-api#987.
- **D3, dispatch (was OPEN-3).** The dispatch/cancel routes, the control-worker
  principal, the `aar_` plus revocation re-check and the atomic `bridge.Store.Enqueue`
  move out of this slice into M1b/3, mctl-api#985 (child of #954, own digest). This slice
  keeps `/resolve` and `scope_ref`, preview, prepare, pending `aar_` creation, the
  transactional workflow-start outbox, the client contracts, and integration checks
  against #985. mctl-agents#1044 calls #985's routes.
- **D4, facade codes (was OPEN-4): fix the facade.** mctl-telegram#1264 maps 429 to
  `rate_limited` and 400/422/409 through an explicit table; `fingerprint_changed` lets
  the client refresh the preview. New public codes need a coordinated, versioned M0
  contract and golden-fixture update; raw upstream errors are never shown. The §4 table
  names the codes #1264 consumes.
- **D5, workflow start (was OPEN-5).** Prepare atomically creates the order, the `we_`,
  the pending `aar_` and a workflow-start record. After commit a separate dispatcher
  starts `GlovoControlWorkflow` with a deterministic workflow id, CAS and idempotency,
  and safe retries; it never starts before commit. The dispatcher is owned by this slice
  (§6c), because the record it drains is written by this slice's prepare transaction and
  splitting the writer from the reader would put the start contract in two digests.

## Current state

What exists in the clone (`mctlhq/mctl-api`):

- `internal/api/router.go` `NewRouter`: public groups are the OAuth endpoints, the
  assistant catalog `/api/v1/assistant-catalog` (mctl-api#876) and webhooks. The
  authenticated group applies gates in this order: `supportAudienceGate`, surface
  aggregate limit, `requestTimeout`, `surfacePrincipalGate`, `agentScopeGate`,
  `agentPrincipalGate`, `usageWriterGate`, `evidenceWriterGate`, `securityProviderGate`,
  `registryPublisherGate`, `supportIncidentProducerGate`, `ciPrincipalGate`, the global
  300/min limiter (loopback skipped) and `tenantAuthzShadow`. The `/api/v1` routes
  follow. Nothing is Glovo-specific, and no `/assistants/` route exists.
- `internal/api/support_audience_gate.go`: an allowlist of (method, regexp). A
  support-audience token is refused with 401 `invalid_token` everywhere else, `/mcp`
  included, so routes added later are closed to it by default. This is the pattern the
  join gate follows.
- `internal/auth/oauth_support_token.go`, `internal/auth/oauth_resource.go`
  `ResolveResource`, `internal/auth/oidc.go` (`User.IsSupportAudience`, the
  `tokenAudience`/`supportAudience` flags): audience-scoped access tokens minted by
  mctl-api's own OAuth server. `cmd/api/main.go` reads `OAUTH_ACCESS_TOKEN_AUDIENCE` and
  `OAUTH_SUPPORT_RESOURCE`.
- `internal/workitems/action_approvals.go`: `ActionApprovalIDPrefix = "aar_"`,
  `CreateActionApproval`, `DecideActionApproval`, `ConsumeActionApproval`,
  `ReserveActionApproval`, `SettleActionApproval`, `IntentHash`.
  `internal/workitems/types.go`: `ExecutionIDPrefix = "we_"`. Routes
  `/action-approvals*` are at router.go lines 789-792 and 922-923.
- `internal/api/handlers_action_approvals.go:411`: the `Idempotency-Key` header must
  equal the body `idempotency_key`, otherwise 400. The join API reuses this rule.
- `internal/api/handlers_surface_identity.go` `surfaceRoutes`: the surface allowlist.
  Join routes must not be added there, because surfaces must not reach them.
- `internal/humaninput/contract.go` and `testdata/*.json`: the existing pattern for a
  cross-repo contract mirrored from another repo (`orchestrator/human_input.py`), with
  golden fixtures. `hir_` is clarification only.
- `internal/openapi/openapi.yaml` (embedded, served at `/openapi.yaml`).
- Store tests use `TEST_DATABASE_URL` (57 call sites). `e2e/e2e_test.go` exists.
  `.github/workflows/validate.yml` runs CI.
- `grep -ri glovo` over `*.go`: no matches at the original investigation. Superseded
  (2026-11-09): mctl-api `a9ca5814` contains the #977 Glovo OAuth audience
  (`internal/api/glovo_audience_gate.go`, feature-off) and the #968 command bridge
  (`internal/bridge`, dark). M1a and M1b are still not implemented.

Sibling proposals read (mctl-gitops `agents-state`, all `status: proposed`):

- `mctl-api/proposals/issue-953-...`: Glovo audience `GLOVO_MCP_RESOURCE`,
  `User.IsGlovoAudience()`, `glovo_audience_gate.go` confining a Glovo token to
  `/api/v1/glovo/facade/*`, `internal/glovo` `Resolver.Resolve(ctx, user)`, connections
  `gcn_`, the worker token `MCTL_GLOVO_WORKER_TOKEN`. It adds no tenant selector (its own
  open question).
- `mctl-api/proposals/issue-954-...`: `provider_orders` (`pord_`), routes
  `/api/v1/provider-orders*` behind `PROVIDER_ORDERS_ENABLED`, the `aar_` created and
  consumed by the worker principal, Target
  `provider:fake/connection:<cid>/install:<iid>@<rev>/order:<pord_>`. Superseded
  2026-11-09 (b): #954 is decomposed into #988 (orders, `ordr_`), #989 (`aar_`) and
  #985 (dispatch); `pord_` and `providerorders` are history only.
- `mctl-telegram/proposals/issue-1235-...`: the wire protocol `glovo-facade-mctl-api/v1alpha1`
  under `/api/v1/assistants/glovo/v1alpha1/` with headers `Authorization` (facade
  workload credential), `X-Mctl-Subject-Token`, `X-Mctl-Selected-Tenant`; routes
  `/resolve`, `/connection`, `/connections`, `/orders:list`, `/previews`, `/basket`,
  `/orders:prepare`, `/orders/{order_id}`; plus a `gsc_` scope_ref.
- `mctl-telegram/proposals/issue-1227-...`: the seven-tool table (inputs and outputs) and
  the scopes `glovo:read` and `glovo:basket:prepare`.

The mismatch: #1235 expects a facade-credential route family. #953 serves a user-token
route family at a different prefix. #954 serves owner and worker routes that the facade
must not call (confused deputy). No component owns the mapping between them.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` (admins, karabu, labs, namax66): no `mctl-api` service
  directory and no Glovo service. mctl-api's deployed values are not in this checkout,
  so its current env (for example whether `OAUTH_SUPPORT_RESOURCE` is set) was not
  observed.
- `services/labs/mctl-telegram/values.yaml`: `PUBLIC_BASE_URL` and `OAUTH_ISSUER_URL`
  are `https://tg.mctl.ai`. The join routes therefore must not live on that host's path
  space.
- `grep -ril glovo services/ tenants/`: no matches. Nothing Glovo is deployed.
- mctl MCP tools: not called. The gitops checkout was enough for the above, and
  mctl-api's own deployed config remains unobserved (see Open questions in
  requirements.md).

## Proposed solution

### AMEND 2026-11-08 — M0 closed refusal + DB/approval atomicity proof

A missing or unbound human-selected team grant is 403 `ambiguous_tenant`, also when exactly one team would be eligible. `ambiguous_tenant` is already a member of the facade's closed refusal set (mctl-telegram `27c671d2`, `internal/glovo/mctlapi/mctlapi.go:27,43`), so no new public code is introduced. A mismatched `X-Mctl-Selected-Tenant` is 403 `not_authorized` on the wire, with the internal reason `tenant_mismatch` in audit only (§4). The shared fixtures pin both.

The `Prepare` sequence is not atomically satisfied merely by invoking existing `workitems.CreateActionApproval` and `ExecutionByID` while holding a separate `glovojoin` transaction. Design a concrete shared DB pool and `pgx.Tx`-aware WorkItem/execution/`aar_` APIs **or** an idempotent compensating state machine with separately validated transitions; prove failure injection on each boundary, no orphan approved receipt, no duplicate pord_/we_/aar_, and zero fake-provider writes. Any fallback to partial commit must explicitly remain `not_ready`/blocked until reconciled. The legacy #954 source uses `ReserveActionApprovalTx` only for reserve, not pending creation; don't assume a `Prepare` helper exists or can span databases. Amendment 2026-11-09 names the shared pool and the tx-aware APIs in §6b; the compensating state machine stays the allowed fallback.



### 1. Decision: one canonical route family, owned by mctl-api

Keep the prefix #1235 froze, `/api/v1/assistants/glovo/v1alpha1/`. It is versioned, does
not collide with `/mcp`, `/api/v1/glovo/*` or `/api/v1/provider-orders/*`, and it is what
the facade already targets. Under it mctl-api serves thin join handlers that call the M1a
and M1b packages in process (`internal/glovo`; since (b) `internal/glovo/orders` of #988
and the #989 `workitems` Glovo methods instead of `internal/providerorders`). The facade
never calls `/api/v1/glovo/facade/*` or `/api/v1/provider-orders/*`. Those stay
human/owner and worker routes. The M1a Glovo-audience gate keeps confining a bare Glovo
token to `/api/v1/glovo/facade/*`, which this join API does not need. Whether M1a still
needs those routes for a non-facade client is M1a's call.

### 2. Identity flow (canonical, amends #1235)

```
MCP client --Glovo-aud token--> facade (verifies via JWKS, as in #1235)
facade --Authorization: Bearer <MCTL_GLOVO_FACADE_TOKEN>
       --X-Mctl-Subject-Token: <same user access token>
       --[X-Mctl-Selected-Tenant: <echo of mctl_tenant claim>]
       --traceparent, X-Request-Id
     --> mctl-api /api/v1/assistants/glovo/v1alpha1/...
         glovoJoinGate -> verify subject -> tenant claim -> M1a Resolve
         -> (every route except /resolve and /compatibility) validate X-Mctl-Scope-Ref (§2b)
         -> handler
```

- **Facade workload identity.** A new machine principal `NewGlovoFacadeUser()` in
  `internal/auth/oidc.go`, recognised by a constant-time compare with
  `MCTL_GLOVO_FACADE_TOKEN`. It follows the evidence-writer pattern and is refused at
  startup if the value equals any other machine token (service, evidence, usage, M1a
  worker). It carries no groups and no tenant.
- **`internal/api/glovo_join_gate.go` `glovoJoinGate`**, mounted directly after
  `supportAudienceGate`. Two rules: (a) a facade principal reaches only
  `^/api/v1/assistants/glovo/v1alpha1/` and gets 401 everywhere else, `/mcp` included;
  (b) a non-facade principal on that prefix gets 401 `not_authorized` (internal reason
  `not_facade_identity`, §4). Because it
  runs before `surfacePrincipalGate` and `agentPrincipalGate`, no relay or delegation
  header can turn another principal into the facade. Join routes are not added to
  `surfaceRoutes`, `supportAudienceRoutes` or any agent scope.
- **Subject re-verification.** `glovojoin.SubjectVerifier` calls the same local-OAuth
  verification path as `AuthMiddleware` (`internal/auth/provider_localoauth.go`) on
  `X-Mctl-Subject-Token`. It checks: signature, `iss == BaseURL`, `aud` containing
  `GLOVO_MCP_RESOURCE` and no API or support audience (precedence as M1a defines it,
  fail closed), `exp`, revocation by `jti` or token family, and a principal-backed
  `sub`. The raw header is deleted from the request after verification. Only
  `sha256(token)` reaches the audit record and the span. The subject token is never
  accepted in a query string or body.
- **Server-bound selected tenant.** M1e extends `/oauth/consent`: when the resource is
  `GLOVO_MCP_RESOURCE`, the consent page lists the M1a-eligible tenants (membership ∩
  pilot allowlist ∩ current install), with nothing preselected. The human must pick one.
  The choice is stored on the authorization code and the refresh-token family and minted
  as the claim `mctl_tenant`. On every join call the tenant is that verified claim. The
  `X-Mctl-Selected-Tenant` header is optional, compared and never read as input. Then
  `glovo.Resolver.Resolve(ctx, subject)` runs and the claim tenant must be among its
  eligible set, otherwise the M1a refusal code is returned. There is no default tenant,
  no sole-membership fallback and no `labs`.
- **`scope_ref` (amended 2026-11-09, owner).** The earlier "no `scope_ref`" decision is
  withdrawn: the merged facade requires it (`client.go:124`, `client.go:133`). It is
  specified in §2b as a reference, never as authority: every call still re-verifies the
  subject and re-derives tenant and owner, exactly as above.

Why forward the user token instead of having the facade assert the subject: a stolen
facade credential alone cannot act for any user, and a stolen user token cannot reach the
join routes without the facade credential (TM3 in #1235).

### 2a. Opaque reference mapping (M1, amended 2026-11-09)

- Raw identifiers stay inside mctl-api: tenant names, `prn_` principal ids and #988's
  internal `pord_` order key never appear in a bridge command projection or in a `GlovoControlInput`
  (mctl-agents#1044). The M1a `gcn_` connection and `gin_` install ids are random ULIDs
  that carry no personal data and match the bridge patterns, so they pass through
  unchanged.
- mctl-api mints the opaque refs and keeps the only mapping, in #988's
  `glovo.join_refs(kind, ref, tenant, principal_id, subject_id, created_at)`, through
  #988 `MintJoinRefTx` (amended (b): #988 is the single owner of the table and its
  minting helper; this slice calls it and creates no join-ref table of its own):

  | Kind | Ref | One per | Subject |
  |---|---|---|---|
  | `tenant` | `tnr_` | tenant | tenant name |
  | `principal` | `prr_` | (tenant, principal) | `prn_`; the same human in two tenants gets two unrelated refs |
  | `order` | `ordr_` | #988 order | the #988 order row's own `order_ref` (#988's `pord_` primary key stays unexported) |

- Format: prefix plus 26 base62 characters from `crypto/rand` (the bridge's `randAlnum`),
  inside the bridge patterns `^(tnr|prr|ordr)_[A-Za-z0-9]{16,40}$`. Refs are random, never
  a hash of the raw id, so enumerating tenant names or ULIDs cannot reverse them.
  `UNIQUE(kind, ref)` and `UNIQUE(kind, tenant, subject_id)`; minted lazily with
  `INSERT … ON CONFLICT DO NOTHING` plus `SELECT` inside the transaction that first needs
  them; never updated, reused or deleted while an order references them.
- `EnqueueInput` gets the raw `Tenant` and `OwnerPrincipalID` (private columns,
  `docs/bridge.md` "Private (Postgres only)") and the mapped `TenantRef`, `PrincipalRef`,
  `OrderRef`, with `ConnectionRef` = `gcn_`.
- A ref is resolved only inside mctl-api. Any call that names a ref re-derives tenant and
  owner from the verified caller and requires the mapping row to match; otherwise the
  answer is the not-found code of §4.

### 2b. `scope_ref` (M3, owner decision 2026-11-09)

The merged facade is not changed. It calls `POST /resolve` before every tool call and
sends the returned value as `X-Mctl-Scope-Ref` on the follow-up call.

- **Shape.** `/resolve` returns exactly `{scope_ref, tenant, expires_at}`. `scope_ref` is
  `gsc_` plus 32 base64url characters from `crypto/rand` (192 bits, above the 128-bit
  floor); `tenant` is the verified claim tenant; `expires_at` is RFC 3339 UTC.
- **Binding.** The ref is bound to the subject principal (`prn_`), the claim tenant, the
  M1a install id and install revision, and the subject token's refresh-token family, so
  revoking the grant revokes every ref minted from it.
- **TTL.** `expires_at = min(now + 5 min, subject token exp)`. The facade resolves per
  tool call, so a short TTL costs nothing.
- **Storage.** Server-side only, as `sha256(ref)`, in `glovo_join_scope_refs(ref_hash
  PRIMARY KEY, principal_id, tenant, install_id, install_revision, grant_family_id,
  created_at, expires_at)`. The plaintext is returned once and never stored, logged or put
  in a span; logs and audit carry the hash prefix only. Expired rows are deleted by a
  bounded sweep and are refused on read regardless of the sweep.
- **Validation on every use.** Header only (never query or body), stripped after use. The
  row must exist and be unexpired; its principal, tenant and grant family must equal those
  of the freshly verified subject token; its install revision must still be current in
  M1a, else 403 `stale_install`. Every other failure is 403 `not_authorized` with no
  distinction between unknown, expired and foreign on the wire (§4).
- **Reference, not authority.** The handler never reads tenant or owner from the row. It
  uses the values it re-derived from the verified subject token and the M1a resolver; the
  row only has to agree with them.
- **Rate.** `/resolve` counts against the per-subject limit (§10).
- **Compatibility.** The shape is exactly what `27c671d2` decodes, so the change is
  additive and `glovo-facade-mctl-api/v1alpha1` keeps its version.

### 3. Route matrix (frozen, v1alpha1)

All paths are relative to `/api/v1/assistants/glovo/v1alpha1`. No query strings are used.
Scopes are checked against the subject token.

| MCP tool | Verb + path | Request body | 200 body (= tool output) | Scope | Backing call | Source owner |
|---|---|---|---|---|---|---|
| (preflight) | `POST /resolve` | `{}` | exactly `{scope_ref, tenant, expires_at}` (amended 2026-11-09; the facade decodes with `DisallowUnknownFields`) | any Glovo scope | `glovo.Resolver.Resolve`, then mint a `gsc_` (§2b) | M1a #953 / M1e |
| `glovo_auth_status` | `GET /connection` | none | `{connection_state, connection_id?, provider_account_label?, expires_at?}` | `glovo:read` | `glovo.Connections.Current(tenant, principal)` | M1a #953 |
| `glovo_connect_account` | `POST /connections` | `{idempotency_key}` | `{connection_id, state:"pending_handoff", handoff_url, expires_at}` | `glovo:basket:prepare` | `glovo.Connections.Create` (synthetic handoff URL) | M1a #953 |
| `glovo_get_order_history` | `POST /orders:list` | `{limit<=20, cursor?}` | `{orders:[...], next_cursor?}` | `glovo:read` | `ReadBridge.History` | M1e (seam), mctl-api#986 (transport), mctl-telegram#1262 (fake data) |
| `glovo_preview_reorder` | `POST /previews` | `{order_ref}` (wire name unchanged; value is the #1059 `pho_` history-order ref) | `{preview_id, items, unavailable_items, fingerprint, expires_at}` | `glovo:read` | `ReadBridge.Preview` plus a `glovo_join_previews` row; `fingerprint` computed by mctl-api over the #1059 approval basket | M1e |
| `glovo_get_basket` | `GET /basket` | none | `{store_name?, items, totals_label, fingerprint}` | `glovo:read` | `ReadBridge.Basket`; `fingerprint` computed by mctl-api over the #1059 approval basket | M1e / mctl-api#986 / mctl-telegram#1262 |
| `glovo_prepare_order` | `POST /orders:prepare` | `{preview_id, idempotency_key}` | `{order_id, fingerprint, consent_request_id, expires_at}` | `glovo:basket:prepare` | #988 order (`ordr_`) + `we_` + #989 `CreateGlovoApprovalTx` pending `aar_`, zero provider writes; `order_id` is the `ordr_` | #988, #989 |
| `glovo_order_status` | `GET /orders/{order_id}` | none | `{state, outcome, handoff_url?}` | `glovo:read` | #988 owner-path `Get` plus #989 `GlovoApprovalStatus` | #988, #989 |
| (launch) | `GET /compatibility` | none | `{contract_version, contract_digest, api_version, dependencies:{connection_registry, provider_orders, read_bridge, control_worker, provider_worker}, deploy_ready}` | facade identity, no subject needed | `glovojoin.Readiness` | M1e |

`consent_request_id` is the `aar_` id. The human decides it only through the existing
owner decision route (`POST /api/v1/action-approvals/{id}/decision`), which the facade
cannot reach. No join route decides, consumes, reserves or settles an `aar_`, and none
accepts an `hir_`.

### 4. Refusal and status mapping (closed enum, in the contract; amended 2026-11-09)

The wire `error` value on 401, 403, 404 and 409 is a member of the set the merged facade
accepts (`upstreamCodes`, mctl-telegram `27c671d2` `internal/glovo/mctlapi/mctlapi.go:42-47`),
except the rows marked *exception*. At `27c671d2` the facade shows those as
`upstream_invalid` (fail closed). Owner decision D4: the facade fix mctl-telegram#1264
consumes exactly these four codes: 409 `fingerprint_changed` (the client refreshes the
preview), 409 `idempotency_key_reused`, 400 `invalid_arguments` and 429 `rate_limited`
(with `Retry-After`). This API sends no 422. Adding a fifth public code needs a
coordinated, versioned M0 contract and golden-fixture update in both repositories. The
internal reason never reaches the wire; it is recorded in the audit event and the span
attribute `glovo.refusal_reason`.

| Condition | Internal reason (audit only) | HTTP | Wire `error` |
|---|---|---|---|
| Bearer is not the facade workload identity | `not_facade_identity` | 401 | `not_authorized` |
| Subject token missing, invalid, expired, revoked, wrong `iss`/`aud` | `subject_token_invalid` | 401 (+ `WWW-Authenticate`) | `not_authorized` |
| `X-Mctl-Scope-Ref` missing, unknown, expired, revoked, or bound to another principal, tenant or grant family (§2b) | `scope_ref_invalid` | 403 | `not_authorized` |
| `scope_ref` bound to an install revision that is no longer current | `scope_ref_stale` | 403 | `stale_install` |
| Subject token lacks the route's scope | `insufficient_scope` | 403 | `scope_unsupported` |
| No human-selected team grant (also with one eligible team) | `tenant_selection_missing` | 403 | `ambiguous_tenant` |
| `X-Mctl-Selected-Tenant` present and different from the verified claim | `tenant_mismatch` | 403 | `not_authorized` |
| M1a resolver refusal | the M1a code | 403 | unchanged: `no_tenant`, `ambiguous_tenant`, `not_in_pilot`, `scope_unsupported`, `not_authorized`, `no_install`, `stale_install`, `connection_revoked` |
| No connection for this owner, or a `gcn_` that is foreign or absent | `connection_not_found` | 404 | `no_connection` |
| Connection exists but is not active | `connection_not_active` | 409 | `connection_expired` or `connection_revoked`, by M1a state |
| Preview or order absent, foreign (owner or tenant), or preview expired | `preview_not_found`, `order_not_found`, `preview_expired` | 404 | `not_found` |
| Basket fingerprint changed since the preview | `fingerprint_changed` | 409 | *exception* `fingerprint_changed` |
| Same idempotency key, different body | `idempotency_key_reused` | 409 | *exception* `idempotency_key_reused` |
| Schema violation, unknown or duplicate field, header/body key mismatch | `invalid_request` | 400 | *exception* `invalid_arguments` |
| Rate limit | `rate_limited` | 429 (+ `Retry-After`) | *exception* `rate_limited` |
| Dependency not configured, or a store/bridge read failed (never mapped to empty) | `not_ready:<dependency>`, `dependency_unavailable:<dependency>` | 503 | `not_ready`, `dependency_unavailable` (the facade maps every 5xx by status to `upstream_unavailable`) |

The error body is `{"error": code, "error_description": <fixed text per code>}` (joint
contract C1, owner decision kept 2026-11-09). It carries no id, no dependency name and no
text derived from input. The request id is returned in `X-Request-Id`; dependency
readiness is reported only by `GET /compatibility`. Unknown and foreign ids get the same
answer, so the table gives no existence oracle.

### 5. Read bridge protocol

**Amended 2026-11-09 (M5, owner D1).** The `glovo-read/v1alpha1` envelope and `grr_`
ids below are withdrawn as a wire protocol. `ReadBridge` remains an in-process Go
interface; its request and result types are Go structs with no version string and no id
family of their own. Implementations: `NotReadyBridge` (default), `FixtureBridge` (build
tag only) and the client of the bridge read extension mctl-api#986, which carries the
versioned, typed read results. Until #986 lands, history, preview and basket (and
therefore prepare) answer `not_ready`; P1 acceptance requires them working. The struct
sketch below is kept for the field list only.

`internal/glovojoin/bridge.go`:

```go
type ReadBridge interface {
    Read(ctx context.Context, req GlovoReadRequest) (GlovoReadResult, error)
}
// GlovoReadRequest{RequestID (in-process correlation only, no wire id), Kind history|preview|basket,
//   Tenant, PrincipalRef (opaque hash, not principal id), ConnectionID, InstallID, InstallRevision,
//   Args (bounded), Deadline, TraceParent}
// GlovoReadResult{RequestID, Kind, ConnectionID, InstallRevision, Payload (schema per kind), Synthetic: true}
```

- Amended (b): the result carries no binding refs and the handler checks no echo.
  #986 `FetchReadResult` takes every binding from the stored command row and checks
  tenant, owner, `glovo:read`, expiry, connection and install revision. The handler
  checks only that the kind and the #1059 schema version are the ones it asked for and
  that `Payload` validates against the kind's #1059 schema. Anything else becomes
  `dependency_unavailable`. The handler computes the approval-basket fingerprint itself
  from the #1059 approval-basket projection of the preview or basket payload.
- Implementations: `NotReadyBridge` (the default: every call gets `not_ready`,
  `dependency: read_bridge`); `FixtureBridge` (tests and harness only, built under the
  `glovojoin_fixture` tag so it cannot ship in the release image); and later
  the mctl-api#986 read-extension client once #986 is approved and merged (owner D1).
  The transport decision of mctl-agents#1043 is superseded by #968 (owner,
  2026-11-09). Raw read payloads are never put into a bridge command, a Temporal
  input, signal or log. mctl-api assumes no cross-namespace Temporal Activity.
- Previews are persisted in mctl-api so that prepare binds to what the user saw. The
  table is `glovo_join_previews(id 'gpv_'+128-bit, tenant, principal_id, connection_id,
  install_id, install_revision, fingerprint, payload_hash, created_at, expires_at <=
  15m)`. Amended 2026-11-09: its DDL runs in the migration entry point under the
  migration role (joint contract C3), not inline at runtime.

### 6. Prepare path (zero writes)

`POST /orders:prepare` runs as follows. Load the `gpv_` row by (id, tenant, principal),
otherwise 404. Check it is unexpired, otherwise 409. Re-check that the connection is
active and the install revision is current through #959 `LockOwnerShared` and
`LiveConnectionTx` on the §6b transaction (L1, L2 shared). Then, in that one
transaction (amended (b)): create the #988 order (`Create` + `Finalize`, which binds the
connection and the approval-basket fingerprint; its `order_ref` is the `ordr_` returned
as `order_id`), a `we_` owned by the principal, the pending `aar_` through #989
`CreateGlovoApprovalTx` (which calls #988 `BindApproval`; its `IntentHash` is #989
`GlovoIntent` over the binding and the fingerprint), and the workflow-start record of
§6c. No provider effect row, no bridge command and no
dispatch is created. Idempotency is
#988's idempotent create plus #989's `(requested_by, idempotency_key)`, and a replay with a different
fingerprint gets 409 `idempotency_key_reused`. A replay with the same key and body returns
the original body byte for byte with the header `Idempotent-Replayed: true` (M4); the
body never gains a `replayed` field. The transaction is the one named in §6b. If #988 or #989 does not expose the verified tx-aware methods above, `Readiness` reports `provider_orders: not_ready` and the route returns 503. A nominal `Prepare` method without tested cross-store atomicity and crash recovery does not satisfy readiness.

### 6a. Enqueue and dispatch (M7, owner option b; owned by mctl-api#985)

- mctl-api is the only writer of `bridge_commands`, always in process with
  `bridge.Store.Enqueue(ctx, tx, EnqueueInput{…})` inside the transaction of the order
  change that motivates the command. No slice adds an HTTP route that enqueues a command,
  and no route accepts a command id, a command kind or a payload from a caller.
- **This slice enqueues nothing.** Prepare writes the order, the `we_`, the pending `aar_`
  and the workflow-start record (§6c) and no bridge command.
- Dispatch and cancel of an approved order belong to mctl-api#985 (M1b/3): its routes, the
  control-worker principal, the `aar_` reserve plus revocation re-check, the order
  transition and `Enqueue`, in one transaction. `cmd_` ids come from `Enqueue`
  (`store.go:490`), idempotent on `(tenant, execution_id, operation_key)`.
- What this slice guarantees to #985, and checks in integration tests against #985's
  merged code: the order row carries the `ordr_`/`tnr_`/`prr_` refs of §2a, the bound
  fingerprint, the pending `aar_` and the stored `GlovoControlWorkflow` id and run id
  (the `WorkflowID`/`RunID` that `EnqueueInput` needs for `bridge-result`); every write
  #985 makes can run on the §6b transaction boundary.

### 6b. One database, one transaction boundary, one lock order (owner decision A)

Rewritten 2026-11-09 (b); this replaces the D2 text. Decision A supersedes D2.

- **One physical database.** Every Glovo store lives in one Postgres database: the
  bridge (`bridge_commands`, `bridge_read_results`), the work items and `aar_`
  (`action_approval_requests`, `glovo.approval_bindings`), the #988 order tables and
  `glovo.join_refs`, this slice's join tables, and the #959 `glovo.glovo_installs` /
  `glovo.glovo_connections`.
- **Explicit URLs, no fallback.** `GLOVO_DB_URL`, `COMMERCE_DB_URL` and
  `WORK_ITEMS_DB_URL` must each be set explicitly while Glovo is enabled. None falls back
  to `AUDIT_DB_URL` or to another of the three. A missing value is `provider_orders:
  not_ready`. Removing #968's generic bridge fallback (`main.go:1019-1021`) is
  mctl-api#987.
- **Proof of one database, not URL equality.** #985 `control.ProveOneDatabase` writes a
  random nonce through the bridge pool and reads it back through the work-items and Glovo
  pools, checks `pg_is_in_recovery() = false`, finds every participating table with
  `to_regclass` and checks the grants (#985 design §4). Any failure keeps every Glovo
  write path `not_ready` for the life of the process.
- **One transaction.** Every write of the prepare transaction (join tables, #988 order
  and join refs, the `we_`, the pending `aar_`, the workflow-start record) and every write
  of #985's dispatch transaction (including `bridge_commands`) runs on one `pgx.Tx`
  opened from `bridge.Store.Pool()` (`store.go:414`). The connection read is on the same
  transaction (#959 `LiveConnectionTx`), so revocation is no longer a separate-database
  TOCTOU case. No participant opens its own transaction inside the shared one (the
  work-item store has only its private `withTx`, `internal/workitems/store.go:266`; the
  tx-aware variants are #989's `...Tx` methods). CI proves the boundary (#985 T20):
  prepare writes plus dispatch in one `pgx.Tx`, a failure injected after the last
  statement, nothing committed on either side.
- **Schemas and roles.** Glovo tables live in the Postgres schema `glovo`, owned by the
  migration role and created only through each slice's `ApplySchema` entry point. The
  runtime roles get DML grants only, as in #959's role table: the Glovo runtime role
  has DML on its own tables and EXECUTE on `bridge_cancel_open_for_connections`; the
  bridge and work-items roles have USAGE on `glovo` and SELECT on installs and
  connections, never UPDATE or DELETE.

#### Canonical lock order (the only copy; every Glovo slice references it)

| Level | Lock | Mode |
|---|---|---|
| L1 | advisory key `glovo-install/v1\|<tenant>` (#959) | shared for dispatch, cancel, permit, prepare, connect and connection revoke; exclusive for `Install`, `RevokeInstall`, `Reinstall` |
| L2 | advisory key `glovo-owner/v1\|<tenant>\|<principal>` (#959) | shared for prepare, dispatch, cancel and permit; exclusive for #959 connection writes (including revoke) |
| L3 | #988 order row | `FOR UPDATE` |
| L4 | #989 `aar_` row | `FOR UPDATE` |
| L5 | `bridge_commands` rows | `FOR UPDATE`, `ORDER BY command_id` |
| L6 | #959 connection row | read under L2, no row lock |

A path may skip levels but never takes a lower level after a higher one.

| Path | Levels taken, in order |
|---|---|
| #957 prepare | L1 sh, L2 sh, L6 read, L3 (new order), L4 (new `aar_`) |
| #985 dispatch / cancel | L1 sh, L2 sh, L6 read, L3, L4, L5 |
| Bridge permit | `WriteFence.PreLock` (#989): L1 sh, L2 sh, L3, L4; then `lockOwned`: L5; then `Check` |
| #989 owner decision | L4 only |
| #959 revokers (`Revoke`, `RevokeForMembership`, `RevokeInstall`, `Reinstall`) | L1 (sh, or ex for install changes), L2 ex, connection rows, then the revocation hook `bridge_cancel_open_for_connections`: L5 `ORDER BY command_id`, same transaction |
| Provider claim, result, expiry | L5 only |
| #989 sweeper (replaces an outcome recorder) | L4 `SKIP LOCKED`, then a plain read of the terminal command (no L5) |

Deterministic tests for the races are #985 T-series and #989 T21; this slice adds the
prepare-versus-revoke case (tasks.md T12).

### 6c. Workflow-start outbox (owner D5, owned by this slice)

- Prepare writes `glovo_control_starts(order_id, workflow_id, input_digest, state
  pending|started|failed_terminal, attempts, next_attempt_at, started_run_id)` in the
  prepare transaction. `workflow_id` is deterministic from the opaque refs
  (`asst-glovo-<tnr_>-<prr_>-<gin_>-<ordr_>`, the derivation mctl-agents#1044
  re-checks); the input is `GlovoControlInput` with refs, `approval_ref`, fingerprint
  and digests only, never a read payload.
- After commit, a separate dispatcher in mctl-api claims due rows (`FOR UPDATE SKIP
  LOCKED`), starts the workflow with that id and the id-reuse policy "reject duplicate",
  and CAS-updates the row to `started` with the run id. "Already started" with the same id
  is success. Transient errors back off with a bounded attempt count; it never starts a
  workflow for an uncommitted order and never invents an id.
- The dispatcher runs only when `GLOVO_CONTROL_START_ENABLED=true` (default off) and a
  Temporal client for the control namespace is configured; that client is gated by the
  Temporal security path (crosswalk §4, nodes A-I). Until then rows stay `pending` and
  `/compatibility` reports `control_worker: not_ready`.

### 7. Contract package (shared with mctl-telegram)

- `internal/glovojoin/contract/glovo-facade-mctl-api.v1alpha1.json`: the version, the
  route matrix, the request and response JSON Schemas (draft 2020-12,
  `additionalProperties: false`), the refusal table, the idempotency rules, the rate
  limits, the timeouts (5 s), the OAuth resource metadata expectations (`resource`,
  `scopes_supported`, `bearer_methods_supported: ["header"]`) and `dependencies` version
  gates (minimum M1a and M1b schema versions, bridge `bridge.mctl.ai/v1alpha1` schema
  digests as vendored at `a9ca5814`; amended 2026-11-09).
- `contract.go` (`//go:embed`) and `contract_test.go`, which pins `Digest` (sha256 of
  the file). Changing the file without bumping the digest fails the test, and so does
  bumping the digest without bumping the version.
- `testdata/v1alpha1/<route>/<case>.json`: golden {request headers (token placeholders),
  body, expected status, expected body} cases, one per row of the §4 table (amended
  2026-11-09). `testdata/facade/wire.golden.json` is the facade's request fixture,
  vendored byte for byte from mctl-telegram `27c671d2`
  `internal/glovo/mctlapi/testdata/wire.golden.json` (sha256
  `5acdde3ae3fd92bf81b7f91d8f52b4767627de3f1c080058dda6dea2db295f0a`) with a `PROVENANCE`
  file; the harness replays every operation in it against the real handlers. `testdata/glovo-mcp-tools.json` is a
  pinned copy of the M0 tool schema with its digest. A test asserts that every 200
  response schema equals the matching tool `output_schema`.
- Cross-repo: mctl-telegram vendors the same contract file and fixtures and asserts the
  same digest in `internal/glovo/mctlapi/wire_test.go` (in the facade follow-up for
  crosswalk M13; the merged facade itself is not changed by this slice). Each repo's CI fails on a digest
  mismatch with the other side's pinned value. The pin is updated by PR in both repos;
  a drift in either fails.

### 8. Harness against real handlers

`internal/glovojoin/harness_test.go` (requires `TEST_DATABASE_URL`, build tag
`glovojoin_fixture`) builds the real `api.NewRouter` with the real `workitems.Store`, the
M1a `glovo` store, the #988 order store and the #989 `aar_` methods (amended (b)), a test OAuth server that mints real
local-OAuth Glovo tokens, and `FixtureBridge`. It then replays every golden fixture and
the negative matrix (tasks.md T6). An exported `cmd/glovo-join-harness` (fixture tag)
serves the same stack on a local port so the mctl-telegram facade's integration test can
target real mctl-api handlers instead of `fakeapi`.

### 9. Readiness and launch matrix

`glovojoin.Readiness` probes each dependency: the M1a store is configured and has its
schema version, the #988 and #989 stores are present and #985 `ProveOneDatabase` passed
(amended (b)), the bridge is not
`NotReadyBridge`, and the control and provider worker heartbeats are seen through the
bridge. `docs/glovo-join.md` holds the launch compatibility matrix (facade image ×
mctl-api release × control worker × provider worker × gitops revision × contract
digest). `deploy_ready` stays false in this proposal's scope.

### 10. Rate limits and tracing

Join routes get their own `httprate` group: per subject principal 60/min, writes
10/min, and a facade aggregate of 600/min (keyed `glovo-facade-total`). The global
300/min limiter keys on the facade identity, so it is skipped for this prefix in favour
of the per-subject limiter, the same reasoning `agentAggregateLimit` uses. `traceparent`
is honoured by the existing telemetry middleware. Span attributes are route, refusal
code, tenant and request_id.

## Alternatives

1. **Facade calls the M1a `/api/v1/glovo/facade/*` and M1b `/api/v1/provider-orders/*`
   routes directly.** Rejected. M1b's routes are owner and worker routes, so letting the
   facade hold that privilege is a confused deputy, and history/basket have no owner
   there at all.
2. **Overload M1a's connection registry with history, preview and order adapters.**
   Rejected by the issue as unapproved scope expansion of #953. It would also tie M1a's
   review to M1b.
3. **Trust `X-Mctl-Selected-Tenant` (or have the facade assert the subject) with only the
   workload credential.** Rejected. It makes the tenant caller-controlled and makes a
   facade compromise a full user compromise. The issue forbids a raw JWT or header
   becoming a trusted tenant string.
4. **RFC 8693 token exchange (facade swaps the user token for a mctl-api join token).**
   Deferred, not rejected. It is cleaner but needs a token-exchange grant mctl-api does
   not have yet. The `SubjectVerifier` interface leaves room for it in v1alpha2.

## Platform impact

- **Migrations:** the tables `glovo_join_previews` and `glovo_join_scope_refs` (the
  join-ref table is #988's `glovo.join_refs`), created by the migration entry point under the migration role
  (amended 2026-11-09; the runtime role gets DML only), and one column on the OAuth authorization-code and
  refresh-family store for the selected tenant (nullable, ignored for non-Glovo
  resources). Both are additive.
- **Backward compatibility:** everything is behind `GLOVO_JOIN_ENABLED` (default off), so
  the routes are 404 when off. Consent for non-Glovo resources is unchanged. No existing
  gate's behaviour changes for existing principals. `glovoJoinGate` only refuses on the
  new prefix or for the new principal.
- **MCP tool count:** unchanged. No tool is added to `internal/mcp/server.go`, so the
  `server_test.go` expectation stays the same.
- **Resources:** negligible. One extra JWT verification per join call and one Postgres
  table.
- **Risks and mitigations:**
  - Gate ordering bug lets another principal reach join routes. Mitigation: router test
    over every principal kind × every join route, plus a facade × non-join routes test.
  - Token leak through logs. Mitigation: the header is stripped after verification, only
    the hash is recorded, and a log-capture test greps for the token.
  - Cross-repo drift. Mitigation: a digest pinned on both sides plus golden fixtures.
  - Premature launch claim. Mitigation: `deploy_ready` is false until all dependencies
    are ready, and the docs require M1a and M1b to be merged first.
  - The #988/#989 tx-aware API differs from what §6 assumes. Mitigation: the
    join layer depends on a narrow interface `glovojoin.Orders`, and a mismatch shows up
    as `not_ready` rather than a broken route.
