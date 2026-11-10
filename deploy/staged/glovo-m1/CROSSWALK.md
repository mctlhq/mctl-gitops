# Glovo M1 contract and deployment readiness crosswalk

Status: **informational, not an approval record.** Nothing in this file
approves a proposal digest, a release, a deployment, a Temporal authorization
change or P1/P2 activation. Each of those keeps its own gate (section 5).

Purpose: one place that lines up the M1 slices, the contracts between them,
the places where they disagree, and the order of approvals that leads to P1.
It replaces nothing; the proposals and `docs/bridge.md` stay canonical.

## Pinned sources

Every citation below refers to one of these exact revisions. `UNVERIFIED`
marks anything not read at that revision.

| Key | Repository | Revision | What |
| --- | --- | --- | --- |
| G | mctl-gitops | `f96409351e0fcefab16d5d268b9fc15f29081412` (merge of #2541) | proposals, staged package, runbooks |
| A | mctl-api | `a9ca5814` (merge of #977) | `docs/bridge.md`, `internal/bridge`, `internal/api`, `internal/auth` |
| T | mctl-telegram | `27c671d2` (merge of #1259) | facade `internal/glovo/mctlapi` |

Proposal paths (G), all `status: proposed`:

| Issue | Path under `platform-gitops/agents-state/` | `content_hash` at G |
| --- | --- | --- |
| mctl-api#959 | `mctl-api/proposals/issue-959-feat-glovo-m1a-2-tenant-principal-connec/` | `sha256:8874e278…` |
| mctl-api#960 | `mctl-api/proposals/issue-960-feat-glovo-m1a-3-explicit-human-selected/` | `sha256:47b42c3c…` |
| mctl-api#961 | `mctl-api/proposals/issue-961-feat-glovo-m1a-4-synthetic-connection-ha/` | `sha256:a182ea76…` |
| mctl-api#957 | `mctl-api/proposals/issue-957-feat-glovo-m1e-canonical-facade-to-mctl/` | `sha256:7164840c…` |
| mctl-agents#1044 | `mctl-agents/proposals/issue-1044-feat-assistants-m1-trusted-glovo-control/` | `sha256:ccbdc11a…` |
| mctl-telegram#1262 | `mctl-telegram/proposals/issue-1262-feat-glovo-re-platform-fake-provider-wor/` | `sha256:f3025729…` |

A hash listed here is what was on disk at G. It is not a statement that the
owner approved it.

## 1. Component map

| Component | Repo | State at the pinned revisions | Talks to |
| --- | --- | --- | --- |
| Facade (`glovo.mctl.ai/mcp`, MCP over OAuth) | mctl-telegram | merged (T, tg#1259); not deployed | mctl-api `/api/v1/glovo/facade/*` over HTTPS with a Glovo-audience token |
| Glovo OAuth audience and resource gate | mctl-api | merged, feature-off (A, #977); `glovoAudienceRoutes` empty (`internal/api/glovo_audience_gate.go:26-29`) | facade, OAuth clients |
| M1a store: installs, connections, allowlist, audit | mctl-api | proposed: #959 (store), #960 (team grants, allowlist routes, kill switch), #961 (handoff refs, worker identity, facade routes); joint contract in each design (G, 959 `design.md:32-36`) | facade routes, control worker |
| M1e join (facade routes, previews, prepare) | mctl-api | proposed: #957 (G, 957 `design.md:154-178`) | M1a store, M1b WorkItems/`aar_`, bridge |
| Bridge (command outbox, claim/result/write-permit) | mctl-api | merged, dark (`MCTL_BRIDGE_ENABLED` unset, A `docs/bridge.md:8`) | provider worker (HTTP), control workflow (Temporal signal `bridge-result`, A `docs/bridge.md:168`) |
| Control worker (`GlovoControlWorkflow`) | mctl-agents | proposed: #1044 (G, 1044 `design.md:98-156`) | Temporal (its own namespace), mctl-api |
| Fake provider worker | mctl-telegram | proposed: #1262 (bridge HTTP client, no Temporal); supersedes the held tg#1258 | mctl-api bridge routes only |
| Temporal | mctl-gitops | live 1.31.0, plaintext, no authorizer; NetworkPolicy is the only isolation (G `docs/runbooks/temporal-client-auth.md`, live evidence rows) | mctl-api, mctl-agents workers, kuptsi |
| Staged deployment package | mctl-gitops | P0, inert (G `deploy/staged/glovo-m1/README.md`) | none |

## 2. Contract table

| # | Producer → consumer | Contract | Defined at | Notes |
| --- | --- | --- | --- | --- |
| C1 | mctl-api → all Glovo callers | Refusal body `{"error": <code>, "error_description": <fixed text>}`; closed `glovo.Code` enum; HTTP mapping via `glovo.Status` | G 959 `design.md:32`, 960 `design.md:31`, 961 `design.md:37` | owner kept this shape 2026-11-09 |
| C2 | operator → mctl-api | Kill switch `GLOVO_ENABLED` (default false) AND every readiness dependency healthy; `GLOVO_OAUTH_ENABLED`/`GLOVO_DISABLED` withdrawn | G 959 `design.md:33`, 960 `design.md:119,127` | `GLOVO_MCP_RESOURCE` alone still refuses `invalid_target` |
| C3 | migration job → DB | DDL only through `glovo.ApplySchema(ctx, migrationConnStr)`; runtime role DML only | G 959 `design.md:34` | no `AUDIT_DB_URL` fallback (owner) |
| C4 | Glovo worker / bridge provider → mctl-api | Two disjoint identities: Glovo worker (#961, default off, refused on `/api/v1/bridge/*`) and `service:bridge-provider:<ref>` with `bridge:provide`, audience `mctl-api-bridge` (refused on `/api/v1/glovo/*`) | G 959 `design.md:35`; A `docs/bridge.md:145-156` | issuer gated on mctl-gitops#2506 (`docs/bridge.md:154` writes it as mctl-api#2506, which does not exist) and #2540 |
| C5 | facade → mctl-api | Routes `/api/v1/glovo/facade/*` (#961 adds them to `glovoAudienceRoutes`); preflight `POST /resolve` returns `{tenant, principal_ref, contract_version}` | G 961 `design.md:41`; 957 `design.md:154` | see M3 |
| C6 | mctl-api → provider | Bridge HTTP: `POST /api/v1/bridge/commands/claim`, `/{command_id}/result`, `/{command_id}/write-permit`; command/result schemas `bridge.mctl.ai/v1alpha1` (vendored from mctl-agents#1045) | A `docs/bridge.md`; G 1262 `design.md:68-77` | `cmd_` ids generated server-side |
| C7 | mctl-api → control workflow | Temporal signal `bridge-result` `{command_id, result_digest}` to the stored workflow | A `docs/bridge.md:168` | see M6 |
| C8 | control workflow → mctl-api (enqueue) | `bridge.Store.Enqueue(ctx, tx pgx.Tx, …)` is an in-process Go call; no HTTP route exists | A `internal/bridge/store.go:478` | see M7 |
| C9 | control workflow → result | `GlovoControlResult` (`order_status` enum `completed|refused|cancelled|expired|unknown|failed`) | G 1044 `design.md:100-102` | see M8 |
| C10 | provider outcome map | Provider reports outcomes only within the frozen v1alpha1 enums; reclaim after `permitted` reports `unknown` (`applied_prior_lease`); `permit_already_issued` → `failed_terminal/internal/unknown` | G 1262 `design.md:10-15` | owner decision 2026-11-09 |

## 3. Mismatch list

Each row names the proposal that must change. "AMEND" means a gitops PR that
edits the proposal text, which supersedes any pending grant on the old digest.

| # | Mismatch | Evidence | Owner of the fix | Required change |
| --- | --- | --- | --- | --- |
| M1 | Identifier families differ: M1a uses `prn_<ULID>` principals and tenants by TEXT name; the bridge and #1044 use opaque `prr_`/`tnr_`/`ordr_`/`gcn_` handles | G 959 `design.md:69,149`; G 1044 `design.md:104-106` | #957 AMEND (owns the join) | One mapping table `prn_`/tenant name ↔ `prr_`/`tnr_`, where it is stored, who mints the opaque refs, and that raw `prn_`/tenant names never leave mctl-api in bridge commands |
| M2 | Refusal set not closed against the facade: #957 emits codes the facade does not know (`not_facade_identity`, `subject_token_invalid`, `insufficient_scope`, `tenant_mismatch`, …) and the facade expects codes #957 never emits | G 957 `design.md:174-178`; T `internal/glovo/mctlapi/client.go:262-267` | #957 AMEND | A wire → public mapping table with golden fixtures shared with the facade, including 429 → `rate_limited`; settle the `ambiguous_tenant` paragraph (G 957 `design.md:81`) that contradicts the 403 row (`design.md:175`) |
| M3 | `/resolve` shape: the merged facade decodes `{scope_ref, tenant, expires_at}` and refuses an empty `scope_ref`; #957 returns `{tenant, principal_ref, contract_version}` and drops `scope_ref` | T `internal/glovo/mctlapi/client.go:118-127`; G 957 `design.md:139,154` | #957 AMEND **and** a facade change in mctl-telegram | Pick one shape; the other side follows in a paired change with a contract test. Until then the merged facade cannot talk to #957 (P1 blocker) |
| M4 | `"replayed": true` on idempotent replays is not in the `additionalProperties: false` output schemas | G 957 `requirements.md:66`, `tasks.md:14`; `design.md:229` | #957 AMEND | Either add `replayed` to the schemas or signal replay out of band (header) |
| M5 | Second wire protocol: #957 defines `ReadBridge` with `glovo-read/v1alpha1` (`grr_` ids, `history|preview|basket`), separate from #968's command outbox | G 957 `design.md:157-159,189-192,232` | #957 AMEND | Reads go through the #968 bridge (`read_status` or a new kind added to the vendored schema by its own change), or the AMEND justifies a second channel with its own identity, rate limit and gate. Not both silently |
| M6 | Signal name: #1044 waits for `assistants_provider_result(command_id)`; mctl-api sends `bridge-result` `{command_id, result_digest}` | G 1044 `design.md:154`; A `docs/bridge.md:168` | #1044 AMEND | Use `bridge-result` and its payload; result is read back by digest, not trusted from the signal |
| M7 | Enqueue path: #1044 `ProviderBridgePort.create_command` assumes an HTTP route; #968 exposes only in-process `Store.Enqueue(ctx, tx pgx.Tx, …)` | G 1044 `design.md:124-127,152`; A `internal/bridge/store.go:478` | #1044 AMEND **and** #957 AMEND (decision needed) | Name the slice that adds a control-worker → mctl-api enqueue route (identity, rate limit, idempotency on operation key) or move enqueue into an mctl-api activity. No implementation before this is decided |
| M8 | `command_id` is derived client-side (`cmd_` + base32(sha256)[:26]); #968 mints `cmd_` server-side and dedupes by operation key | G 1044 `design.md:111-113`; A `docs/bridge.md` (command ids) | #1044 AMEND | Pass a deterministic operation key; accept the server-returned `cmd_`; drop client-side `command_id` |
| M9 | Outcome model: `order_status` enum vs bridge `outcome` × `provider_effect`; `unknown` after reclaim must survive the mapping | G 1044 `design.md:100-102,177`; G 1262 `design.md:10` | #1044 AMEND | A total mapping table `(outcome, provider_effect, error_code)` → `order_status`/`reason_code`, with `provider_effect=unknown` never mapped to `completed` or re-dispatch |
| M10 | Approval binding: `aar_` must bind exact execution and basket fingerprint at dispatch; approval refusals are not distinguished | G 1044 `design.md:149-152,168` | #1044 AMEND (P3 carry-over) | Fingerprint change = `basket_changed`, new `we_` + new `aar_`; distinct refusal reasons (`approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `provider_disabled`, `tenant_busy`); `hir_` stays non-authorizing |
| M11 | DB topology for the shared `pgx.Tx`: the bridge store opens `COMMERCE_DB_URL` (fallback `AUDIT_DB_URL`); the M1a store has no `AUDIT_DB_URL` fallback; #957 requires one transaction across join, WorkItem/`aar_` and enqueue | A `cmd/api/main.go:1019-1024`, `internal/bridge/store.go:414`; G 957 `design.md:83` | #957 AMEND | Name the single database and pool that every participant of the prepare transaction uses, or choose the compensating state machine the AMEND already allows |
| M12 | `invalid_target`: #977 answers `invalid_target` on `/oauth/authorize` and `/oauth/token` for the Glovo resource; #957 does not list it | A `internal/api/oauth_handlers.go:213-214` | #957 AMEND (P3) | Document that P2 requires #960's `GLOVO_ENABLED` admission; until then `invalid_target` is expected |
| M13 | Facade maps 400/422/429 and unknown codes to `upstream_invalid` | T `internal/glovo/mctlapi/client.go:250-267` | mctl-telegram facade follow-up (with M2) | 429 → `rate_limited` honouring `Retry-After`; 400/422 per the M2 table |
| M14 | Staged `compatibility.yaml` lists `GLOVO_TEAM_FALLBACK` | G `deploy/staged/glovo-m1/compatibility.yaml:14` | staged package (P1 prep PR) | Remove; there is no team fallback in the joint contract (C2) |
| M15 | Staged provider netpol and namespace patch assume a Temporal provider worker | G `deploy/staged/glovo-m1/netpol/worker-to-temporal.yaml`; `temporal-namespaces.patch.md:5-19` | staged package (P1 prep PR) | Replace with provider egress to the mctl-api bridge only; drop `mctl-assistants-provider-glovo` from the Temporal namespace list; keep the control namespace |
| M16 | README links mctl-agents#1043 as "the bridge" | G `deploy/staged/glovo-m1/README.md` Links | this PR | Point at mctl-api#968 / `docs/bridge.md`; #1043 stays as history |
| M17 | `docs/bridge.md:154` cites the issuer spike as mctl-api#2506; it is mctl-gitops#2506 | A `docs/bridge.md:154` | mctl-api docs fix (trivial) | Correct the reference |

Not a mismatch, recorded for completeness: #959/#960/#961 already agree on
C1-C5 (their joint contract was merged in #2541).

## 4. Minimal Temporal security path for P1 (bridge-only provider)

With #1262 the provider worker holds **no Temporal credential**; it speaks
HTTP to the bridge with `bridge:provide`. The Temporal clients that P1 adds
are therefore only:

- the control worker (#1044) in its own Temporal namespace;
- mctl-api, which starts `GlovoControlWorkflow` and sends `bridge-result`
  (it is already an admitted client of the shared cluster).

The DAG in G `docs/runbooks/temporal-client-auth.md` ("Downstream issue
breakdown") gates node I (`mctl-assistants*` namespaces) behind H, and H
behind G (authorizer), which needs A, B, D, E and F. A bridge-only provider
removes the provider namespace from I; it does not shorten the chain:

| Node | Needed for P1 | Filed | Note |
| --- | --- | --- | --- |
| A client support (token file, TLS CA) | yes | mctl-api#983, mctl-agents#1057 | kuptsi-app also needs it before G (`UNVERIFIED`: not filed) |
| B metrics and authz alerts | yes (G depends on it) | mctl-gitops#2539 | |
| C JWKS trust path decision | yes | mctl-gitops#2540 | also feeds the bridge issuer (#2506) |
| D shadow credential plumbing | yes | not filed | after C |
| E frontend TLS | yes | not filed | after A |
| F disposable canary | yes | not filed | this is the rollback test the handoff requires |
| G authorizer enablement | yes | not filed | production Temporal authorization change: separate approval and maintenance window |
| H production negative proof | yes | not filed | after G |
| I control namespace + identity | yes, control only | not filed | provider namespace no longer requested |
| J temporal-web identity | no | deferred | |

Until H passes, any P1 control worker would sit on a cluster where every
admitted 7233 caller can act on every Temporal namespace (G runbook, live
evidence). This file does not propose relaxing that order.

## 5. Ordered approval gates to P1

Each gate is a separate decision. Earlier gates do not approve later ones,
and a parent approval never covers a child issue.

1. **Contract AMENDs.** #959/#960/#961 (merged, #2541) and #1262 (merged,
   #2542) are done. Pending: #957 AMEND (M1-M5, M7, M11, M12) and #1044 AMEND
   (M6-M10), each as its own gitops PR with review.
2. **Digest approvals.** The owner approves the current digest of each of
   #959, #960, #961, #1262, #957 and #1044 individually, after the
   supersede comment; never the parent #954.
3. **Implementation.** Each slice merged through its own PR with green CI and
   a clean review on the head: #959 → #960 → #961; #1262 (then tg#1258 closes
   as superseded); #957; #1044; facade follow-up for M3/M13.
4. **Issuer decision** mctl-gitops#2506 / #2540 for the bridge provider and
   the Glovo worker credentials, plus the security approval for credential
   issuance that A `docs/bridge.md:175-177` requires.
5. **Temporal path** A → I (section 4), each node approved separately, G
   rollback-tested on the F canary first.
6. **Releases and images exist**; `compatibility.yaml` pinned to real
   versions; staged drift M14-M15 fixed in a P1 prep PR.
7. **P1 issue** under mctl-gitops#2457 and its owner approval. Only then a
   runtime deployment.
8. **P2** (DNS/TLS/OAuth/allowlist, Ingress) is a separate activation GO.

Related security work that is not a numbered P1 gate here: mctl-gitops#2543.

## 6. G3 note

Account operations against a real Glovo account remain
`BLOCKED_PROVIDER_ACCESS`. Glovo's own Claude connector covers discovery and
handoff only, and the Partner API is merchant-only; neither gives a consumer
basket or order API. MCTL builds no consumer discovery API of its own (owner
decision). P3 (real provider) stays out of scope, and nothing in M1 performs
login, basket mutation, checkout or payment.

## UNVERIFIED

- The live Temporal namespace list (G runbook: `NOT_OBSERVED`).
- Whether kuptsi-app has a filed node-A issue.
- The final name of the control Temporal namespace (the staged patch proposes
  `mctl-assistants`; node I will decide).
- Which slice owns the control-worker enqueue route (M7): no proposal names it.
- That the facade can adopt the #957 `/resolve` shape without a contract
  version bump (M3).

## A15 DB staging vs the mctl-api#1004 amendment (mctl-gitops#2579)

Amendment content digest `sha256:2aea76933eda79b535ca8b406f4c31ec2e92a4888928871d1cbd6b4cddd22db2`
(#2579 may still change; recheck the digest before completion). Staged under
`db/`, inert.

| # | #1004 contract | Staged in `db/` |
| --- | --- | --- |
| 1 | `mctl_api_workitems`, explicit `WORK_ITEMS_DB_URL` | managed role, credential ExternalSecrets, env text |
| 2 | `GLOVO_DB_RUNTIME_ROLE`, `GLOVO_DB_MIGRATION_ROLE` | env text, flags stay off |
| 3 | `GLOVO_MIGRATION_DB_URL`, `-work-items-role`, `-confirm` | suspended Job, `/bin/false`, placeholder image |
| 4 | database `mctl-api` | pg_hba lines and DSNs |
| 5 | `COMMERCE_DB_URL` role, connection limits | UNVERIFIED, activation blockers |
| 6 | transitional grants, operator ownership transfer | `roles.patch.md`, plan only, not applied |
