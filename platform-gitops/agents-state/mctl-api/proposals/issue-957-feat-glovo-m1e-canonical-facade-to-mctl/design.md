# Design: issue-957-feat-glovo-m1e-canonical-facade-to-mctl

## Amendment 2026-11-09 (c), round 7 of the AMEND PR

Two seams that round 6 left open. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| R6-957-1, CROSS X-C (the §3a mapping was not total over (command status, `effect_state`)) | §3a is rewritten as one table keyed by the order state and the pair (`status`, `effect_state`) that `bridge.Store.CommandEffect` returns. The canonical result-to-order table is mctl-api#985 §2a (one function, `reconcileOrder`); §3a only renders the wire strings of its last column and never redefines a transition. A pair outside the table is wire `unknown` and an audit event, never `dispatched` or `failed`. §6d.4 gives `CommandEffect` its two-value return |
| CROSS X-A, #985 F1 (G1 said #985 vendors the write schema; it has no emitter, gate or provider) | G1 below is corrected. One owner per responsibility: schema, envelope and result contract mctl-agents#1059 §Write command; per-command wire version, projection, Claim gating, `SubmitResult` and vendoring mctl-api#986 §2a (not #985); enqueue with `WireVersion` v1alpha2 #985 §5 step 11; parse and execute mctl-telegram#1262 task 2b. §7 pins the write schema digest next to the v1alpha1 ones |
| #985 read path (new lock row) | §6b: the `read_command_result` path is listed |

Open items table (round 6) after round 7: unchanged except OPEN-1059-4, whose write-schema half is closed by the vendoring rule above (one copy in #1059, vendored once in mctl-api by #986 task 1 and once in the provider by #1262 task 2b, each pinned by sha256).

## Amendment 2026-11-09 (c), round 6 (final, targeted) of the AMEND PR

Owner decision: only four groups are fixed now; every other round-5 finding is recorded as an OPEN item in its owning proposal. Where this section and older text disagree, this section wins.

| Group | Change |
|---|---|
| G1 (X-2, write command schema) | One owner: mctl-agents#1059 `command-place-order-fake.schema.json` (`bridge.mctl.ai/v1alpha2`, payload = the approval basket by `$ref`). (Round 7 correction: mctl-api#986 §2a vendors it and owns the wire version, Claim gating and `SubmitResult`; #985 only enqueues with `WireVersion` v1alpha2; mctl-telegram#1262 task 2b is the provider.) #957, #985, #988, #989 reference it. OPEN-1059-1, OPEN-985-8 and OPEN-989-6 are closed |
| G2 (X-1, F1, status bodies) | §3a: this slice owns the `GET /connection` and `GET /orders/{order_id}` bodies and every wire value; `outcome` comes from #985 `bridge.Store.CommandEffect`; #985 `read_command_result` owns `dispatched -> closed\|unknown` through #988 `MarkClosed` / `MarkUnknown` (OPEN-985-5 closed); `handoff_url` and `provider_account_label` are omitted from these bodies |
| G3 (F3, #988 P2-2) | Merge order puts A13/A14 (`glovo.control_starts`, `glovojoin.ApplySchema`, `ControlStartTx`) before #986 and #985; #985 lists A14 as a blocking dependency; package direction `control` imports `glovojoin`, and `Readiness` takes an injected `func`; #988 `Ready` is `not_ready` until #989 task 2b grants the `SELECT`s |
| G4 (#959 P2-3, P2-1) | `Transition` to `active` is `invalid_request`; CHECK `glovo_connections_active_expiry_check`; `Connection` and `Install` fields listed once in #959 Types (remainder OPEN-959-3). #960 N1 (one line): the allowlist routes use `isHumanAdmin` with T21a-T21d |

Open items recorded in round 6 (one recommendation each, in the owning proposal's requirements.md):

| Id | Proposal | Round-5 finding | Recommendation in one line |
|---|---|---|---|
| OPEN-961-1 | #961 | R5-1 | Connect resolves key K through a #959 read-only replay lookup before branching; fix the hash text |
| OPEN-961-2 | #961 | R5-2 | own `connect.ApplySchema` entry point, registered in the §6d.1 chain |
| OPEN-961-3 | #961 | R5-3 | a #961 wiring task for `WithEndPurger`, `Sweep`, `connect.Service`; name it in #985 task 9 |
| OPEN-961-4 | #961 | R5-4 | #959 `LiveConnection*` return the lapsed `*Connection` with `connection_expired` |
| OPEN-985-11 | #985 | F2 | `MCTL_GLOVO_WRITE_FENCE_ENABLED`, set by the gitops PR lifting #2457; route first, fence last |
| OPEN-985-13 | #985 | R8 | `DispatchCommandTTL` = 900 s, capped at `fresh_until` (#985 §7.4) |
| OPEN-985-14 | #985 | R8 | fixture seam: `glovojoin_fixture` selects `gate_fixture.go` and `ttl_fixture.go`; never skips §7.3 items 2 to 6 (#985 §7.4, T29) |
| OPEN-985-12 | #985 | F3 | vendor the control contract files into mctl-agents with `SHA256SUMS`, checked by #1044 and #990 |
| OPEN-986-4 | #986 | P2-1 | vendor `claim-response.schema.json` and pin the envelope strings; extend T7c |
| OPEN-986-5 | #986 | P2-2 | one canonical location per vector file, with sha256 pin tests |
| OPEN-988-5 | #988 | P2-4 | requirement, CHECKs and T20 for `join_refs` mint and lookup |
| OPEN-989-8 | #989 | N2 | Sweeper started from `main.go` by #985 task 9; drop the "no new interface" sentence |
| OPEN-1059-4 | #1059 | R5-2 | per-consumer vendor table; one basket copy location |
| OPEN-1059-5 | #1059 | R5-3 | normative pre-check rule list with a raw-text must-reject entry per rule |
| OPEN-959-3 | #959 | P2-1 (rest) | declare `AuditEvent`, `ConnectResult`, `ConnectInput`, `RefusalEvent`, `GrantRow`, `Option` once |

## Amendment 2026-11-09 (c), round 5 of the AMEND PR

Fold-in of the round-4 findings; simplified, no new mechanism beyond the one named per row. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| R4-1 (install id, revision, refresh family have no owner) | §6d.4: #959 `GetInstall` is the one source of install id and revision; #960 `teamgrant.Grant.RefreshFamilyID` the one source of the family; §2, §2b, requirements and A5 match |
| R4-2, X-3 (`GlovoControlInput` schema, `limits`, TTL) | §6c: #1044 owns the schema; this slice vendors it, writes its twelve members, copies `limits` from it and checks a golden; `GlovoApprovalTTL` is pinned to 15 minutes; OPEN-957-11 for the #1044 AMEND |
| X-1 (merge order), #988 F3 (`Querier`) | §6d.1 states the one merge order (#1059, #959, #988, ...); §6d.4 defines `dbq.Querier` once and the `glovo.RegisterGrants` registry owner (#959) |

## Amendment 2026-11-09 (c), round 4 of the AMEND PR

Resolves the round-3 findings that land in this canonical seam (F1 P3, F2, F3, X-1, X-2, X-3) and propagates the changes the other eight slices made. This slice stays the only copy of the refusal set, the lock order and the interface list. Where this section and older text disagree, this section wins.

| Finding | Change here |
|---|---|
| F2 (the outbox stores only a digest; the dispatcher cannot rebuild the input) | §6c: `glovo.control_starts` gains `input BYTEA NOT NULL`, the canonical `GlovoControlInput` JSON (refs, digests and the `gin_` taken from the preview row; no payload), written in the prepare transaction, INSERT-only (not in the UPDATE column list of §6d.1). `CHECK (input_digest = 'sha256:' \|\| encode(sha256(input), 'hex'))`. The dispatcher sends those bytes verbatim after re-checking the digest and rebuilds nothing. New crash-recovery test (tasks A13, T11) that starts from the stored input only |
| F3 (stale consent migration text) | Platform impact and tasks Rollback: the selected-tenant column and the consent change are deleted. The only migrations of this slice are the four `glovojoin.ApplySchema` tables (`join_previews`, `join_scope_refs`, `join_read_refs`, `control_starts`) |
| F1 P3 (one preview prepared into many orders) | §5 and §6: the preview is single-use. `join_previews.consumed_order_ref TEXT NULL` with a partial unique index; prepare claims it with `UPDATE ... WHERE consumed_order_ref IS NULL` under a new lock level L2c (§6b). Zero rows is 409 `fingerprint_changed` with the new internal reason `preview_consumed` (§4.2), so no code is added to the closed set. Grant row `UPDATE (consumed_order_ref)` on `join_previews` only. Tests T5 and T11 |
| X-1 (`GET /connection` and `POST /connections` have no owner) | Owner: #961, package `internal/glovo/connect` (`Service.Current`, `Service.Connect`, `JoinScope`, `ConnectOutcome`). §3 backing calls and §6d.4 list it. A replay of `POST /connections` returns the same `connection_id` and a freshly minted `handoff_url` (the raw handoff reference is never stored), with `Idempotent-Replayed: true`; this is the one documented exception to "byte for byte" |
| X-2 (`ApplyGlovoApprovalSchema` signature) | §6d.4 and §6d.1: `workitems.ApplyGlovoApprovalSchema(ctx, migrationConnStr, runtimeRole string) error`, the same shape as every other `ApplySchema` |
| X-3 (bridge read DDL claimed by #985 and #986) | One owner: #986, `bridge.ApplyReadSchemaTx(ctx, tx, runtimeRole)`. #985 `bridge.ApplySchema` calls it and depends on it. Merge order (§6d.1), no cycle: #1059, #959, #988 (with `internal/jcs`), #960, #961, #989, #986, #985, then this slice's read routes. The grant row of `bridge_read_results` names #986 as creator |
| Class sweep (#959 F1) | Every database-clock expiry compare in the Glovo slices is `clock_timestamp()`, never `now()` (the transaction start time). §6d.4 `LiveConnectionTx` and `ActivateTx` are updated; `join_read_refs` uses `clock_timestamp()` too |
| #959 F2/F3, #961 N3 (purge hook and grant registry) | §6d.4 lists `WithEndPurger`, `WithEndPurgerRequired`, `EndPurgerInstalled`, `GetConnectionForWorker` and the grant registry `glovo.expectedGrants`, which mirrors the `glovo.*` rows of §6d.1 |
| #985 F3 (bridge-store selector) | §6d.1 mode selector: probe, DSN and failure outcomes specified |
| #985 F2 (dispatch replay) | §6d.4: dispatch replays on any state with a non-empty `command_id` (the #985 definition); nothing changes here beyond the interface text |
| #989 F1, F2 | §6d.4: `GlovoApprovalInput` and `artifact_hash` (the basket fingerprint) are named; prepare chooses the TTL (`GlovoApprovalTTL`, a constant at most `MaxApprovalTTL`), the same value as the response `expires_at` and #1044's wait bound |

## Amendment 2026-11-09 (c), round 3 of the AMEND PR

Resolves the 35 confirmed findings of the second review round, at head `68118cc3c` (the round-3 fix-up). This slice
stays the canonical seam; the table lists only what changes here.

| Finding | Change here |
|---|---|
| X-1 (`ordr_` source; circular `order` join ref) | §2a drops the `order` kind; §6 step 4 mints the `ordr_` with #988 `NewOrderRef()` and passes it as `CreateInput.OrderRef` |
| X-2 (`InstallRevision` decimal vs `irv_`) | §5: two fields, decimal `InstallRevision` (stored, compared) and `InstallRevisionRef` (`irv_`, wire only) |
| X-3 (second pool) | §6d.4: #959 `NewStore(ctx, pool, runtimeRole, migrationRole, opts...)` (round 5), `Pool()`; `ProveOneDatabase(ctx, bridgeStore, glovoStore, workItemsPool)` |
| X-4 (`GlovoApprovalStatus` on the work-items pool) | §6d.4: `q Querier` on the Glovo pool; `GlovoApprovalForDecision` |
| X-5 (UPDATE column list nowhere) | §6d.1: the one exact list on `action_approval_requests` |
| X-6 (`PreLock` scope) | §6d.4: step 0 scope check before any lock |
| X-7 (`release_reservation`) | Not here: OPEN-985-9 in #985; no mctl-api slice depends on it |
| X-8 (MUST 10 owner) | New §5a: `glovo.join_read_refs`; §4.2 `read_ref_not_issued` |
| N2 (replay vs step order) | §6 step 1b read-only replay lookup; rollback-and-retry on `replayed=true` |
| Consent ownership (#960) | §2 consent bullet now defers to #960; tasks 5 withdrawn |
| F1/F2 of #985 (role attributes; bridge store mode) | §6d.1: `bridge_schema_version` selector; role attribute and trigger checks; OPEN-957-6, OPEN-957-7 |
| L2a/L2b | §6b: tenant mutex and handoff-ref rows, after L2 and before L3 |

## Amendment 2026-11-09 (c), round 2 of the AMEND PR

Resolves the confirmed findings of the second independent review of mctl-gitops#2550
(head `dc1fe6e5`) that land in this slice or that this slice now owns as the canonical
seam. Code references were re-checked at mctl-api `ceac9ed`. This slice is the single
owning place for the cross-slice seams: the closed refusal table (§4), the role and grant
table, the execution binding, the approval-basket source and the interface list (new
§6d). Every other Glovo proposal references these and does not restate them. Where this
section and older text disagree, this section wins; the contradicted passages are edited.

| Finding | Change here |
|---|---|
| X-1, F1, #988 F1/F2 (no tx-aware `wi_`/`we_` create; real `we_` ids carry hyphens; nobody binds the `we_` to the order) | §6d.2: #989 owns `CreateGlovoExecutionTx(ctx, tx, in) (workItemID, executionID, err)` with alphanumeric ids that match the bridge `refPatterns` (`internal/bridge/store.go:164-165`), no own transaction and no advisory lock outside L1..L6 (the generic `withTx` lock at `internal/workitems/store.go:266-272` is not taken). #988 `Create` writes `ExecutionID` once at insert. `RecordEffect` is withdrawn from prepare. §6 and task 8 updated |
| F5, #988 F6 (workflow id / run id and `tnr_`/`prr_` promised on the order row) | §6a corrected; §6d.2 names the reads #985 uses: workflow id from `ExecutionBindingTx`, run id from `glovojoin.ControlStartTx`, refs from #988 `LookupJoinRefTx`. `glovo.control_starts` is keyed by `order_ref` (`ordr_`) |
| X-2, F3 (prepare has no source for the approval basket) | §5 and §6d.3: `glovo.join_previews` stores the JCS bytes of the #1059 approval basket at read time, with its own expiry, independent of the #986 read TTL. Prepare never reads the provider. An empty basket or an all-unavailable preview is a valid read that prepare refuses |
| F4, X-9 (aar_ idempotency key is global) | §6: the #989 key is `"glovo-prepare:" + ordr_`, derived server-side, never the client key |
| X-4, F2 (one transaction runs as one role, but the role tables grant it nothing) | §6d.1: `glovo_runtime` used by the one Glovo pool (bridge and #959 stores), `glovo_migrator` that owns every object and applies all DDL and grants, the only grant table, existing consumers' grants, and the startup checks. Owner-confirmed 2026-11-09 with conditions R1-R5 (row below) |
| Owner decision 2026-11-09 (role model confirmed, R1-R5, plus the bridge startup DDL AMEND) | §6d.1 rewritten: R1 `glovo_runtime`, R2 `glovo_migrator` (credentials never in runtime or agents), R3 other roles only justified grants with an "existing consumers" table (work-items, commerce, bridge-scrub, bridge without Glovo), R4 one pool from `GLOVO_DB_URL` (`COMMERCE_DB_URL` stays commerce-only, `cmd/api/main.go:563`), R5 startup checks and negative tests; `bridge.NewStore` DDL at start (`internal/bridge/store.go:374`, origin/main = `ceac9ed`) is split by #985 into `bridge.ApplySchema` + `bridge.NewRuntimeStore`, no extra rights for the runtime role; grants never replace the per-write tenant, connection and `aar_` checks |
| X-3, F6 (refusal set not closed; §6 vs §4 on an expired preview) | §4 rewritten as the closed table for both the facade routes and the #985 control routes, with internal `glovo.Code`, HTTP status, both wire columns and #1044 M10. §6 now says 404 for an expired preview |
| F7, #986 F3, X-12 (ReadBridge request does not match #986; "opaque hash") | §5 sketch replaced: `GlovoReadRequest` is #986 `ReadRequest`, with the verified principal id, the `tnr_`/`prr_`/`gcn_` refs and the subject token's scopes. Read routes mint missing refs in their own short transaction under L1/L2 shared |
| X-5 (no owner for `irv_`) | §2a: new join-ref kind `install_revision` (`irv_`) in #988 `glovo.join_refs`. It is wire-only; mctl-api compares the raw decimal revision |
| X-6, #959 F1, #985 F1, #988 F3 (interface names and signatures differ) | §6d.4: one interface list per providing slice; every consumer uses these names |
| P3 F8 (L6 is read before L3, which breaks the ordering rule) | §6b: L6 is a lock-free read and is exempt from the ordering rule; the only non-row waits a Glovo path may take are listed there |
| P3 F10 (#989 expects an owner cancel through #957) | Not added: an unapproved order is closed by #985 cancel or by expiry of its `aar_`; #989 is corrected |
| P3 X-7 (who creates schema `glovo`) | §6d.1: every `ApplySchema` runs `CREATE SCHEMA IF NOT EXISTS glovo` under the migration role, in a fixed order |

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
| #988 P2-7 (two owners of the join-ref table) | §2a: the table is #988's `glovo.join_refs`, minted through #988 `MintJoinRefTx` (kinds `tenant`, `principal`, `install_revision`); the `ordr_` is not a join ref but #988's own `order_ref` column (round 3). #988's internal `pord_` primary key is unexported and never leaves the store |
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
  set `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL` explicitly to one physical database (amended (c), §6d.1 R4). Equal
  URL strings are not proof: a test proves that the prepare writes and #985's `Enqueue`
  share one `pgx.Tx`. Missing configuration or an unproven boundary answers `not_ready`.
  (Amended (b): there is no different-database branch; `GLOVO_DB_URL` is part of the one
  database and the one transaction, §6b.) Removing #968's generic fallback is a separate,
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

The `Prepare` sequence is not atomically satisfied merely by invoking existing `workitems.CreateActionApproval` and `ExecutionByID` while holding a separate `glovojoin` transaction. Design a concrete shared DB pool and `pgx.Tx`-aware WorkItem/execution/`aar_` APIs **or** an idempotent compensating state machine with separately validated transitions; prove failure injection on each boundary, no orphan approved receipt, no duplicate ordr_/we_/aar_, and zero fake-provider writes. Any fallback to partial commit must explicitly remain `not_ready`/blocked until reconciled. The legacy #954 source uses `ReserveActionApprovalTx` only for reserve, not pending creation; don't assume a `Prepare` helper exists or can span databases. Amendment 2026-11-09 names the shared pool and the tx-aware APIs in §6b; the compensating state machine stays the allowed fallback.



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
       --[X-Mctl-Selected-Tenant: <echo of the stn claim>]
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
- **Server-bound selected tenant (owned by #960; round 3).** Consent-time team selection,
  the claims and the resolver belong to mctl-api#960 alone (joint contract, "Consent-time
  team selection" row); this slice adds no consent path and mints no tenant claim. #960's
  consent page lists the eligible teams (membership ∩ pilot allowlist minus
  non-selectable tenants; the current install is checked at use, not at consent), with
  nothing preselected, stores a server-side `oauth_team_grants` row and mints the claims
  `tgr` (grant id) and `stn` (selected tenant). On every join call the tenant is that
  verified claim, read through `User.TeamGrant()` and re-checked by `teamgrant.Check` on
  every request. The `X-Mctl-Selected-Tenant` header is optional, compared with `stn` and
  never read as input. Then `scope.Resolver.Resolve(ctx, *auth.User) (Scope, *glovo.Error)`
  (#960 §4) runs, then #959 `GetInstall` supplies the install id and revision (§6d.4), and
  the first refusal of either is returned unchanged. There is no default
  tenant, no sole-membership fallback and no `labs`. A token without a valid `tgr` is
  `ambiguous_tenant`.
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
    | `install_revision` | `irv_` | (tenant, install, revision) | `<gin_>@<decimal revision>`; added (c) for the #1059 read command's `install_revision_ref`. Wire-only: mctl-api stores and compares the raw decimal revision, never the `irv_` |

- Format: prefix plus 26 base62 characters from `crypto/rand` (the bridge's `randAlnum`),
  inside the bridge patterns `^(tnr|prr|ordr)_[A-Za-z0-9]{16,40}$` and the #1059 pattern `^irv_[A-Za-z0-9]{16,40}$`. Refs are random, never
  a hash of the raw id, so enumerating tenant names or ULIDs cannot reverse them.
  `UNIQUE(kind, ref)` and `UNIQUE(kind, tenant, subject_id)`; minted lazily with
  `INSERT … ON CONFLICT DO NOTHING` plus `SELECT` inside the transaction that first needs
  them; never updated, reused or deleted while an order references them. Amended (c): the
  read routes (history, preview, basket) are the first to need `tnr_`, `prr_` and `irv_`.
  They mint them in their own short transaction on the bridge pool under L1 and L2
  shared, commit, then call `ReadBridge`. Prepare mints `tnr_`, `prr_` and `irv_` where absent in its §6b transaction. The `ordr_` is **not** a join ref (round 3): it is the order's own `order_ref` column, generated by prepare with #988 `orders.NewOrderRef()` before the workflow id is derived, and passed to #988 `Create` as `CreateInput.OrderRef` (§6 step 4, #988 §1). Readers that only need an existing ref use #988
  `LookupJoinRefTx` (§6d.4), which answers `not_found` when the ref was never minted.
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
  install id and install revision from #959 `GetInstall`, and the team grant's
  `RefreshFamilyID` (the `Grant` returned by #960 `teamgrant.Check`; the access token
  carries `tgr`, not a family claim), so revoking the grant revokes every ref minted
  from it.
- **TTL.** `expires_at = min(now + 5 min, subject token exp)`. The facade resolves per
  tool call, so a short TTL costs nothing.
- **Storage.** Server-side only, as `sha256(ref)`, in `glovo.join_scope_refs(ref_hash
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
| `glovo_auth_status` | `GET /connection` | none | `{connection_state, connection_id?, provider_account_label?, expires_at?}` | `glovo:read` | `connect.Service.Current(ctx, JoinScope)` (#961 §4a; `no_connection` when there is none); body fields §3a | #961 (call), #957 (body) |
| `glovo_connect_account` | `POST /connections` | `{idempotency_key}` | `{connection_id, state:"pending_handoff", handoff_url, expires_at}` | `glovo:basket:prepare` | `connect.Service.Connect(ctx, JoinScope, idempotency_key)` (#961 §4a: #959 `Connect` under L1/L2/L2a, then the `ghr_` row; `handoff_url` = `GLOVO_SYNTHETIC_HANDOFF_BASE_URL` + `/` + the raw reference) | #961 |
| `glovo_get_order_history` | `POST /orders:list` | `{limit<=20, cursor?}` | `{orders:[...], next_cursor?}` | `glovo:read` | `ReadBridge.History` | M1e (seam), mctl-api#986 (transport), mctl-telegram#1262 (fake data) |
| `glovo_preview_reorder` | `POST /previews` | `{order_ref}` (wire name unchanged; value is the #1059 `pho_` history-order ref) | `{preview_id, items, unavailable_items, fingerprint, expires_at}` | `glovo:read` | `ReadBridge.Preview` plus a `glovo.join_previews` row; `fingerprint` computed by mctl-api over the #1059 approval basket | M1e |
| `glovo_get_basket` | `GET /basket` | none | `{store_name?, items, totals_label, fingerprint}` | `glovo:read` | `ReadBridge.Basket`; `fingerprint` computed by mctl-api over the #1059 approval basket | M1e / mctl-api#986 / mctl-telegram#1262 |
| `glovo_prepare_order` | `POST /orders:prepare` | `{preview_id, idempotency_key}` | `{order_id, fingerprint, consent_request_id, expires_at}` | `glovo:basket:prepare` | #988 order (`ordr_`) + `we_` + #989 `CreateGlovoApprovalTx` pending `aar_`, zero provider writes; `order_id` is the `ordr_` | #988, #989 |
| `glovo_order_status` | `GET /orders/{order_id}` | none | `{state, outcome}` (§3a; no `handoff_url`) | `glovo:read` | #988 owner-path `Get`, #989 `GlovoApprovalStatus` and #985 `bridge.Store.CommandEffect`, all on the `glovo_runtime` pool (never the work-items pool, §6d.4); body and mapping §3a | #957 (body, mapping), #988, #989, #985 (reads) |
| (launch) | `GET /compatibility` | none | `{contract_version, contract_digest, api_version, dependencies:{connection_registry, provider_orders, read_bridge, control_worker, provider_worker}, deploy_ready}` | facade identity, no subject needed | `glovojoin.Readiness` | M1e |

`consent_request_id` is the `aar_` id. The human decides it only through the existing
owner decision route (`POST /api/v1/action-approvals/{id}/decision`), which the facade
cannot reach. No join route decides, consumes, reserves or settles an `aar_`, and none
accepts an `hir_`.

### 3a. Status bodies (round 6, G2; the one owner is this slice)

This slice owns the two wire bodies and every wire value in them; the sources below are
the only inputs, and the handler adds no other field. A wire field with no source is
omitted.

- `GET /connection`: `connection_state` = #959 `Connection.State`, `connection_id` =
  `ConnectionID`, `expires_at` = `ExpiresAt` (omitted while NULL). `provider_account_label`
  is omitted in M1: no #959 or #961 field holds one and the pinned tool schema marks it
  optional. No connection is 404 `no_connection`, a lapsed one `connection_expired`
  (#961 `Current`); neither has a body.
- `GET /orders/{order_id}`: `{state, outcome}`. `handoff_url` is never part of this body
  (it belongs to `POST /connections`, #961). Inputs: #988 `Order.State` and `CommandID`;
  #989 `GlovoApprovalStatus(aar)` only while the order is `finalized`; #985
  `bridge.Store.CommandEffect(commandID)`, which returns the pair (`status`, `effect_state`) of
  the command (round 7), only when `CommandID` is non-empty. `outcome` is `observed_placed` only for
  (`completed`, `succeeded`), else `OUTCOME_UNKNOWN` (placement not observed).

The order state decides the first four rows alone. For an order that has a `CommandID` and is
`dispatched` or `closed` the wire `state` is the last column of the canonical table in mctl-api#985
§2a ("Result to order"), keyed by the pair, and is not stored or waited for: it is derived on every
read, so it is the same before and after `reconcileOrder` has moved the stored order.

| #988 `Order.State` | other input | wire `state` | wire `outcome` |
|---|---|---|---|
| `open` | none | `open` | `OUTCOME_UNKNOWN` |
| `finalized` | aar `pending` / `approved` / `refused` / `expired` | `awaiting_approval` / `approved` / `refused` / `expired` | `OUTCOME_UNKNOWN` |
| `cancelled` | any | `cancelled` | `OUTCOME_UNKNOWN` |
| `unknown` | any | `unknown` | `OUTCOME_UNKNOWN` |
| `dispatched`, `closed` | `pending` or `leased`, `none` or `permitted` | `dispatched` | `OUTCOME_UNKNOWN` |
| `dispatched`, `closed` | `pending` or `leased`, `unknown` | `unknown` | `OUTCOME_UNKNOWN` |
| `dispatched`, `closed` | `completed`, `succeeded` | `placed` | `observed_placed` |
| `dispatched`, `closed` | `completed`, `failed` or `not_performed` | `failed` | `OUTCOME_UNKNOWN` |
| `dispatched`, `closed` | `completed`, `unknown` | `unknown` | `OUTCOME_UNKNOWN` |
| `dispatched`, `closed` | `completed`, `none` | `failed` | `OUTCOME_UNKNOWN` |
| `dispatched`, `closed` | `cancelled` or `expired`, `none` | `cancelled` | `OUTCOME_UNKNOWN` |
| `dispatched`, `closed` | `cancelled` or `expired`, `unknown` | `unknown` | `OUTCOME_UNKNOWN` |
| `dispatched`, `closed` | any other pair, or `CommandEffect` finds no command, or its read fails | `unknown`, and an audit event | `OUTCOME_UNKNOWN` |

The table is total: every #988 state, and for the last six rows every pair of the five command
statuses and six effect states, lands on exactly one row (the "any other pair" row is the
complement, and an unreadable command is never read as a command that did nothing). A pair outside
the table can only come from an invariant violation (for example a terminal command whose
`effect_state` is `permitted`); it is never rendered as `dispatched` or `failed`. The mapping to
#1044 M9 (a workflow vocabulary: `completed`, `cancelled`, `expired`, `failed`, `unknown` with
`reason_code`) is a different surface and is read by #985's `read_command_result` triple, not by this
body; the two agree on every pair that has an effect, and differ only in that an expired command is
`cancelled` on this wire and `expired` in the workflow (a wire string that does not exist here,
by design, because the facade vocabulary has no `expired` for a dispatched order).

A failed effect is surfaced only; it writes nothing to the order or the `aar_` (#989 §7
already leaves that `aar_` `consumed` or `unknown`). The result-to-order transition
(`dispatched` to `closed`, `cancelled` or `unknown`) is owned by #985 `reconcileOrder`
(called from `read_command_result` and from `Cancel`), and this body does not wait for it. The
contract JSON pins these strings, with one fixture per row and a test over every #988 state and
every (`status`, `effect_state`) pair (T6).

### 4. Refusal and status mapping (closed set; amended 2026-11-09 and (c))

The wire `error` value on 401, 403, 404 and 409 of the facade join routes is a member of
the set the merged facade accepts (`upstreamCodes`, mctl-telegram `27c671d2`
`internal/glovo/mctlapi/mctlapi.go:42-47`), except the codes marked *exception*. At
`27c671d2` the facade shows those as `upstream_invalid` (fail closed). Owner decision
D4: the facade fix mctl-telegram#1264 consumes exactly these four codes: 409
`fingerprint_changed` (the client refreshes the preview), 409 `idempotency_key_reused`,
400 `invalid_arguments` and 429 `rate_limited` (with `Retry-After`). This API sends no
422. Adding a fifth public facade code needs a coordinated, versioned M0 contract and
golden-fixture update in both repositories. The internal reason never reaches the wire;
it is recorded in the audit event and the span attribute `glovo.refusal_reason`.

**Amended (c): this is the only closed refusal set of the Glovo M1 slices** (owner
decision D-F). It covers the facade join routes of §3 and the #985 control routes.
#959, #985, #986, #988 and #989 emit only the internal `glovo.Code` values of the first
table; each route family maps them to the wire with that table and nothing else. #959's
`glovo.Status(code)` returns exactly the HTTP column, and a golden test (task A6) checks
`glovo.Status` against this table for every code. A slice that needs a new code adds a
row here in the same PR (through D4 when the facade wire changes). `unavailable` and
`invalid_request` are the internal codes; `dependency_unavailable` and
`invalid_arguments` exist only as facade wire values.

#### 4.1 Codes

| `glovo.Code` (internal) | HTTP | Facade route wire `error` | Control route wire `error` (#985) | #1044 M10 |
|---|---|---|---|---|
| `not_authorized` | 401 when no valid bearer or subject token, else 403 | `not_authorized` | `not_authorized` | terminal |
| `no_tenant` | 403 | `no_tenant` | `no_tenant` | terminal |
| `ambiguous_tenant`, `not_in_pilot`, `scope_unsupported`, `no_install` | 403 | unchanged | not produced | — |
| `stale_install` | 403 | `stale_install` | `stale_install` | terminal |
| `not_found` | 404 | `not_found` | `not_found` | terminal |
| `no_connection` | 404 | `no_connection` | `no_connection` | terminal |
| `connection_revoked`, `connection_expired` | 409 | unchanged | unchanged | terminal |
| `connection_exists`, `stale_version` | 409 on M1a's own routes | sent as 503 `dependency_unavailable` (a retry sees the live state through `GET /connection`) | not produced | — |
| `fingerprint_changed` | 409 | *exception* `fingerprint_changed` | not produced | — |
| `idempotency_key_reused` | 409 | *exception* `idempotency_key_reused` | not produced (control routes take no key) | — |
| `invalid_transition` | 409 | never sent: see the reason table | `invalid_transition` | terminal |
| `approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `basket_changed` | 409 | never sent: see the reason table | unchanged | the same name |
| `tenant_busy` | 409 | sent as 503 `dependency_unavailable` | `tenant_busy` | `tenant_busy` |
| `invalid_request` | 400 | *exception* `invalid_arguments` | `invalid_request` | terminal |
| `rate_limited` | 429 (+ `Retry-After`) | *exception* `rate_limited` | `rate_limited` | retryable |
| `not_ready` | 503 | `not_ready` | `not_ready` | `provider_disabled` |
| `unavailable` | 503 | `dependency_unavailable` | `unavailable` | retryable |

The facade maps every 5xx by status to `upstream_unavailable`. `not_authorized` is the
only code with two statuses.

#### 4.2 Conditions

| Condition | Internal reason (audit only) | `glovo.Code` |
|---|---|---|
| Bearer is not the facade workload identity | `not_facade_identity` | `not_authorized` (401) |
| Subject token missing, invalid, expired, revoked, wrong `iss`/`aud` | `subject_token_invalid` | `not_authorized` (401, + `WWW-Authenticate`) |
| `X-Mctl-Scope-Ref` missing, unknown, expired, revoked, or bound to another principal, tenant or grant family (§2b) | `scope_ref_invalid` | `not_authorized` (403) |
| `scope_ref` bound to an install revision that is no longer current | `scope_ref_stale` | `stale_install` |
| Subject token lacks the route's scope; #986 `ErrReadNotAuthorized` | `insufficient_scope` | `scope_unsupported` |
| No human-selected team grant (also with one eligible team) | `tenant_selection_missing` | `ambiguous_tenant` |
| `X-Mctl-Selected-Tenant` present and different from the verified claim | `tenant_mismatch` | `not_authorized` (403) |
| M1a resolver refusal | the M1a code | the M1a code, status from §4.1 |
| No connection for this owner, or a `gcn_` that is foreign or absent | `connection_not_found` | `no_connection` |
| Connection exists but is not active (including `expires_at` passed, #959 `LiveConnectionTx`) | `connection_not_active` | `connection_expired` or `connection_revoked`, by M1a state |
| #986 `ErrBindingMismatch` with an M1a state attached | `read_binding:<state>` | `no_connection`, `connection_revoked`, `connection_expired` or `stale_install`, by that state |
| Preview or order absent, foreign (owner or tenant), or preview expired | `preview_not_found`, `order_not_found`, `preview_expired` | `not_found` |
| A `pho_` in `POST /previews`, or a history `cursor`, that no earlier history read returned to this (tenant, principal, connection) (§5a, #1059 consumer duty 10) | `read_ref_not_issued` | `not_found` (zero commands enqueued) |
| Prepare on a preview with no approval basket (empty basket, every item unavailable) | `basket_empty` | `invalid_request` |
| The preview's stored approval basket no longer yields its stored fingerprint under the vendored #1059 rules (for example after a contract update between preview and prepare) | `fingerprint_changed` | `fingerprint_changed` |
| Prepare on a preview that already produced an order under another idempotency key (`consumed_order_ref` set; round 4, F1 P3) | `preview_consumed` | `fingerprint_changed` |
| Same idempotency key, different body | `idempotency_key_reused` | `idempotency_key_reused` |
| Schema violation, unknown or duplicate field, header/body key mismatch, an `ordr_` in the preview `order_ref` | `invalid_request` | `invalid_request` |
| Rate limit | `rate_limited` | `rate_limited` |
| Dependency not configured, proof failed, gate closed | `not_ready:<dependency>` | `not_ready` |
| Store or bridge read failed (never mapped to empty); #986 `ErrReadUnavailable`, `ErrCommandNotFound`, `ErrCommandExpired`, or `ErrBindingMismatch` without an M1a state | `dependency_unavailable:<dependency>`, `read:<sentinel>` | `unavailable` |
| A sibling store refusal that cannot occur on a facade route unless an invariant broke: #988 `invalid_transition` at prepare (a replay is answered by the idempotent replay path before any write), #989 `approval_replayed` at prepare (the order is new) | `invariant:<store>:<code>` | `unavailable` (facade); the store code itself on control routes |
| `lock_timeout` (SQLSTATE `55P03`) on any lock of the §6b order | `tenant_busy` | `tenant_busy` |
| Any other I/O error | `dependency_unavailable:<dependency>` | `unavailable` |

The #985 control-route conditions are listed in #985 design §2b; each resolves to a code
of §4.1 and nothing else.

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
therefore prepare) answer `not_ready`; P1 acceptance requires them working.

`internal/glovojoin/bridge.go` (rewritten (c); the request is #986 `bridge.ReadRequest`
field for field, so A12 is a pass-through and no field is translated):

```go
type ReadBridge interface {
    Read(ctx context.Context, req bridge.ReadRequest) (*bridge.ReadResult, error)
}
// bridge.ReadRequest (#986 design §3), filled by the handler from verified values only:
//   Kind             history | preview | basket
//   Tenant           the verified claim tenant (private, never on the wire)
//   OwnerPrincipalID the verified subject principal id, prn_ (private)
//   TenantRef, PrincipalRef  tnr_, prr_ from #988 glovo.join_refs (§2a), minted by the read route
//   ConnectionRef    the owner's live gcn_ read through #959
//   InstallRevision    the current install revision as the decimal string of the #959 BIGINT. Canonical form
//                      (round 3, X-2): this is what #986 stores in bridge_read_results.install_revision and
//                      compares with #959 LiveConnection's revision in FetchReadResult. mctl-api never compares an irv_.
//   InstallRevisionRef the irv_ ref minted by the read route (§2a) for <gin_>@<decimal>. Wire only: #986 writes it, and only
//                      it, to the command's install_revision_ref (#1059); the two fields are filled together, from one
//                      #959 read, and EnqueueRead refuses a request where either is empty
//   Scopes           the scopes of the verified subject token
//   Params           bounded, validated against the #1059 read-command schema
//   Deadline         at most the handler deadline
// bridge.ReadResult{Kind, ResultRef, Digest, Data (JCS bytes of the payload), ExpiresAt}
```

- Amended (b), (c): the result carries no binding refs and the handler checks no echo.
  #986 `FetchReadResult` is the **authoritative** binding check: it takes every binding
  from the stored command row and checks tenant, owner, `glovo:read`, expiry, connection
  and install revision against the request above. The handler
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
  table is `glovo.join_previews(id 'gpv_'+128-bit, tenant, principal_id, connection_id,
  install_id, install_revision, approval_basket BYTEA NULL, fingerprint TEXT NOT NULL
  DEFAULT '', payload_hash, created_at, expires_at <= 15m, consumed_order_ref TEXT NULL)` plus `CREATE UNIQUE INDEX join_previews_consumed ON glovo.join_previews (consumed_order_ref) WHERE consumed_order_ref IS NOT NULL`, with
  `CHECK ((approval_basket IS NULL AND fingerprint = '') OR fingerprint = 'sha256:' ||
  encode(sha256(approval_basket), 'hex'))`. Amended (c), the approval-basket source
  (§6d.3): `approval_basket` holds the JCS bytes of the #1059 approval basket taken from
  the read payload at preview time, after #988 `basket.Parse`. It is NULL for a valid
  empty preview. The preview row has its own expiry and does not depend on the #986
  read-result TTL; prepare never reads `bridge_read_results` and never calls the
  provider. Amended 2026-11-09: its DDL runs in `glovojoin.ApplySchema` under the
  migration role (joint contract C3), not inline at runtime.
  Round 4 (F1 P3): a preview is single-use. Prepare claims it with `UPDATE glovo.join_previews
  SET consumed_order_ref = $ordr WHERE id = $1 AND consumed_order_ref IS NULL` (§6 step 4b); the
  column is the only one prepare may update on this table (§6d.1), and the claim rolls back
  with the transaction, so a failed prepare leaves the preview usable.
- Amended (c): an empty current basket and a preview whose every item is unavailable are
  valid, successful reads (#1059 `empty: true`). `GET /basket` then answers `items: []`
  and `fingerprint: ""`, and `POST /previews` answers `items: []` with the
  `unavailable_items` and `fingerprint: ""` (the M0 tool schema types `fingerprint` as a
  plain string, mctl-telegram `27c671d2` `internal/glovo/contract/glovo-mcp-tools.json`).
  Prepare on such a preview is refused (`basket_empty`, §4.2). An empty answer is never a
  stand-in for `not_ready` (requirements).

### 5a. Issued `pho_` refs and cursors (#1059 consumer duty 10; owner: this slice)

mctl-agents#1059 makes it a consumer MUST to accept a `pho_` history ref or a `cursor` in
a read command only if an earlier history read for the same tenant, principal and
connection returned it. This slice owns that check (round 3, X-8); #986 is a transport and
validates parameters only against the #1059 schema.

- Table `glovo.join_read_refs(tenant TEXT, principal_id TEXT, connection_id TEXT, kind
  TEXT CHECK (kind IN ('pho','cursor')), ref TEXT, created_at TIMESTAMPTZ, expires_at
  TIMESTAMPTZ, PRIMARY KEY (tenant, principal_id, connection_id, kind, ref))`, created
  by `glovojoin.ApplySchema` (A14); `glovo_runtime` rights in §6d.1 (`SELECT, INSERT,
  DELETE`). It holds opaque refs only, never a payload.
- `POST /orders:list` (history): after the result validates against the #1059 schema, the
  handler inserts every `pho_` order ref and the `next_cursor` it returned
  (`ON CONFLICT DO NOTHING`, `expires_at = clock_timestamp() + 1 h`, which is longer than the 15 min
  preview window and independent of the read-result TTL) in one short transaction on the
  `glovo_runtime` pool, and answers only after that commit. An insert failure is
  `unavailable`; the handler never answers with refs it did not record. A request that
  carries a `cursor` first requires `kind='cursor'` to exist for (tenant, principal,
  connection), unexpired, else 404 `not_found` with zero commands enqueued.
- `POST /previews`: before `ReadBridge.Preview` the handler requires `kind='pho'` for the
  request's `order_ref` under the same triple, unexpired, else 404 `not_found` (internal
  reason `read_ref_not_issued`) and no `bridge_commands` row. The check is by exact
  match; a `pho_` that belongs to another principal, tenant or connection is
  indistinguishable from an unknown one.
- Expired rows are deleted by a bounded sweep and refused on read regardless of it. The
  table takes no advisory lock and no row lock of the §6b order; its own unique-index
  waits are listed there.
- The provider side (Provider MUST 1-3: resolve `pho_` only inside the connection, refuse
  a foreign or unknown ref as `failed_terminal/provider_rejected`) stays with the provider
  and is tracked as OPEN-1059-3 (widened in mctl-agents#1059); this check is defence in
  depth, not a substitute for it.

### 6. Prepare path (zero writes)

`POST /orders:prepare` runs as follows (rewritten (c); every name is from §6d.4).

1. Begin the §6b transaction on the bridge pool (READ COMMITTED). #959
   `LockOwnerShared` (L1, L2 shared), then #959 `LiveConnectionTx` (L6 read; `expires_at`
   passed counts as expired).
1b. **Replay lookup before any write** (round 3). Under L2 shared, call the read-only #988
   `LookupByIdempotencyKey(ctx, tx, sc, key)`. On a hit compare `request_hash` (another
   body is 409 `idempotency_key_reused`), then answer the replay from the stored order and
   its `aar_` (`GlovoApprovalStatus` on the same transaction), byte for byte, with
   `Idempotent-Replayed: true`. Nothing is written, no `ordr_`, `wi_` or `we_` is minted.
2. Load the `gpv_` row by (id, tenant, principal). Absent, foreign or expired: 404
   `not_found` (§4.2). A row whose `consumed_order_ref` is already set (and that step 1b did
   not answer as a replay): 409 `fingerprint_changed`, reason `preview_consumed` (§4.2). A NULL `approval_basket` (empty preview): 400 `invalid_arguments`
   (`basket_empty`). The connection and install revision must equal the row's, else the
   §4.2 connection or `stale_install` code.
3. `basket.Parse(row.approval_basket)` (#988) and `basket.Fingerprint` over the result
   must equal `row.fingerprint`, else 409 `fingerprint_changed`. No read call is made.
4. Mint the `ordr_` with `orders.NewOrderRef()` (#988; not a join ref, §2a) and mint or
   re-read `tnr_`/`prr_` with `MintJoinRefTx`. Compute the deterministic workflow id
   (§6c) from the refs and the `ordr_`.
4b. (round 4, F1 P3) Claim the preview, level L2c of §6b: `UPDATE glovo.join_previews SET
   consumed_order_ref = $ordr WHERE id = $gpv AND tenant = $t AND principal_id = $p AND
   consumed_order_ref IS NULL`. Zero rows means another prepare claimed it after step 2:
   roll the transaction back and re-run from step 1, which hits 1b when the winner used the
   same key and otherwise stops at step 2 with `preview_consumed`.
5. #989 `CreateGlovoExecutionTx` creates the owner's `wi_` and `we_` (§6d.2), with the
   workflow id as the execution's engine ref.
6. #988 `Create` (snapshot 1 = the preview's approval-basket bytes, `ExecutionID` = the
   `we_`, `OrderRef` = the `ordr_` of step 4, `ExpectedFingerprint` = the row's) and
   `Finalize`. The order's `order_ref` **is** the `ordr_` of step 4, returned as
   `order_id`; the workflow id, `engine_ref`, the `aar_` key and `control_starts` all embed
   that one value. If `Create` returns `replayed=true` (two prepares with one key both
   missed step 1b), roll the whole transaction back, which discards the `wi_`/`we_` and
   join rows of steps 4-5, and re-run from step 1 (the retry then hits 1b).
7. #989 `CreateGlovoApprovalTx` creates the pending `aar_` and calls #988 `BindApproval`.
   Its `IntentHash` is #989 `GlovoIntent` over the binding and the fingerprint. Its
   idempotency key is `"glovo-prepare:" + ordr_`, derived here and never taken from the
   client (the generic `UNIQUE (requested_by, idempotency_key)` is global across tenants,
   `internal/workitems/action_approvals.go:152`).
8. Insert the `glovo.control_starts` row (§6c), including the canonical `GlovoControlInput`
   bytes and their digest (round 4, F2). Commit.

No provider effect row, no bridge command and no dispatch is created. Idempotency is
the step 1b lookup plus #988's idempotent create on `(tenant, owner, client idempotency_key)` as the concurrency backstop: a replay with the
same key and body returns the original body byte for byte with the header
`Idempotent-Replayed: true` (M4; the one exception is `POST /connections`, whose replay
returns the same `connection_id` and a freshly minted `handoff_url`, #961 §4a), and the body never gains a `replayed` field; the same
key with a different body is 409 `idempotency_key_reused`. Two owners, or two tenants,
using the same client key prepare independently. If a dependency does not expose the
§6d.4 methods, `Readiness` reports `provider_orders: not_ready` and the route returns
503. A nominal `Prepare` method without tested cross-store atomicity and crash recovery
does not satisfy readiness.

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
  merged code (corrected (c)): the #988 order row carries its `ordr_`, the `we_`
  (`ExecutionID`, set at `Create`), the bound fingerprint and the pending `aar_`. The
  order row does **not** carry `tnr_`, `prr_`, a workflow id or a run id. #985 reads
  them with the §6d.2 calls: `tnr_`/`prr_` through #988 `LookupJoinRefTx`, the workflow
  id through #989 `ExecutionBindingTx`, and the run id through `glovojoin.ControlStartTx`.
  Every write #985 makes can run on the §6b transaction boundary. Test A8 asserts that the
  enqueued command's `workflow_id` and `run_id` equal the started run's.

### 6b. One database, one transaction boundary, one lock order (owner decision A)

Rewritten 2026-11-09 (b); this replaces the D2 text. Decision A supersedes D2.

- **One physical database.** Every Glovo store lives in one Postgres database: the
  bridge (`bridge_commands`, `bridge_read_results`), the work items and `aar_`
  (`action_approval_requests`, `glovo.approval_bindings`), the #988 order tables and
  `glovo.join_refs`, this slice's join tables, and the #959 `glovo.glovo_installs` /
  `glovo.glovo_connections`.
- **Explicit URLs, no fallback.** `GLOVO_DB_URL` (the one `glovo_runtime` pool, shared by the #959 store and the bridge store, #957 §6d.1 R4) and `WORK_ITEMS_DB_URL` must each be set explicitly while Glovo
  is enabled. None falls back to `AUDIT_DB_URL` or to the other. `COMMERCE_DB_URL`
  stays the commerce ledger's and is not a Glovo pool (amended (c)). A missing value is `provider_orders:
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
  migration role and created only through each slice's `ApplySchema` entry point. One
  transaction is one session and therefore one role: the shared transaction runs as the
  single role `glovo_runtime`; `glovo_migrator` owns every object. The role model
  (owner-confirmed 2026-11-09, conditions R1-R5), the only grant table, the existing
  consumers' grants and the startup checks are in §6d.1. Grants govern service access,
  never end-user authority: every write fence still checks tenant and principal, the
  live connection and the `aar_`.

#### Canonical lock order (the only copy; every Glovo slice references it)

| Level | Lock | Mode |
|---|---|---|
| L1 | advisory key `glovo-install/v1\|<tenant>` (#959) | shared for dispatch, cancel, permit, prepare, connect and connection revoke; exclusive for `Install`, `RevokeInstall`, `Reinstall` |
| L2 | advisory key `glovo-owner/v1\|<tenant>\|<principal>` (#959) | shared for prepare, dispatch, cancel and permit; exclusive for #959 connection writes (including revoke) |
| L2a | #961 tenant mutex row `glovo.glovo_rate_counters(scope='tenant_mutex', tenant)` (round 3; the 50-per-tenant connect limit is counted only after it is held) | `FOR UPDATE`, connect and reconnect only |
| L2b | #961 handoff-ref row `glovo.glovo_handoff_refs` (round 3) | `FOR UPDATE`, worker activate only |
| L2c | #957 preview row `glovo.join_previews` (round 4, F1 P3) | `UPDATE ... WHERE consumed_order_ref IS NULL` (row lock), prepare only |
| L3 | #988 order row | `FOR UPDATE` |
| L4 | #989 `aar_` row | `FOR UPDATE` |
| L5 | `bridge_commands` rows | `FOR UPDATE`, `ORDER BY command_id` |
| L6 | #959 connection row | read under L2, no row lock |

A path may skip levels but never takes a lower level after a higher one. Amended (c): L6
is a lock-free read, exempt from that rule, so reading it before L3 is allowed. The only
other waits a Glovo path may take are the unique-index waits of its own inserts
(`glovo.orders`, `glovo.join_refs`, `glovo.join_read_refs`, `glovo.approval_bindings`, `bridge_commands`, and the partial unique indexes `orders_execution`, `orders_approval`, `orders_command`, `join_previews_consumed`) and
the `ApplySchema` advisory keys, which run only under the migration role and never in a
runtime transaction. #989 `CreateGlovoExecutionTx` takes no advisory lock.

| Path | Levels taken, in order |
|---|---|
| #957 prepare | L1 sh, L2 sh, L6 read, L2c (preview claim, step 4b), L3 (new order), L4 (new `aar_`); step 1b is a plain read under L2 |
| #961 connect / reconnect (round 3) | L1 sh, L2 ex, L2a (inside #959's `AfterLocks`) |
| #961 worker activate (round 3) | L1 sh, L2 ex, L2b (inside #959 `ActivateTx`'s `AfterLocks`) |
| #957 read routes (minting refs, then `ReadBridge`) | L1 sh, L2 sh in a short transaction that only mints join refs; the read itself takes L5 on its own read command only (#986); history then inserts `glovo.join_read_refs` (§5a) in a separate short transaction with no lock level |
| #985 dispatch / cancel | L1 sh, L2 sh, L6 read, L3, L4, L5; `Cancel` on `ErrAlreadyCompleted` calls `reconcileOrder` under these same locks (round 7) |
| #985 `read_command_result` (round 7) | L1 sh, L2 sh, L3 (`LockOrderForControl`), then L4 for the two `none` rows of the #985 §2a table; no L5: a terminal command never changes, so `CommandEffect` reads it without a lock |
| Bridge permit | `WriteFence.PreLock` (#989): L1 sh, L2 sh, L3, L4; then `lockOwned`: L5; then `Check` |
| #989 owner decision | L4 only |
| #959 connection enders (`Revoke`, `RevokeForMembership`, `RevokeInstall`, `Reinstall`, `Reconnect` (`superseded`), terminal `Transition`) | L1 (sh, or ex for install changes), L2 ex, connection rows, then the revocation hook `bridge.CancelOpenForConnections`: L5 `ORDER BY command_id`, same transaction |
| Provider claim, result, expiry | L5 only |
| #989 sweeper (replaces an outcome recorder) | L4 `SKIP LOCKED`, then a plain read of the terminal command (no L5) |

Deterministic tests for the races are #985 T-series and #989 T21; this slice adds the
prepare-versus-revoke case (tasks.md T12).

### 6c. Workflow-start outbox (owner D5, owned by this slice)

- Prepare writes `glovo.control_starts(order_ref, workflow_id, input BYTEA NOT NULL, input_digest, state
  pending|started|failed_terminal, attempts, next_attempt_at, started_run_id)` in the
  prepare transaction (amended (c): keyed by the `ordr_`, never the internal `pord_`). `workflow_id` is deterministic from the opaque refs
  (`asst-glovo-<tnr_>-<prr_>-<gin_>-<ordr_>`, the derivation mctl-agents#1044
  re-checks); the input is `GlovoControlInput` with refs, `approval_ref`, fingerprint
  and digests only, never a read payload. Round 5 (R4-2, X-3): the schema of that input is
  owned by mctl-agents#1044 (`glovo-control-input.v1alpha1.json` plus its `SHA256SUMS`, which
  #1044's strict validator also uses). This slice vendors both into
  `internal/glovojoin/contract/` and prepare writes exactly its twelve members:
  `schema_version`, `tenant_ref` (`tnr_`), `principal_ref` (`prr_`), `install_ref`
  (`gin_`), `install_revision`, `connection_ref` (`gcn_`), `order_ref` (`ordr_`),
  `execution_id` (`we_`), `work_item_id` (`wi_`), `approval_ref` (`aar_`), `fingerprint`
  and `limits`. `limits` is whatever the vendored schema defines: this slice copies its
  members and values verbatim from the schema's published defaults and invents none
  (OPEN-957-11 asks the #1044 AMEND to enumerate them). The encoding is canonical JSON
  (RFC 8785).
- Round 4 (F2): the `input` column holds that canonical JSON itself, written in the
  prepare transaction from values prepare already holds (`tnr_`/`prr_` from `MintJoinRefTx`,
  `gin_` from the preview row's `install_id`, `gcn_` from the live connection, `wi_`/`we_`
  from #989, the `aar_`, the fingerprint and `limits`). `CHECK (input_digest = 'sha256:' || encode(sha256(input),
  'hex'))`. The column is INSERT-only: it is not in the `UPDATE` list of §6d.1, so a runtime
  bug cannot rewrite it. The dispatcher sends the stored bytes verbatim after re-computing
  the digest (a mismatch is `failed_terminal` plus an audit event, never a rebuilt input) and
  reads nothing from the order, join-ref or connection stores, so it needs no caller scope.
  Test (tasks A13, T11): a Go test validates the stored `input` of a real prepare against the
  vendored schema and compares it with the checked-in golden
  `internal/glovojoin/contract/testdata/control-input.golden.json` (the same file #1044's CI
  is asked to consume, OPEN-957-11); after a crash between commit and start, the dispatcher starts the
  workflow from the stored row alone, with every other store stubbed to fail.
- After commit, a separate dispatcher in mctl-api claims due rows (`FOR UPDATE SKIP
  LOCKED`), starts the workflow with that id and the id-reuse policy "reject duplicate",
  and CAS-updates the row to `started` with the run id. "Already started" with the same id
  is success. Transient errors back off with a bounded attempt count; it never starts a
  workflow for an uncommitted order and never invents an id.
- The dispatcher runs only when `GLOVO_CONTROL_START_ENABLED=true` (default off) and a
  Temporal client for the control namespace is configured; that client is gated by the
  Temporal security path (crosswalk §4, nodes A-I). Until then rows stay `pending` and
  `/compatibility` reports `control_worker: not_ready`.

### 6d. Cross-slice seams (canonical, added 2026-11-09 (c))

This section is the only copy of the role and grant table, the execution binding, the
approval-basket source and the interface list of the Glovo M1 slices. #959, #985, #986,
#988 and #989 reference it and do not restate it. A change to any of them is a change
here, in the same PR as the slice that needs it.

#### 6d.1 Roles and grants (owner decision A, role model confirmed by the owner 2026-11-09)

Owner decision A says "one database does not mean one privileged runtime user". The
owner confirmed on 2026-11-09 the reading below, with five mandatory conditions (R1-R5).
One transaction is one session and therefore one role. In every Glovo M1 proposal,
"the migration role" means `glovo_migrator` and "the (Glovo) runtime role" means
`glovo_runtime`.

- **R1 `glovo_runtime`**, the one dedicated role for Glovo transactions. It has only the
  DML this table lists, on the Glovo tables and on the named shared bridge, work-items
  and `aar_` objects. It is not superuser, `CREATEROLE`, `CREATEDB` or `BYPASSRLS`; it
  owns nothing and is not a member of any owning role; it has no `CREATE` on any schema
  and no `TRUNCATE`, `TRIGGER` or `REFERENCES`, so it cannot run DDL or disable a
  trigger. The role name is configuration, passed to every `ApplySchema` as
  `runtimeRole` (`^[a-z_][a-z0-9_]{0,62}$`); `glovo_runtime` is the default.
- **R2 `glovo_migrator`**, a separate role that creates and owns schema `glovo` and every
  object in it, the bridge tables and (OPEN-989-1, extended) `action_approval_requests`,
  `work_items`, `work_item_executions` and `work_item_events`. It applies all DDL and
  all grants, only through the `ApplySchema` entry points, in this order:
  `glovo.ApplySchema` (#959) → `orders.ApplySchema` (#988) →
  `workitems.ApplyGlovoApprovalSchema` (#989) → `bridge.ApplySchema` (#985; it calls #986's
  `bridge.ApplyReadSchemaTx(ctx, tx, runtimeRole)` for the read objects, round 4 X-3) →
  `glovojoin.ApplySchema` (this slice). Every entry point has the shape `ApplySchema(ctx,
  migrationConnStr, runtimeRole string) error` (round 4, X-2). Each runs
  `CREATE SCHEMA IF NOT EXISTS glovo` and refuses to continue when the schema or an
  object it would create is owned by another role. Its credentials are used only by the
  migration job (#985 task 4); they are never mounted into the mctl-api runtime, the
  control worker, the facade or any agent or DevLoop environment.
- **R3 other subsystems.** No other role gets any privilege on schema `glovo` or a
  Glovo table. On shared tables, a role keeps only the grants listed under "Existing
  consumers" below, each with its reason. Existing consumers keep working as stated
  there; a test per consumer proves it.
- **R4 one transaction, one pool, one role.** Prepare, approval decision, revoke,
  cancel, dispatch and the fence run on one `pgx.Tx` from one pool connected as
  `glovo_runtime`. With Glovo enabled that pool is opened from `GLOVO_DB_URL`, and both
  the #959 store and the bridge store use it (`bridge.NewRuntimeStore(ctx, pool)`).
  `COMMERCE_DB_URL` stays the commerce ledger's URL and role (`cmd/api/main.go:563`)
  and is never `glovo_runtime`; the bridge reads it (`main.go:1019`) only while Glovo
  is disabled. Equal URLs, or one physical database, are not proof: the proof below is.
- **R5 startup checks and negative tests**, below. Any mismatch is `not_ready` with zero
  provider writes.

**Merge order (round 5, X-1; the one statement, every proposal matches it; no cycle).**
mctl-agents#1059, then #959 (it ships `glovo.Owner`, `glovo.Connection`, the `glovo.Code`
enum, `dbq.Querier` and `glovo.expectedGrants` with `glovo.RegisterGrants`), then #988 (it
ships `internal/jcs`; it vendors the #1059 vectors from a pinned #1059 commit, so there is
no cycle), #960, #961, #989, this slice's non-read PRs (A13 `glovo.control_starts`, A14 `glovojoin.ApplySchema` and `glovojoin.ControlStartTx`; they need only #959, #988 and #989, round 6, G3), #986 (it ships `bridge.ApplyReadSchemaTx` and tests it
standalone on a database built from today's `bridgeSchema`), #985 (`bridge.ApplySchema` calls
the #986 function; it consumes `glovojoin.ControlStartTx`), then this slice's read routes. Package direction: `internal/glovo/control` imports `glovojoin`, never the reverse; `glovojoin.Readiness` takes the `control.ProveOneDatabase` result as a `func(context.Context) error` that `main.go` injects, so `glovojoin` does not import `control`. A slice that lists another slice as a
dependency uses a test double until that slice merges, and answers `not_ready` meanwhile.

**Bridge startup DDL (mandatory AMEND, owned by #985).** At `ceac9ed` (= origin/main)
`bridge.NewStore` runs `bridgeSchema` on every start (`internal/bridge/store.go:365-379`,
the `Exec` at `:374`), and `cmd/api/main.go:1027` is its only runtime caller.
`OpenExistingStore` (`:381-404`) already opens without DDL, for `cmd/bridge-scrub`.
#985 tasks 3a and 4 split them: `bridge.ApplySchema(ctx, migrationConnStr,
runtimeRole)` under `glovo_migrator`, and `bridge.NewRuntimeStore` that only checks the
schema version and the grants. `glovo_runtime` is never given `CREATE`, ownership or any
extra right to make the old `NewStore` pass.

*Mode selector (round 3, #985 F2).* One selector, no flag: `bridge.ApplySchema` creates
`bridge_schema_version` (a single-row table, `SELECT` for `glovo_runtime`) and writes the
version it applied. `main.go` decides the mode once at startup (round 4, #985 F3): it probes
`to_regclass('public.bridge_schema_version') IS NOT NULL` on `GLOVO_DB_URL` when that is set,
else on the legacy bridge DSN (`COMMERCE_DB_URL`, as today). `to_regclass` needs no table
privilege, so the probe works for the old bridge role that no longer owns the tables; the
version value is read afterwards by `NewRuntimeStore` through the runtime role (`SELECT` on
the table, granted by `ApplySchema`). Table present and `GLOVO_DB_URL` unset, or any probe or
version-read error: the bridge is `not_ready`, and neither case ever falls back to
`NewStore`. Row
present: the bridge always runs on `NewRuntimeStore` over the shared `GLOVO_DB_URL` pool,
whatever `GLOVO_ENABLED`, `GLOVO_JOIN_ENABLED` or `MCTL_GLOVO_CONTROL_ENABLED` say, so
unsetting a Glovo flag never switches the bridge back to a `NewStore` that would run DDL on
migrator-owned tables or move the bridge to another database. Row absent (a deployment that
never ran the migrator): `NewStore` is unchanged. A bridge whose tables already exist under
another owner (created earlier by `NewStore`) makes `ApplySchema` refuse with an explicit
error naming the tables, and leaves them untouched; the one-time ownership transfer is an
operator step (OPEN-957-6, requirements.md Open questions). A missing or old schema on the runtime path is `not_ready`.

**Grants do not replace authority checks.** SQL grants decide which service may touch
which table. They do not decide what an end user may do. Every write fence still checks
the tenant and principal, the live connection (#959 `LiveConnectionTx` under L2) and the
`aar_` (#989 fence) on each write, whatever role runs it.

The only grant table for `glovo_runtime`. Every right not listed is absent.

| Object | Creator (`ApplySchema` of) | `glovo_runtime` |
|---|---|---|
| schema `glovo` | every slice (`IF NOT EXISTS`) | `USAGE` |
| `glovo.glovo_installs`, `glovo.glovo_connections` | #959 | `SELECT, INSERT, UPDATE` |
| `glovo.glovo_connect_requests` | #959 | `SELECT, INSERT, UPDATE`, `DELETE` (round 3: the 24 h cleanup is #961's `Sweep`) |
| `glovo.glovo_audit_events` | #959 | `SELECT, INSERT` |
| `glovo.glovo_pilot_allowlist` | #959 | `SELECT, INSERT, DELETE` |
| `glovo.glovo_handoff_refs` | #961 | `SELECT, INSERT, UPDATE (consumed_at)`, `DELETE` (TTL purge and #959 `endConnection` purge of unconsumed rows) |
| `glovo.glovo_rate_counters` | #961 | `SELECT, INSERT, UPDATE (count, updated_at)`, `DELETE` (stale windows) |
| `glovo.join_refs`, `glovo.order_snapshots`, `glovo.order_effects`, `glovo.order_events` (+ `USAGE` on its sequence) | #988 | `SELECT, INSERT` |
| `glovo.orders` (+ the BEFORE INSERT guards of #988 §3 on `orders` and `order_effects`) | #988 | `SELECT, INSERT`, `UPDATE (state, final_basket_fingerprint, final_snapshot_seq, approval_ref, command_id, version, updated_at)` |
| `glovo.approval_bindings` | #989 | `SELECT, INSERT`, `UPDATE (command_id)` |
| `public.action_approval_requests` | #989 (ownership move, OPEN-989-1) | `SELECT, INSERT`, `UPDATE (state, decided_by, decided_at, reason, decided_by_principal_id, decided_via_principal_id, decided_context_digest, authority_basis, authz_mode, fresh_until, consumed_at, reserved_at)` (round 3, the only copy of the list; it is exactly what `DecideGlovoApprovalTx` (the first ten columns incl. `state`), `ConsumeGlovoApprovalTx` (`state`, `consumed_at`), `ReserveGlovoApprovalTx` (`state`, `reserved_at`), `RevokeGlovoApprovalTx` (`state`, `decided_by`, `decided_at`, `reason`) and `MarkGlovoApprovalUnknownTx` (`state`) write; no `executed_at`, no identity or policy column). #989 design §2 and `ApplyGlovoApprovalSchema` reference this row |
| `public.work_items`, `public.work_item_executions`, `public.work_item_events` | #989 (ownership move, OPEN-989-1) | `SELECT, INSERT` |
| `glovo.join_previews` | #957 | `SELECT, INSERT, DELETE` (the bounded expiry sweeps), `UPDATE (consumed_order_ref)` (round 4, F1 P3) |
| `glovo.join_scope_refs`, `glovo.join_read_refs` | #957 | `SELECT, INSERT, DELETE` (the bounded expiry sweeps) |
| `glovo.control_starts` | #957 | `SELECT, INSERT`, `UPDATE (state, attempts, next_attempt_at, started_run_id, updated_at)` (`input` and `input_digest` are INSERT-only, round 4 F2) |
| `bridge_commands`, `bridge_signal_outbox` | #985 (`bridge.ApplySchema`) | `SELECT, INSERT, UPDATE` |
| `bridge_command_transitions`, `bridge_write_permits` (+ sequences) | #985 | `SELECT, INSERT` |
| `bridge_read_results`, the read columns of `bridge_commands` (`wire_version`, `read_request_id`, `install_revision_ref`) | #986 (`bridge.ApplyReadSchemaTx`, called by #985 `bridge.ApplySchema`) | `SELECT, INSERT, DELETE`, `UPDATE (data, erased_at)` on the results table; the `bridge_commands` table-level grant above covers the new columns |
| `bridge_colocation_probe` | #985 | `SELECT, INSERT, DELETE` |
| every `*_schema_version` table | its slice | `SELECT` |

Every `glovo.*` row of this table is mirrored by the Go registry `glovo.expectedGrants`,
owned by #959 (round 5, #959 P2-3 / #988 F2). The one registration path is
`glovo.RegisterGrants(rows ...GrantRow)`, which each slice calls from its own package
`init` for its own tables, in its own PR; the checked-in file
`internal/glovo/testdata/grants.golden` is the source this table is verified against (the
slice PR that adds rows updates both). The #959 `Ready` check reports `not_ready` only for
an existing `glovo` table that has no registered row (an unknown table is never "fine"); a
row whose table does not exist yet is skipped.

**Existing consumers** (R3). These are the only grants to other roles, each issued by
the creating slice's `ApplySchema`:

| Role | Grants | Why, and how it keeps working |
|---|---|---|
| work-items role (`WORK_ITEMS_DB_URL`) | `SELECT, INSERT, UPDATE` on `work_items`, `work_item_executions`, `work_item_events`, `action_approval_requests`, as its existing statements use them; `SELECT` on `bridge_colocation_probe` | Generic work items and action approvals keep running. Once `glovo_migrator` owns these tables (OPEN-989-1), `workitems.NewStore` stops running DDL when it does not own them and only checks the schema version (#989 task 2b). The Glovo guards act only on Glovo-kind rows, and a Glovo-kind write by any role other than `glovo_runtime` is refused by `glovo.aar_guard()`. The existing work-items suite runs unchanged against the migrated schema under this role. No privilege on schema `glovo` |
| commerce ledger role (`COMMERCE_DB_URL`) | none from this table | Untouched: it keeps its own tables and URL; it is never the bridge pool while Glovo is enabled |
| bridge maintenance role (`MCTL_BRIDGE_SCRUB_DATABASE_URL`, `cmd/bridge-scrub`) | `SELECT`, `UPDATE (result)` on `bridge_commands` | `ScrubLegacyResultBatch` (`internal/bridge/store.go:949`) needs exactly this; it already opens through `OpenExistingStore`, without DDL |
| bridge role while Glovo is disabled | unchanged | `NewStore` keeps its behaviour; once `bridge.ApplySchema` has run, the deployment uses `NewRuntimeStore` only |

There is no `SECURITY DEFINER` function: `glovo_runtime` already holds the
`bridge_commands` rights the revocation hook needs, so the hook is a plain Go function on
the revoker's transaction (#985 `bridge.CancelOpenForConnections`).

**Startup checks** (#985 `control.ProveOneDatabase` step 4, and each slice's `Ready`;
any miss is `not_ready`, zero provider writes):
- `current_user` of the Glovo pool equals the configured `runtimeRole`, and the #959
  store and the bridge store hold the same pool (`glovoStore.Pool() == bridgeStore.Pool()`, pointer equality; #959 `NewStore` takes that pool and opens none, round 3);
- `has_schema_privilege`, `has_table_privilege` and `has_column_privilege` reproduce
  the `glovo_runtime` table exactly: every listed DML right is present and nothing
  beyond it; no `CREATE` on any schema, no `TRUNCATE`, `TRIGGER` or `REFERENCES`;
- `rolsuper`, `rolcreaterole`, `rolcreatedb` and `rolbypassrls` are false, and
  `NOT pg_has_role(current_user, <owner>, 'MEMBER')` for every Glovo table, shared
  table above and trigger function;
- every required object exists (`to_regclass`) with its schema version, and every guard
  trigger of each slice's inventory is present and enabled (`tgenabled = 'O'`; #988 §3 `triggerInventory`; #985 `ProveOneDatabase` step 4 runs this check with the role-attribute check, round 3);
- the work-items pool's `current_user` differs from `runtimeRole` and has no `USAGE`
  on schema `glovo`; the colocation probe shows one physical database.

**Negative tests** (#985 T26, #989 T15b, #959 T16): a runtime role with an extra
`TRIGGER`, `CREATE` or ownership, or a missing DML right, is `not_ready`; the wrong
`current_user` is `not_ready`; the work-items role and the commerce role are refused on
every `glovo.*` table, and the work-items role is refused a Glovo-kind `aar_` insert or
update by `glovo.aar_guard()`; `glovo_runtime` cannot `ALTER TABLE … DISABLE TRIGGER`,
`CREATE TABLE` or `DROP`; with `NewRuntimeStore` no DDL statement is sent (statement
log); in every case the fake provider sees zero writes.

#### 6d.2 Execution binding (`wi_`/`we_`), workflow id, run id and refs

- **Owner: #989**, the slice that extends `internal/workitems`.
  `CreateGlovoExecutionTx(ctx, tx pgx.Tx, in GlovoExecutionInput{Tenant,
  OwnerPrincipalID, WorkflowID, Actor}) (workItemID, executionID string, err error)`
  inserts one `work_items` row (owner = the principal, origin surface `glovo`), one
  creation event and one `work_item_executions` row (engine `temporal`, `engine_ref` =
  `WorkflowID`, attempt 1) on the caller's transaction. Ids are `wi_`/`we_` plus 26
  characters from the bridge `randAlnum` alphabet, so they match
  `^we_[A-Za-z0-9]{16,40}$` and `^wi_[A-Za-z0-9]{16,40}$` (`internal/bridge/store.go:164-165`).
  It begins no transaction and takes no advisory lock: the generic `withTx` lock
  (`internal/workitems/store.go:266-272`) is not taken, because the rows are new and
  their primary keys guard them.
- Generic ids are `wi_`/`we_` plus a hyphenated UUID (`store.go:395`, `:676`). They never
  match the bridge patterns or the #988 `execution_id` CHECK, so a Glovo order can bind
  only a `we_` from `CreateGlovoExecutionTx`. A test uses an id from the real store.
- `ExecutionBindingTx(ctx, q Querier, executionID string) (tenant, ownerPrincipalID,
  workItemID, workflowID string, err error)` (#989) is the #988 `Executions`
  collaborator. There is no separate adapter.
- #988 `Create` takes `ExecutionID` in `CreateInput`, calls `ExecutionBindingTx`,
  requires tenant and owner to equal the order's, and writes `execution_id` once at
  insert. `Order.ExecutionID` is therefore set from the first row. `RecordEffect` is
  withdrawn; #988 `MarkDispatched` writes the `place_order_fake` effect row.
- `EnqueueInput` for #985: `WorkflowID` from `ExecutionBindingTx` (equal to
  `glovo.control_starts.workflow_id`; a difference is `unavailable`), `RunID` from
  `glovojoin.ControlStartTx(ctx, q, orderRef) (workflowID, runID string, err error)`.
  An empty run id is valid (`bridge_commands.run_id` defaults to `''`,
  `internal/bridge/store.go:74`): the result signal then goes to the workflow id's
  current run, and the "reject duplicate" id reuse policy (§6c) allows only one.
  `TenantRef`/`PrincipalRef` from #988 `LookupJoinRefTx`; `OrderRef` is the order's
  `ordr_`; `ConnectionRef` its `gcn_`.

#### 6d.3 Approval-basket source

- Preview time: the handler validates the #986 result, extracts the `approval_basket`
  member, runs #988 `basket.Parse` on its bytes (raw pre-check, closed schema, sort,
  uniqueness, arithmetic) and stores the JCS bytes and their fingerprint in
  `glovo.join_previews` (§5). The read-result TTL does not bound the preview.
- Prepare time: the stored bytes are snapshot 1 of the #988 order and, unchanged, the
  `place_order_fake` payload that #985 enqueues.
- **The write payload is exactly the approval basket.** `JCS(bridge_commands.payload)`
  must equal the order's final snapshot bytes. There is no wrapper object and no other
  top-level field. The #989 fence runs `basket.Parse` on the payload, so an extra field,
  a missing field or any other shape is `basket_changed`. The schema is owned by
  mctl-agents#1059 (`command-place-order-fake.schema.json`, `bridge.mctl.ai/v1alpha2`),
  vendored and gated by mctl-api#986 §2a (round 7; not #985); #1059 OPEN-1059-1 is closed.
- An empty basket or an all-unavailable preview is a valid read (#1059 `empty: true`)
  with no approval basket. It can be shown, never fingerprinted, prepared or approved.

#### 6d.4 Interfaces, one list per providing slice

Consumers use exactly these names, arguments and transaction semantics. "tx" means the
method runs on the caller's `pgx.Tx` and never begins, commits or rolls back.

| Provider | Method | Semantics |
|---|---|---|
| #959 `glovo.Store` | `NewStore(ctx, pool *pgxpool.Pool, runtimeRole, migrationRole string, opts ...Option) (*Store, error)`, `Pool() *pgxpool.Pool`, `WithExplicitURL(bool) Option` | round 3: the shared `GLOVO_DB_URL` pool, no pool of its own; `Ready` compares `current_user` with `runtimeRole`, every owner with exactly `migrationRole` (round 5, as #988), and fails without `WithExplicitURL(true)` |
| | `type Querier` in package `internal/glovo/dbq` (`Exec`, `Query`, `QueryRow`; satisfied by `*pgxpool.Pool` and `pgx.Tx`) | round 5 (#988 F3): the one definition, created by #959 task 1. Every bare `Querier` in these proposals means `dbq.Querier`; #988's own `orders.Querier` is deleted. `glovo.Owner`, `glovo.Connection` and the `glovo.Code` constants are created by #959 task 1 and only used elsewhere |
| | `GetInstall(ctx, tenantID string) (*Install, error)` | round 5 (R4-1): the one source of install id (`gin_`) and install revision. No lock, one statement; absent or `uninstalled` is `no_install`. The #957 resolver calls it once per request after #960 `Resolve`; a `scope_ref` whose revision differs is `stale_install` |
| | `ActivateTx(ctx, tx, in ActivateInput{..., ExpiresIn time.Duration})`, `ConnectInput.AfterLocks`, `ConnectInput.TerminalOnly`, `AppendRefusal(ctx, ev)` | round 3, for #961: tx-scoped activation `pending_handoff -> pending_provider -> active`; SQL sets `expires_at = clock_timestamp() + ExpiresIn` (`<= 0` or `> 24h` is `invalid_request`, round 4); hook after L1/L2; terminal-only reconnect; refusal audit |
| | `LockOwnerShared(ctx, tx pgx.Tx, tenant, principal string) error` | tx; L1 shared, then L2 shared |
| | `LiveConnectionTx(ctx, tx pgx.Tx, owner glovo.Owner) (*glovo.Connection, error)` | tx; no row lock; caller holds L2; `expires_at <= clock_timestamp()` (statement time, round 4; `now()` is the transaction start and would let a long transaction permit after expiry) is `connection_expired` even before any `Transition` |
| | `WithRevocationHook(h glovo.RevocationHook) Option`, `type RevocationHook func(ctx, tx pgx.Tx, ended []string, actor string) error` | every path that ends a connection calls it on its own transaction |
| | `WithMembershipRevoker(name string) Option`, `MembershipRevocationWired() bool` | true only when the slice that detects a membership removal registered itself (OPEN-985-2) |
| | `Ready(ctx) error` | `revocation_hook_missing` when no hook is installed; `end_purger_missing` when `WithEndPurgerRequired(true)` and none installed; `not_ready` for an existing `glovo` table with no `glovo.expectedGrants` row (round 4) |
| | `GetConnectionForWorker(ctx context.Context, connectionID string) (*glovo.Connection, error)` | round 4, for #961: read by id with no owner predicate, worker routes only (source-scan test); the caller then calls the locked primitives with the Owner and `ExpectedVersion` it read |
| | `type EndPurger func(ctx, tx pgx.Tx, ended []string) error`, `WithEndPurger(p EndPurger) Option`, `WithEndPurgerRequired(bool) Option`, `EndPurgerInstalled() bool` | round 4: the ended-connection purge of #961's `glovo_handoff_refs` is installed by #961; #959 names no #961 table |
| | `glovo.expectedGrants` (registry), `glovo.RegisterGrants(rows ...GrantRow)`, `ApplySchema(ctx, migrationConnStr, runtimeRole string) error` | round 5: Go mirror of the `glovo.*` rows of §6d.1, owned by #959 and filled by each slice through `RegisterGrants`; verified against `internal/glovo/testdata/grants.golden`. `ApplySchema` of every slice refuses a foreign-owned object, a recorded version above the compiled one, and quotes role names with `pgx.Identifier` |
| #961 `connect.Service` | `Connect(ctx, sc JoinScope, idempotencyKey string) (*ConnectOutcome, error)`, `Current(ctx, sc JoinScope) (*glovo.Connection, error)`, `type JoinScope struct{ Tenant, PrincipalID string; InstallRevision int64 }` | round 4, X-1: the only backing calls of `POST /connections` and `GET /connection` (§3); `Current` answers `no_connection` when none; a `Connect` replay returns the same connection and a fresh `handoff_url` |
| #988 `orders.Store` | `NewStore(ctx, pool *pgxpool.Pool, runtimeRole, migrationRole string, conns Connections, execs Executions) (*Store, error)`, `Ready(ctx) error`, `ApplySchema(ctx, migrationConnStr, runtimeRole string) error` | round 4 (N4): `Ready` compares every owner with exactly `migrationRole`; `JoinKind`, `ActorKind` and `Snapshot` are defined in #988 §1 |
| | `AppendSnapshot(ctx, tx, sc Scope, a Actor, orderRef string, expectedVersion int64, b basket.Approval, expectedFP string) (*Snapshot, error)`, `Get(ctx, q Querier, sc Scope, orderRef string) (*Order, error)`, `LockOrder(ctx, tx, sc Scope, orderRef string) (*Order, error)`, `ScopeFromRefs(ctx, q Querier, tenantRef, principalRef string) (Scope, error)` | `AppendSnapshot`, `Finalize`, `BindApproval` and `Create` re-read the live connection on the caller's tx; `MarkCancelled`, `MarkUnknown` and `MarkDispatched` do not (#988 §6, round 4 N2). `LockOrder` is the owner-path L3 |
| | `NewOrderRef() string`, `LookupByIdempotencyKey(ctx, q Querier, sc Scope, key string) (*Order, error)` | round 3: the `ordr_` is minted by prepare and passed in; read-only replay lookup (not_found on a miss) |
| | `Create(ctx, tx, in CreateInput) (*Order, bool, error)` (`CreateInput.OrderRef` required), `Finalize(ctx, tx, sc Scope, a Actor, orderRef string, expectedVersion int64, expectedFP string) (*Order, error)` | tx; owner path |
| | `BindApproval(ctx, tx, sc Scope, a Actor, orderRef, approvalRef string) error` | tx; called by #989 with `Scope{Tenant, PrincipalID: owner}` and `Actor{Kind: system, ID: "service:glovo-prepare"}` |
| | `PeekOrderScope(ctx, q Querier, orderRef string, tenants []string) (Scope, error)` | unlocked read of write-once columns |
| | `LockOrderForControl(ctx, tx, orderRef string, tenants []string) (*Order, error)` | tx; L3. #985 passes its credential's `Tenants`; the #989 fence passes `[]string{command.tenant}` |
| | `MarkDispatched(ctx, tx, o *Order, commandID string, a Actor) error`, `MarkCancelled(...)`, `MarkUnknown(...)`, `MarkClosed(...)` | tx; `MarkDispatched` also writes the effect row; `MarkClosed` is `dispatched -> closed` only, called by #985 `read_command_result` (round 6, G2) |
| | `Snapshot(ctx, q Querier, sc Scope, orderRef string, seq int) (*Snapshot, error)` | `Snapshot.Canonical` holds the JCS bytes |
| | `MintJoinRefTx(ctx, tx, kind JoinKind, tenant, principalID, subjectID string) (string, error)` (kinds `tenant`, `principal`, `install_revision`; there is no `order` kind), `LookupJoinRefTx(ctx, q Querier, kind JoinKind, tenant, principalID, subjectID string) (string, error)` | mint is insert-or-read; lookup is read-only, `not_found` if never minted |
| | `basket.Parse(raw []byte) (Approval, []byte, error)`, `basket.Fingerprint(canonical []byte) string` | the only entry points; `Parse` returns the JCS bytes |
| #989 `workitems.Store` | `CreateGlovoExecutionTx`, `ExecutionBindingTx` | §6d.2 |
| | `ApplyGlovoApprovalSchema(ctx, migrationConnStr, runtimeRole string) error` | round 4, X-2: the same shape as every other `ApplySchema`; creates the `aar_guard` with `runtimeRole` as a literal and issues the grants of §6d.1 |
| | `CreateGlovoApprovalTx(ctx, tx, in GlovoApprovalInput) (*ActionApprovalRequest, bool, error)` | tx; calls #988 `BindApproval`. `GlovoApprovalInput{Tenant, OwnerPrincipalID, WorkItemID, ExecutionID, OrderRef, ConnectionRef, InstallID, InstallRevision, BasketFingerprint, Provider, ExpiresIn}` is defined in #989 §4. Prepare passes `ExpiresIn = GlovoApprovalTTL`, the named constant `15 * time.Minute` (the OPEN-957-10 recommendation; only the owner changes it; it is at most `MaxApprovalTTL` and far below #1044's 2 h `execution_timeout`) (SQL stores `clock_timestamp() + ExpiresIn`), and returns the stored value as `expires_at`; #1044 bounds its approval wait by it. The row's `artifact_hash` is the basket fingerprint (#989 §3) |
| | `LockGlovoApprovalTx(ctx, tx, id string) (*ActionApprovalRequest, *GlovoBinding, error)` | tx; L4 |
| | `ReserveGlovoApprovalTx(ctx, tx, id string, cmd ReserveCommand) (replayed bool, err error)` | tx; `ReserveCommand` is defined once in #989 §4 |
| | `ConsumeGlovoApprovalTx`, `RevokeGlovoApprovalTx`, `MarkGlovoApprovalUnknownTx`, `DecideGlovoApprovalTx` | tx; #989 §4 |
| | `GlovoApprovalStatus(ctx, q Querier, tenants []string, id string) (*GlovoApprovalStatus, error)` | round 3: a read on the caller's `Querier`, which is the `glovo_runtime` pool (or the prepare/dispatch `pgx.Tx`), never the work-items pool, whose role has no privilege on schema `glovo` (R3). Used by `glovo_order_status`, #985 `read_approval` and the prepare replay |
| | `GlovoApprovalForDecision(ctx, q Querier, id string) (*ActionApprovalRequest, *GlovoBinding, error)` | round 3: the Glovo-kind pre-read of the decision route and of `canSeeActionApproval`'s owner rule, on the `glovo_runtime` pool; the generic `aar_` row is first read through the work-items pool, and only a Glovo kind goes on to this read |
| | `receipt.NewFence(...)`, `receipt.Ready(ctx) error` | #989 §6, §8 |
| #985 bridge and control | `bridge.CancelOpenForConnections(ctx, tx pgx.Tx, connectionIDs []string, actor string) error` | the `RevocationHook` implementation; L5 `ORDER BY command_id` |
| | `bridge.WriteFence.PreLock(ctx, tx pgx.Tx, c bridge.Caller, commandID string) error` | called by `permitTx` before `lockOwned`; step 0 applies `lockOwned`'s provider and tenants predicate and answers `ErrCommandNotFound` for absent and foreign ids alike, and refuses non-`place_order_fake` kinds, before any lock (#985 §7.2, #989 §6) |
| | `bridge.ApplySchema(ctx, migrationConnStr, runtimeRole string) error`, `bridge.NewRuntimeStore(ctx, pool *pgxpool.Pool) (*Store, error)` (the shared `GLOVO_DB_URL` pool; no DDL) | §6d.1; `ApplySchema` calls #986 `bridge.ApplyReadSchemaTx` (round 4, X-3) |
| | `bridge.Store.CommandEffect(ctx, q dbq.Querier, tenants []string, commandID string) (status, effectState string, err error)` | round 6, G2, round 7: read-only; Glovo `place_order_fake` commands inside `tenants` only, anything else `not_found`; returns the pair that keys the #985 §2a table and §3a |
| | `Dispatcher.Dispatch` replay | round 4 (#985 F2): on any order state with a non-empty `command_id` whose `approval_ref` and fingerprint match, the same `cmd_` with the current `order_state` and `effect_state` |
| | `control.ProveOneDatabase(ctx, bridgeStore *bridge.Store, glovoStore *glovo.Store, workItemsPool *pgxpool.Pool) error` | §6d.1 checks; requires `glovoStore.Pool() == bridgeStore.Pool()` (round 3: two stores, one pool, one role) and proves `workItemsPool` is the same database through the colocation probe |
| #960 (`internal/glovo/scope`, `internal/auth`) | `Resolver.Resolve(ctx, u *auth.User) (Scope, *glovo.Error)`, `User.TeamGrant() (grantID, tenant string, ok bool)`, `teamgrant.Check(ctx, grantID, principalID, clientID, resource) (teamgrant.Grant, error)` (only an `active` grant passes) | round 3: sole owner of consent-time selection and of the claims `tgr`/`stn`. Round 5 (R4-1): #960 defines `teamgrant.Grant{ID, PrincipalID, Tenant, ClientID, Resource, RefreshFamilyID, State}`; `Grant.RefreshFamilyID` is the `scope_ref` binding key (§2b) and is the only place #957 reads it |
| #986 bridge reads | `ReadClient.Read(ctx, ReadRequest) (*ReadResult, error)`, `Store.FetchReadResult(ctx, ReadFetch) (*ReadResult, error)` | own short transactions; the authoritative read binding check |
| | `bridge.ApplyReadSchemaTx(ctx, tx pgx.Tx, runtimeRole string) error` | round 4, X-3: the one owner of the read DDL (`bridge_read_results`, the three read columns of `bridge_commands`, the read-shape CHECK, the read level table `bridge_read_schema_version`) and `bridge.CheckReadLevel(ctx, q Querier) error`; called by #985 `bridge.ApplySchema`; tested standalone |
| #988 `internal/jcs` | `Canonicalize(raw []byte) ([]byte, error)`, `Precheck(raw []byte) error` | round 4, X-3/N3: the one RFC 8785 implementation; #986 imports it |
| #957 (this slice) | `glovojoin.ControlStartTx(ctx, q Querier, orderRef string) (workflowID, runID string, err error)`, `glovojoin.ApplySchema(ctx, migrationConnStr, runtimeRole string) error` | read; DDL |

### 7. Contract package (shared with mctl-telegram)

- `internal/glovojoin/contract/glovo-facade-mctl-api.v1alpha1.json`: the version, the
  route matrix, the request and response JSON Schemas (draft 2020-12,
  `additionalProperties: false`), the refusal table, the idempotency rules, the rate
  limits, the timeouts (5 s), the OAuth resource metadata expectations (`resource`,
  `scopes_supported`, `bearer_methods_supported: ["header"]`) and `dependencies` version
  gates (minimum M1a and M1b schema versions, bridge `bridge.mctl.ai/v1alpha1` schema
  digests as vendored at `a9ca5814`, and (round 7) the digest of `command-place-order-fake.schema.json`
  as vendored by #986; amended 2026-11-09).
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

Round 8: the same tag also selects #985's `gate_fixture.go` (opens the const-closed control
gate only) and the TTL overrides: #985 owns `SetFixtureDispatchCommandTTL`, this slice owns
`internal/glovojoin/ttl_release.go` / `ttl_fixture.go` with `SetFixtureGlovoApprovalTTL(d)`
(release: `const GlovoApprovalTTL = 15 * time.Minute`; fixture: a `var`). Connection expiry
needs no override variable (#985 §7.4). The tag never skips a precondition of #985 §7.3.

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

- **Migrations:** only the four tables `glovo.join_previews`, `glovo.join_scope_refs`,
  `glovo.join_read_refs` and `glovo.control_starts` (the join-ref table is #988's
  `glovo.join_refs`), created by `glovojoin.ApplySchema` under the migration role, last in
  the §6d.1 order, with the grants of the §6d.1 table and nothing more. They are additive.
  This slice changes no OAuth table: consent-time team selection, its grant table and its
  columns are #960's (round 4, F3).
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
