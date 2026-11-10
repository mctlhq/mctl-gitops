# Design: issue-1044-feat-assistants-m1-trusted-glovo-control

## Amendment 2026-11-10 (independent review, AMEND): contract reconciliation against current main

Sources re-read on default branches: mctl-api `081bd6b7` (control routes #985 merged earlier,
#1001 merged as `675dff75`), mctl-agents main (#1062 merged as `46ccddce`), mctl-gitops main.
These items replace the text they name below; where this section and older text disagree, this
section wins. Items marked UNVERIFIED could not be confirmed against code and stay assumptions.

1. Contract names. mctl-api `internal/glovojoin/prepare.go` (`ControlInputSchemaVersion`) and
   `internal/glovojoin/contract/testdata/control-input.golden.json` use
   `glovo-control-input/v1alpha1` for the input. The result is `glovo-control-result/v1alpha1`
   (no mctl-api code reads it; owned here). `assistants.mctl.ai/glovo-control/v1alpha1` is dropped.
   prepare.go marks the version and `ControlLimits` (currently `{}`) as provisional until this
   schema is vendored, so `limits` members are all optional with defaults and bounds, and
   `limits: {}` is valid; unknown members are still rejected.
2. Start contract. Workflow type `GlovoControlWorkflow`, task queue `mctl-assistants-control`,
   exactly one argument of type bytes: the RFC 8785 bytes (as stored in
   `glovo.control_starts.input`). The strict raw-text pre-check (duplicate keys, non-integer
   numbers) runs first on those bytes, before any decode: a decoded dict would already have lost
   duplicate keys. How the mctl-api starter encodes the argument is UNVERIFIED on the mctl-api
   side (no starter was found on main); the golden consumer test of task 13 pins it once it exists.
3. Gating. mctl-api#985 control routes and #989 (mctl-api#1001, `675dff75`) are merged:
   vendoring `internal/glovo/control/contract/` is no longer blocked (`SHA256SUMS` digest
   `afb2e8de2fc709e7671deaa821268cc9ca3ba2d8ebceacb272c389c0954d0a06` at `675dff75` and at main
   `081bd6b7`; re-verify when vendoring). `BLOCKED_FOR_INTEGRATION` stays for the runtime only:
   docs/glovo-control.md says no production verifier mints the control principal until
   mctl-gitops#2506 (an open ZITADEL-versus-Vault issuer spike; the control-principal verifier is
   not yet in place) and no dispatcher is attached on main, so a mounted route answers 503
   `not_ready`.
4. Credentials. The static `MCTL_ASSISTANTS_TOKEN` is replaced by a credential-provider port
   for a bearer whose audience is exactly `mctl-api-glovo-control` (principal
   `service:glovo-control-worker`, permission `glovo:control-dispatch`; `internal/auth/glovo_control_worker.go`,
   docs/glovo-control.md). The issuer source is pending mctl-gitops#2506. The port refuses
   client-side a token that is not a control token (wrong audience). Temporal client auth uses
   the node A names `TEMPORAL_TOKEN_FILE`, `TEMPORAL_TLS_CA_FILE`, `TEMPORAL_TLS_SERVER_NAME`
   (VERIFIED_SOURCE: mctl-gitops `docs/runbooks/temporal-client-auth.md`, row "A. Client
   support": `TEMPORAL_TOKEN_FILE` is re-read at least every 5 minutes; only the mctl-agents
   implementation is UNVERIFIED, because mctl-agents#1057 is an open issue and no open PR for it
   was found), inert when unset, never logged, through a neutral shared module.
   `orchestrator.assistants` must not import `orchestrator.temporal.worker` (T2 enforces it);
   note that the DevLoop worker owns `Client.connect` today, so decision (c) must be taken with
   that in view. This proposal duplicates no #1057 work. The provider holds
   no Temporal credential (mctl-telegram#1276).
5. `orchestrator.action_approvals.intent_hash` import removed: after M10 the workflow never
   computes an intent. The allowed-import list shrinks accordingly.
6. OPEN-989-5 limit. The basket fingerprint may travel in Temporal history only for the
   synthetic, fake-only M1. A keyed digest is required before any real data; the ADR (task 11)
   states this.
7. Rate limiting. the mctl-api control routes never send `Retry-After` (not present in
   `internal/api/handlers_glovo_control.go` or docs/glovo-control.md; other mctl-api surfaces do
   send it: `internal/glovojoin/http.go`, openapi.yaml, docs/principals.md).
   When the header is absent the client uses bounded exponential backoff; when present it is
   honoured within the same bound.
8. Result enum source. mctl-agents#1059 is merged (#1062, `46ccddce`). `docs/contracts/bridge/v1alpha2/README.md`
   says there is no v1alpha2 write result: the unchanged v1alpha1 `result.schema.json`
   (`docs/spikes/1043/`) stays the result contract of `place_order_fake`, so the M9 enum domain is
   read from it. Prefer reusing the strict parsing of `tools/bridge_contract.py` over a local
   duplicate. `tools/bridge_contract.py` imports `jsonschema`, `referencing` and `jcs`
   (`tools/jcs.py`); `jsonschema` is in the dev dependency group of pyproject.toml only, the
   control image installs with `--no-dev`, and `tools/` is outside the image's minimal copy list,
   so availability in the image is UNVERIFIED (reuse needs the dependencies in the runtime group
   and `tools/` copied, or the pre-check stays local and stdlib-only).
9. `not_ready` currently maps to `refused`/`provider_disabled`, which conflates a transient
   not-ready (no dispatcher attached, readiness probe failed) with a disabled provider. See
   OPEN decision (e). The (`status`, `effect_state`) pair-class table stays a local copy
   (existing open item, unchanged).

OPEN owner decisions (recorded, not decided):

- (a) Schema version. Recommended: #1044 adopts `glovo-control-input/v1alpha1` (no mctl-api
  change). Alternative: mctl-api switches to the old `assistants.mctl.ai/...` string.
- (b) Image. Recommended: build-only in CI and let mctl-gitops#2576 own the reproducible build
  and digest pinning. Alternative: publish `ghcr.io/mctlhq/glovo-control-worker` (staged name)
  behind an off-by-default repo variable, never in release-deploy `values_path`.
- (c) Shared Temporal client module. #1057 is an open issue with no code yet, so "land #1057
  first" has nothing to wait on today. Recommended: one neutral shared module owned by the first
  PR that needs it, with `orchestrator.assistants` never importing `orchestrator.temporal.worker`;
  take the decision with the DevLoop worker's ownership of `Client.connect` in view.
- (d) Control token source: pending mctl-gitops#2506. Recommended: accept `BLOCKED_FOR_INTEGRATION`
  for the runtime at approval; the code, contract vendoring and tests ship now.
- (e) `not_ready` mapping (`provider_disabled` appears nowhere in mctl-api: it is only this
  workflow's mapping of `not_ready`; task 12's check that every table code exists in the vendored
  bodies must exclude workflow-only reason codes). Recommended: a distinct transient handling (bounded retry, then
  `unknown`/`dispatch_unconfirmed`, never `refused`) for the not-ready code, with
  `provider_disabled` kept for a genuinely disabled provider, if mctl-api can tell them apart.

Negative matrix (case -> named test):

| Case | Test |
|---|---|
| two tenants, two principals | T7 |
| wrong audience | T20 |
| missing team | T8 (`no_tenant`) |
| revoked connection | T8 |
| stale install | T8 |
| approval replay | T10 + T11 |
| foreign order | T21 (+ T7 foreign `command_id`) |
| ambiguous provider write | T13 + T9 |

UNVERIFIED, image health: probes, readiness endpoint and `readOnlyRootFilesystem` needs of the
worker image are not verified (no deployment exists; mctl-gitops#2576 decides).

## Amendment 2026-11-09

Resolves the crosswalk mismatches assigned to this slice (M6-M10 in mctl-gitops
`deploy/staged/glovo-m1/CROSSWALK.md`, PR #2545), the re-review request on mctl-agents#1044
(comment 6740430920) and the #1258 carry-overs (comment 6740200693). Sources re-read at
mctl-api `a9ca5814` (merged bridge #968, `docs/bridge.md`, `internal/bridge/schema/`) and
mctl-gitops `4f2d2d76`; re-checked at mctl-api `ceac9ed6` (cited bridge files unchanged).
Rows marked **(owner)** record owner decisions of 2026-11-09, including D1, D3 and D5
of mctl-api#957 design "Owner decisions 2026-11-09". The
owner decided on 2026-11-09 that #968 is the canonical bridge; the transport question of
mctl-agents#1043 is closed by that decision. Where this section and older text below
disagree, this section wins; the passages it contradicts have been edited.

| # | Finding | Change |
|---|---|---|
| M6 | The workflow waited for `assistants_provider_result(command_id)`; mctl-api sends `bridge-result` with `{command_id, result_digest}` to the stored workflow and run, at least once (`docs/bridge.md` "Signals") | The signal is `bridge-result`, payload `{command_id, result_digest}`. The workflow dedupes on `command_id`, ignores a `command_id` it did not receive from mctl-api, and then reads the result back through `ControlApiPort.read_command_result(command_id)`, accepting it only if the digest equals the signalled `result_digest`. The signal is a wake-up, never the result |
| M6b | Found during this amendment: the workflow also waited for `assistants_approval_decided`, which no mctl-api component sends (the dispatcher sends only `bridge-result`) | The approval wait is poll-only: `read_approval` every `approval_poll_interval_s` (default 15, bounded 5-60), capped by the `aar_` expiry. No approval signal is registered |
| M7 | `ProviderBridgePort.create_command` assumed an HTTP enqueue route; #968 has only in-process `Store.Enqueue(ctx, tx, …)` | **(owner, option b)** The workflow orchestrates only through mctl-api APIs. `ProviderBridgePort`, `bridge.py` and `bridge_decision.json` are removed. Dispatch and cancel are `ControlApiPort.dispatch_order(order_ref, approval_ref, fingerprint)` and `cancel_order(order_ref)`; mctl-api performs the order transition, the `aar_` plus revocation re-check and `Enqueue` in one transaction. **(owner, D3)** The dispatch/cancel routes and the control-worker principal are mctl-api#985 (M1b/3); #985 is merged (2026-11-10), so the contract is vendored and pinned; a real `ControlApiPort` still refuses to construct (`BLOCKED_FOR_INTEGRATION`) until the control-principal verifier is in place and a dispatcher is attached |
| M8 | `command_id` derived client-side (`cmd_` + base32(sha256)[:26]); #968 generates `cmd_` server-side and dedupes on `(tenant, execution_id, operation_key)` (`internal/bridge/store.go:478-536`) | **(owner)** `ids.command_id` is removed. `dispatch_order` returns the server's `cmd_`, which the workflow stores. An activity retry calls `dispatch_order` again and gets the same `cmd_` back (`created=false`). The operation key is built by mctl-api, not by the workflow |
| M9 | `order_status` vs the bridge's `outcome` × `provider_effect` × `error_code`; `unknown` after a reclaim must survive | "Result mapping (M9)": one total mapping table over the frozen v1alpha1 enums. `provider_effect=unknown` maps to `unknown` in every row, is never `completed` and never re-dispatched. The fake provider reports reclaim-after-permit and `permit_already_issued` as `failed_terminal`/`internal`/`unknown` (mctl-telegram#1262 design, owner decision), which the table maps to `unknown` |
| M10 | Approval binding and refusal reasons (#1258 carry-overs) | The `aar_` is created once, by mctl-api at prepare (mctl-api#957 §6, bound to execution, Target and basket fingerprint). `GlovoControlInput` gains `approval_ref` and `fingerprint`; the `quoting` state and `request_order_approval` are removed, so the workflow never creates a second approval. Dispatch passes the input fingerprint; mctl-api compares it with the `aar_` intent, and a difference ends as `refused`/`basket_changed`, which needs a new `we_` and a new `aar_`. Refusal reasons are distinct: `approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `provider_disabled`, `tenant_busy`. `hir_` stays non-authorizing |
| Reads | **(owner, D1)** History, preview and basket are read by mctl-api through the bridge read extension mctl-api#986 | The workflow never receives a read payload. Its input, activity results, signals and logs carry refs and digests only; a test scans recorded histories for any payload field |
| M1 (consumer side) | Ref families | `tnr_`, `prr_`, `ordr_` come from mctl-api's mapping (mctl-api#957 §2a); `connection_ref` is the M1a `gcn_` id and `install_ref` the M1a `gin_` id, both passed through unchanged. The `ins_` prefix is dropped |

## Amendment 2026-11-09 (round 7): alignment with the merged M1 seams

Resolves what the nine amended mctl-api and mctl-agents proposals of mctl-gitops#2550 (the
mctl-api#957, #959, #960, #961, #985, #986, #988 and #989 slices, and mctl-agents#1059)
assign to this slice, and the stale references that remained. Sources: mctl-api#957 design
§3a, §4.1, §6c and OPEN-957-11; #985 design §2a (the total result-to-order table and `reconcileOrder`), §2b, §5, §6, §7.3, §7.4 and OPEN-985-3/4/9/12/13/15; #986 design §2 and OPEN-986-6; #989 design
§10; #988 OPEN-988-2; the merged bridge (mctl-api `docs/bridge.md`, `internal/bridge`,
`internal/temporalclient` at `ceac9ed`); mctl-agents `docs/spikes/1043/*.schema.json`.
Where this section and older text disagree, this section wins; the passages it contradicts
have been edited. Values owned by a sibling are cited by section, not restated.

| Item | Finding | Change |
|---|---|---|
| X-11, OPEN-985-9 (round 3) | `release_reservation` has no route; no `aar_` ever returns to `approved` | Removed (activity, cancellation step, T12 and the requirement line). Cancellation is `cancel_order(order_ref)` only; its semantics are #985 §6: it revokes a pending or approved `aar_`, marks a reserved one `unknown`, and moves a dispatched order to `cancelled` only when the command effect is `none`, else to `unknown` |
| OPEN-985-15 (the round-5 triple rule; it was the second OPEN-985-9 before the renumbering), OPEN-957-11 (d) | The M9 table is keyed on a triple that cancelled and expired commands never have | Confirmed: `read_command_result` returns the triple itself for them (#985 §2a). Rows 7 and 8 of M9 are those triples; any other `effect_state` than `none` or `not_performed` arrives with `provider_effect: unknown` and lands in row 1. Re-checked, see "Result mapping (M9)". The response fields are pinned in `ASSISTANTS_API_CONTRACT` |
| Round 8 reconcile (#985 §2a, #957 §3a: the result-to-order table is now total over (command `status`, `effect_state`)) | Two M9 rows contradicted the order state that #985 writes: `succeeded`/`none` was `unknown` where the order is closed as wire `failed`, and the workflow `refused` was not tied to the wire `failed`. Cancelled and expired are one wire state, `cancelled`, but two workflow outcomes | M9 gets a wire column (one correspondence per row), a pair guard that runs before the table, and row 4 becomes `failed`/`result_inconsistent`. No new state and no new wire string. See "Result mapping (M9)" |
| #985 §2b `unavailable` (503, no state body, on both control routes) | A failed or absent read, or a pair outside the #985 table, is no state at all | The workflow treats it as retryable and never as a state (M10b). A `cancel_order` 503 rolled back its `Store.Cancel`, so nothing was cancelled |
| #957 §4.1 closed code set | Some `reason_code` values exist only in this workflow | Declared workflow-only in M10b: they never appear on the facade wire |
| OPEN-986-6 (activation precondition; owner: the gitops P1 activation issue) | Until the real provider's `supported_versions` in `MCTL_BRIDGE_PROVIDERS` names v1alpha2, a dispatched command is never claimed and expires (#985 §7.3) | Not a workflow concern and not a gate here. The workflow sees it as an expired command with effect `none`: M9 row 8, `expired`/`command_expired`, wire `cancelled` |
| OPEN-985-3 | The #959 refusal codes of #985 §2b are not mapped | New table "Control refusal mapping (M10b)". `Idempotent-Replayed` is read as a replay, not an error |
| OPEN-985-4 | `revalidate_scope` and `resolve_connection` have no route and no owner | Removed from `ControlApiPort`. mctl-api re-checks membership, connection and install revision itself inside dispatch and again inside the write permit (#985 §5, §7.2), and answers with the codes of the M10b table; the workflow decides nothing from Temporal state. The state `resolving` is removed with them (no owner to resolve), and so is `revalidate_interval_s`. If the owner wants a liveness route, #985 adds it to §2a first and this slice then re-adds the call |
| OPEN-957-11 (a) | `limits` is named but not enumerated | "Contracts" below: `approval_poll_interval_s`, `settle_poll_interval_s`, `settle_timeout_s`, each with default and bounds; #957 §6c copies them verbatim |
| OPEN-957-11 (b), (c), OPEN-985-12 | Route constants mirror #953/#954; the control contract files and the Go-produced golden have no consumer | New vendored sets with provenance, and tests, see "Vendored contracts" and tasks 12 and 13. This slice vendors no bridge schema: it has no bridge port, and the only enum source is the in-repo result schema |
| OPEN-988-2 | `GlovoControlInput` must name the one basket fingerprint | `fingerprint` is `"sha256:" + hex(sha256(JCS(approval_basket)))` as defined by mctl-agents#1059 and #988; the workflow carries and compares it and never parses a basket |
| `handoff_ref` | No source: the control routes return ids, enums and digests only, and `handoff_url` belongs to `POST /connections` (#961), not to an order (#957 §3a) | Removed from `GlovoControlResult` |
| `tenant_cap_reached` | Not in the closed code set of #957 §4.1 or #985 §2b | Removed. Admission pressure arrives as `rate_limited` (retryable) or `tenant_busy` (refusal) (M10b) |
| #954 references | #954 is decomposed into #988 (orders), #989 (`aar_` and fence), #985 (dispatch, cancel, permit wiring), #957 (prepare, facade) and #986 (reads) | Citations updated; `CheckpointSideEffect` and `ReserveActionApproval` wording replaced by the #985 transaction |
| M6 (race) | A `bridge-result` signal can arrive before the dispatch activity has stored `cmd_` | A signal for an unknown `command_id` is ignored; the poll of `read_command_result` recovers it, so no result is lost |

### Control refusal mapping (M10b)

Source of the code set: mctl-api#957 design §4.1, column "#985 control route", and #985 §2b
(closed set; #989 §10 for the approval codes). The column "#1044 M10" of §4.1 says
`retryable`, `terminal` or a name; this table is the consumer side of it. Applies to every
control call. A code outside the closed set, or a body that does not parse, is
`failed`/`control_unmapped_code` with no retry.

| Code(s) | Disposition | `order_status` | `reason_code` |
|---|---|---|---|
| `unavailable`, `rate_limited` | retryable (#957 §4.1 and #985 §2b: 429 `rate_limited` is admission pressure with nothing written, and the code is not a terminal refusal): bounded backoff (honour `Retry-After` when present, bounded exponential backoff when absent: the control routes never send it); on exhaustion in `dispatching`, attempt `cancel_order` once and end as shown. `rate_limited` is never a `reason_code`: the exhausted outcome is `dispatch_unconfirmed` | `unknown` | `dispatch_unconfirmed` |
| `approval_invalid`, `approval_expired`, `approval_replayed`, `intent_mismatch`, `basket_changed`, `tenant_busy` | refusal, no retry | `refused` | the code |
| `not_ready` | refusal, no retry (OPEN decision (e), 2026-11-10: this conflates a transient not-ready, such as no dispatcher attached or a failed readiness probe, with a disabled provider; recommended: bounded retry then `unknown`/`dispatch_unconfirmed` for the transient case) | `refused` | `provider_disabled` |
| `no_tenant`, `no_connection`, `connection_revoked`, `connection_expired`, `stale_install` | refusal (scope not live), no retry | `refused` | the code |
| `not_authorized`, `invalid_request`, `not_found`, `invalid_transition` | terminal | `failed` | the code |

- A dispatch answered 200 with the header `Idempotent-Replayed: true` is a success and returns the same `cmd_` (#985 §2a). The workflow never treats the header as an error.
- 503 `unavailable` on `read_command_result`, `cancel_order` or `read_approval` carries no state body (#985 §2b: a failed or absent read, or a pair outside the §2a table). It is retryable and no information: the workflow keeps its state, retries with bounded backoff and never maps it to an `order_status`. A `cancel_order` that never gets a 200 is not a cancellation (it rolled back its `Store.Cancel`): the workflow reports `cancelled` only for a 200 whose `order_state` says so, and otherwise ends `unknown` with `dispatch_unconfirmed` while no `cmd_` is stored and `settle_timeout` after one.
- After a `cmd_` is stored, a terminal refusal from `read_command_result` ends `unknown`/`result_inconsistent`, never `failed` (the effect may exist). `read_approval` in a state other than pending or approved ends `refused` with the #989 §10 reason for that state; an unrecognised state value is treated as not approved (`approval_invalid`).
- The `reason_code` enum is the union of the M9 reasons, the M10 names, the scope and terminal codes of this table, and `settle_timeout`, `dispatch_unconfirmed`, `control_unmapped_code`, `contract_version_unsupported` and `workflow_id_scope_mismatch`. A test asserts that every code of the vendored #985 refusal bodies has a row here.
- Workflow-only reason codes. The `reason_code` enum is this workflow's vocabulary. A value that is also a `glovo.Code` of mctl-api#957 §4.1 (the approval, scope and terminal codes of the table above, and `provider_disabled`, which is the M10 name §4.1 gives to `not_ready`) is carried through. Every other value is owned here, is not a row of #957 §4.1, and never appears on the facade wire (the facade renders only the #957 §3a states and the §4.1 codes): `dispatch_unconfirmed`, `control_unmapped_code`, `settle_timeout`, `contract_version_unsupported`, `workflow_id_scope_mismatch`, and the M9 reasons `provider_effect_unknown`, `result_inconsistent`, `approval_refused`, `cancel_requested`, `command_expired`, `provider_rejected`, `stale_lease`, `provider_unavailable`, `internal`. A change to #957 §4.1 never needs an edit here unless it renames a carried code.

### Vendored contracts (OPEN-985-12, OPEN-957-11)

- `orchestrator/assistants/api_contract/` is a verbatim copy of mctl-api#985's `internal/glovo/control/contract/*.json` with its `SHA256SUMS`, plus a `PROVENANCE` naming the mctl-api commit. `ASSISTANTS_API_CONTRACT` is `<commit>:<sha256 of that SHA256SUMS file>`; the worker compares it with the `PROVENANCE`, and a missing or different pin keeps `BLOCKED_FOR_INTEGRATION`. Route constants in `api_client.py` are generated from these files, never typed by hand. Amended 2026-11-10: #985 is merged (mctl-api#1001, `675dff75`), so the directory may be created now; `SHA256SUMS` digest `afb2e8de2fc709e7671deaa821268cc9ca3ba2d8ebceacb272c389c0954d0a06` observed at `675dff75` and main `081bd6b7`, re-verify when vendoring.
- `tests/fixtures/mctl-api/control-input.golden.json` is a verbatim copy of mctl-api#957's `internal/glovojoin/contract/testdata/control-input.golden.json`, with provenance. It is added in a follow-up PR after #957 A13 has merged, because #957 vendors this slice's schema first.
- No bridge schema is vendored here (no bridge port). The v1alpha1 and v1alpha2 bridge files stay owned by mctl-agents#1043/#1045 history and mctl-agents#1059 in this repository: this repository is the origin of #1059's published set, not one of its consumers (#1059 §Vendoring lists mctl-api#986, #988 and mctl-telegram#1262 as the consumers), so there is no vendored copy of it here to drift.

### Decided 2026-11-09 (owner; formerly open items)

- **Workflow start (D5).** mctl-api#957 writes a workflow-start record in the prepare
  transaction; a dispatcher owned by #957 starts `GlovoControlWorkflow` only after commit,
  with the deterministic id of `ids.control_workflow_id` and "reject duplicate" reuse
  policy. The workflow re-derives and compares that id; the input contract is unchanged.
- **Control routes (D3).** Dispatch and cancel are mctl-api#985's routes. Route constants
  in `api_client.py` are frozen only from #985's merged contract, pinned through
  `ASSISTANTS_API_CONTRACT`.

### Result mapping (M9)

Applies to the `place_order_fake` command the workflow dispatched. M1 never enqueues
`cancel_order_fake` (mctl-api#989, #985): cancelling is `cancel_order` on the existing
command, and `read_command_result` answers only for `place_order_fake` (#985 §2a). Rows are evaluated top to bottom and the first match wins; the rows
are also pairwise disjoint, so every triple matches exactly one row and the order changes
nothing. Amended 2026-11-09 (agy P2 on mctl-gitops#2547): the third row covers the six
`succeeded`/`applied` triples with an `error_code` other than `none`.

| `outcome` | `provider_effect` | `error_code` | `order_status` | `reason_code` | order wire state (#957 §3a) it corresponds to |
|---|---|---|---|---|---|
| any | `unknown` | any | `unknown` | `provider_effect_unknown` | `unknown` (a possible effect is never shown as cancelled or failed) |
| `succeeded` | `applied` | `none` | `completed` | `none` | `placed` |
| `succeeded` | `applied` | `stale_lease`, `expired`, `approval_refused`, `provider_unavailable`, `provider_rejected`, `internal` | `unknown` | `result_inconsistent` | decided by the pair (guard below): `placed` for a pair with an observed effect; the workflow is the more conservative and never claims more than the wire |
| `succeeded` | `none` | any | `failed` | `result_inconsistent` | `failed` (the pair says no effect; round 8, was `unknown`) |
| `failed_retryable`, `failed_terminal`, `cancelled`, `approval_refused` | `applied` | any | `unknown` | `result_inconsistent` | decided by the pair (guard below); the triple says an effect, so the workflow never says it did not happen |
| `approval_refused` | `none` | any | `refused` | `approval_refused` | `failed`: workflow `refused` is the order wire `failed` (no effect) |
| `cancelled` | `none` | any | `cancelled` | `cancel_requested` | `cancelled` |
| `failed_terminal` | `none` | `expired` | `expired` | `command_expired` | `cancelled`: wire has no `expired` (#957 §3a, no order state in #988); `expired` is this workflow's own outcome |
| `failed_terminal` | `none` | `provider_rejected` | `failed` | `provider_rejected` | `failed` |
| `failed_terminal` | `none` | `none`, `stale_lease`, `approval_refused`, `provider_unavailable`, `internal` | `failed` | the `error_code` (`none` becomes `internal`) | `failed` |
| `failed_retryable` | `none` | any | `failed` | the `error_code` (`none` becomes `provider_unavailable`) | `failed` |

Pair guard (round 8). `read_command_result` returns `status`, `effect_state` and the triple, and the
order wire state of the same command is a function of the pair alone (#985 §2a, applied by
`reconcileOrder`, and rendered by #957 §3a). The workflow classifies the pair by that wire state
and never reads an effect differently from it. The class of a terminal pair is `observed` when
the wire state is `placed`, `possible` when it is `unknown`, and `none` when it is `failed` or
`cancelled`; a `pending` or `leased` command is not terminal and is waited for (a reclaim turned
`permitted` into `unknown` there, wire `unknown`, and the wait then ends at `settle_timeout_s`
as `unknown`). The class function is a small table keyed by the pair, and a pair it does not list is class `possible`, labelled in code with its owner (#985 §2a),
and checked in the task 12 contract test against #985's `TestReconcileOrderTable` rows once the
vendored contract set carries them; #985 §2a does not list the pair rows among the contract files
today, so this proposal asks #985 to add them (an open item, see requirements). The guard runs before the
table above:

- class `possible`: `unknown`/`provider_effect_unknown`, whatever the triple says.
- class `observed`: the table decides, but only row 2 may produce `completed`; any other result is `unknown`/`result_inconsistent`.
- class `none`: the table decides only when `provider_effect` is `none`; `applied` or `unknown` is `unknown`/`result_inconsistent`.

For effect `none` the workflow surface is allowed to differ from the #957 §3a wire state, because the
workflow outcome is a workflow-only vocabulary owned by M9. Exactly one cell does, and the wire column
names it: `approval_refused` with `provider_effect` `none` is workflow `refused` while the wire says `failed`.
Provider result `succeeded` with `provider_effect` `none` is workflow `failed`/`result_inconsistent` and the wire
says `failed` too (#985 closes the order): the same state, with a reason that records the contradiction.
Every pair whose effect is not `none` agrees on both surfaces.

So the workflow outcome never says "no effect" against an observed or possible pair, and never
says "completed" against anything but an observed one. Where the triple and the pair disagree
(a stored result that contradicts `effect_state`) the workflow says `unknown`, which is more
conservative than the order wire state, and says so in `reason_code`; #985 derives the order from the
pair alone and does not read the triple (#985 §2a states this itself).

- M1 never re-dispatches. A retry after `failed` is a new execution with a new `aar_`.
- Settle timeout (`settle_timeout_s`, no accepted result): `cancel_order(order_ref)`, then
  `read_command_result`. A terminal `cancelled` or `expired` command whose `effect_state` is
  `none` or `not_performed` maps by rows 7 and 8 (`cancelled` or `expired`; the order wire
  state is `cancelled` for both); a terminal one with any other effect is `unknown` (row 1,
  the same rule as #985 §2a: a possible effect is never shown as cancelled); a non-terminal
  command, an unreadable result and a 503 `unavailable` are `unknown`/`settle_timeout`.
- Domain. The triple is the body of mctl-api#985 `read_command_result` (§2a), whose members are the result enums of the Glovo write command plus the two synthesised triples for terminal `cancelled` and `expired` commands (`cancelled`/`none`/`none` is row 7, `failed_terminal`/`none`/`expired` is row 8; a terminal command whose `effect_state` is anything but `none` or `not_performed` arrives with `provider_effect: unknown`, row 1). The workflow reads `status`, `effect_state` and the triple; a `completed` status without a triple or without `result_digest`, or a triple that contradicts `effect_state` (for example `succeeded` with an `effect_state` other than `succeeded`), is `unknown`/`result_inconsistent`. A terminal `cancelled` or `expired` status has no `result_digest` and needs none. A pair outside the #985 §2a table arrives as a 503 `unavailable` with no state body (no information, retried) when the order is `dispatched`; on an order that is not `dispatched` (after the workflow's own `cancel_order`, say) the route answers 200 from the stored order state, and the pair it carries is then classed `possible`: `unknown`/`result_inconsistent`, never `none`.
- Seam (the result contract of `place_order_fake`, owned by mctl-agents#1059 `command-place-order-fake`, and the total mapping of `(status, effect_state)` to an order state, owned by mctl-api#985 §2a and #957 §3a): the table above depends on them only through the enum domain, the triples and the wire column; the wire column states a correspondence and owns nothing. If either owner changes an enum or a synthesised triple, the test below fails on the count and the per-row counts must be recomputed in the same wave.
- A test enumerates every (`outcome`, `provider_effect`, `error_code`) triple of the
  enums read from the in-repo result schema that owns the `place_order_fake` result (`docs/spikes/1043/result.schema.json`: mctl-agents#1059 is merged, #1062 `46ccddce`, and `docs/contracts/bridge/v1alpha2/README.md` says there is no v1alpha2 write result, so the v1alpha1 file stays the source) (5 × 3 × 7 = 105) and asserts exactly one row matches and that no triple
  with `provider_effect=unknown` yields anything but `unknown`. Per-row counts, top to
  bottom: 35, 1, 6, 7, 28, 7, 7, 1, 1, 5, 7 (total 105, none unmatched). Re-checked
  2026-11-09 (round 7) by enumerating the three enums of `docs/spikes/1043/result.schema.json`
  at mctl-agents `0ef0e04` against the eleven row predicates: 105 triples, every one matched
  exactly once, per-row counts as listed, and the three synthesised triples above land in
  rows 7, 8 and 1. Re-checked again after the round 8 reconcile (the only change is the output
  of row 4, no predicate moved, so the counts are the same): the enumeration was re-run on the
  amended table and gave the same 105 and the same counts. Guarded outcomes were enumerated
  over the three pair classes (105 x 3 = 315): class `possible` gives 105 `unknown`; class
  `observed` gives 1 `completed` and 104 `unknown`; class `none` gives 35 outcomes without an
  effect (`refused`, `failed`, `cancelled`, `expired`) and 70 `unknown`. In none of the 315
  does a no-effect outcome meet an observed or possible class, and `completed` meets only an
  observed one. The test below repeats the 315-case enumeration.

## Current state

mctl-agents (this clone, HEAD `883b3a1`):

- The only Temporal runtime is the DevLoop control plane in
  `orchestrator/temporal/`. `worker.py` connects with
  `Client.connect(address, namespace=namespace, runtime=runtime)` where
  `namespace = os.environ.get("TEMPORAL_NAMESPACE", "mctl-agents")` (line ~850),
  with no credential and no TLS. It selects queues by `--role
  all|control|execution|implementation` (`ROLES`, `worker_plans()`), creates
  schedules (`owns_schedules`) and runs the execution-request dispatcher
  (`start_dispatcher`). Queues are `mctl-dev-loop`, `mctl-dev-loop-exec`,
  `mctl-dev-loop-implement` (`orchestrator/temporal/constants.py`). Slot limits
  are explicit constants (`CONTROL_MAX_CONCURRENT_ACTIVITIES = 100`,
  `EXECUTION_MAX_CONCURRENT_ACTIVITIES = 40`), per ADR-008
  (`docs/adr/008-worker-queue-split-and-capacity.md`).
- Approval waiting: `orchestrator/temporal/workflows/action_approval.py`
  (`ActionApprovalWaitWorkflow`, `run_gated_action`, child id
  `action-approval-aar_X`, signal `action_approval_decided` with the `aar_` id,
  durable poll timer bounded by receipt expiry, outcomes
  `ran|consumed|denied|expired|mismatch|refused|blocked|effect_failed`).
  Temporal state never authorizes; the gated activity redeems the receipt.
- `orchestrator/action_approvals.py`: `ActionIntent`, `intent_hash()` (mirrors
  mctl-api `workitems.IntentHash`), `idempotency_key()`, and
  `ActionApprovalClient` (`create/get/consume/execute`). Pure helpers are
  reusable; the client uses the DevLoop admin identity.
- `orchestrator/temporal/mctl_client.py`: worker calls to mctl-api use the
  static `MCTL_TOKEN` admin service identity. The assistants worker must not
  reuse it.
- `orchestrator/temporal/dispatcher.py`: precedent for a lease/CAS,
  idempotent mctl-api-to-Temporal delivery.
- Tests: `tests/temporal_harness.py` (drop-in `Worker` polling every queue,
  teardown eviction), `WorkflowEnvironment.start_time_skipping()` in e.g.
  `tests/test_action_approval_wait.py`, `start_local()` in
  `tests/test_b4_update_outage_e2e.py`, replay tests in
  `tests/test_workflow_replay.py`, and an import-graph subprocess check in
  `tests/test_worker_isolation.py` (`FORBIDDEN_IN_WORKER`).
- Build/release: one `Dockerfile` (python:3.12-slim + Node 22, gh, gcc, Go)
  for every role; `pr-validation.yml` job `docker-build` (smoke build + run
  checks); `release-please.yml` dispatches mctl-gitops `release-deploy.yaml`
  with `image_name=ghcr.io/mctlhq/mctl-agents` and an explicit `values_path`
  list of the three admins worker deployments.
- `temporalio==1.34.0` (pyproject.toml), which pulls `nexus-rpc==1.4.0`
  (uv.lock). Nothing uses Nexus.
- Nothing named assistants, Glovo or `mctl-assistants` exists in the repo.

Related proposals (read from the gitops checkout):

- mctl-agents#1043 (`agents-state/mctl-agents/proposals/issue-1043-spike-assistants-verify-cross-namespace/`):
  status `proposed`. Plans Nexus gates N1-N7 and bridge gates B1-B4; working
  hypothesis `API_BRIDGE_SELECTED` (mctl-api command outbox with lease,
  `command_id`, `aar_` consume, result post; mctl-api is the only party that
  signals control). Its schemas are `v1alpha1` proposals, not approved APIs.
- mctl-api#953 and #954 are parent issues. Their contracts are carried by the slices
  this workflow consumes (amended 2026-11-09, round 7): the M1a connection registry
  (#959, #960, #961), the owner-scoped order index (#988), the single-use `aar_`
  receipt and write fence (#989), the control routes, dispatch, cancel and refusal table
  (#985), the facade, prepare and the workflow-start outbox (#957) and the read
  extension (#986). `hir_` has no route in.
- mctl-gitops#2456 (status `merged`, ADR-only): JWT claim mapper + default
  authorizer by namespace role; no task-queue dimension; tasks 3-10 are future
  issues, enforcement is not live.

Deployed state checked:

- `mctl_list_services team=admins`: complete=true; `mctl-agents-worker`,
  `mctl-agents-worker-exec`, `mctl-agents-worker-implement` Synced on
  `ghcr.io/mctlhq/mctl-agents:1.117.0`. No assistants service exists.
- `$MCTL_GITOPS_ROOT/services/admins/`: contains `mctl-agents-worker`,
  `-exec`, `-implement`; no assistants control worker.
- `grep -rl "mctl-assistants"` over `$MCTL_GITOPS_ROOT`: matches only proposal
  documents under `agents-state/`; no service, tenant or namespace job declares
  it.
- Not observed: the live Temporal server namespaces, dynamic config and
  authorizer state (no read access through the mctl tools). Recorded as a gap,
  not as absent.

## Proposed solution

### 1. A separate package, not a new DevLoop role

New package `orchestrator/assistants/` with no import of
`orchestrator.temporal.workflows`, `orchestrator.temporal.worker`,
`orchestrator.temporal.mctl_client`, `orchestrator.auth` or
`claude_agent_sdk`. Allowed imports: `temporalio`, stdlib, and the neutral shared Temporal client-auth module shared with mctl-agents#1057 (amended 2026-11-10: the `intent_hash` import is removed, the workflow never computes an intent after M10; the shared module is never imported from `orchestrator.temporal.worker`). Adding a fifth `--role` to
`orchestrator/temporal/worker.py` was rejected because that module owns
schedules, the dispatcher and the DevLoop namespace default; the issue requires
DevLoop to stay unchanged.

Files:

- `orchestrator/assistants/contracts.py` — frozen dataclasses with explicit
  validators: `GlovoControlInput` (`schema_version`, `tenant_ref`,
  `principal_ref`, `install_ref` (`gin_`), `install_revision`, `connection_ref` (`gcn_`),
  `order_ref`, `execution_id` (`we_`), `work_item_id` (`wi_`), `approval_ref` (`aar_`),
  `fingerprint`, `limits`; amended 2026-11-09; these twelve members are exactly the ones
  mctl-api#957 §6c writes),
  `GlovoControlResult` (`schema_version`, `order_status` enum
  `completed|refused|cancelled|expired|unknown|failed`, `reason_code` enum (design
  "Control refusal mapping (M10b)"), `approval_ref`, `fingerprint`, `command_id`; round 7:
  no `handoff_ref`), plus activity I/O types. Refs use the opaque-handle patterns from #1043
  (`^(tnr|prr|ordr|gcn|gin)_[A-Za-z0-9]{16,40}$`, amended 2026-11-09), lengths <= 64, no free text
  > 256. `INPUT_SCHEMA_VERSION = "glovo-control-input/v1alpha1"` and `RESULT_SCHEMA_VERSION = "glovo-control-result/v1alpha1"` (amended 2026-11-10; the old single `assistants.mctl.ai/glovo-control/v1alpha1` is dropped). Member formats
  (round 7): `execution_id` `^we_[A-Za-z0-9]{16,40}$`, `work_item_id`
  `^wi_[A-Za-z0-9]{16,40}$`, `approval_ref` `^aar_[A-Za-z0-9]{16,40}$`,
  `install_revision` an integer from 1 to 9007199254740991 (the `int64` of mctl-api#959, kept
  inside the exact range of RFC 8785 numbers), `fingerprint` `^sha256:[0-9a-f]{64}$` (the
  one basket fingerprint of mctl-agents#1059 and #988, `"sha256:" + hex(sha256(JCS(approval_basket)))`;
  the workflow carries and compares it and never receives a basket). `limits` is an object with
  `additionalProperties: false` and exactly these optional integer members (amended 2026-11-10: none required, `limits: {}` is valid and takes every default; an unknown member is rejected), each published
  with its default and bounds in the schema, and copied verbatim by mctl-api#957 §6c:
  `approval_poll_interval_s` (default 15, 5-60), `settle_poll_interval_s` (default 15, 5-60)
  and `settle_timeout_s` (default 900, 60-900; 900 is the `ttl_seconds` maximum of the bridge
  command schema, and the real command TTL, the named constant `DispatchCommandTTL`, is
  owned by mctl-api#985). There is no member for an overall timeout: the lifetime is bounded
  by the approval wait (the `aar_` expiry, `GlovoApprovalTTL`, mctl-api#957 OPEN-957-10) plus
  `settle_timeout_s`. The workflow is started as type `GlovoControlWorkflow` on queue `mctl-assistants-control` with a single argument of type bytes (the RFC 8785 bytes of `glovo.control_starts.input`; the starter's encoding is UNVERIFIED on the mctl-api side), and the raw-text pre-check runs on those bytes before anything else. The input arrives as RFC 8785 canonical JSON (mctl-api#957 §6c); the
  validator rejects duplicate keys and any non-integer number in an integer position, using
  the strict parse of `tools/bridge_contract.py` / `vectors/must-reject.json` (mctl-agents#1059, merged) where possible, else an equivalent stdlib-only local one with the same must-reject cases (`jsonschema` is a dev-group dependency only: availability in the `--no-dev` image is UNVERIFIED).
- `orchestrator/assistants/schemas/glovo-control-{input,result}.v1alpha1.json`
  plus `SHA256SUMS` — generated by `tools/assistants_schema.py`; a test
  regenerates and compares (source-pinned contract).
- `orchestrator/assistants/ids.py` — `control_workflow_id(tenant_ref,
  principal_ref, install_ref, order_ref)` ->
  `asst-glovo-<t>-<p>-<i>-<o>`. There is no client-side `command_id` (amended
  2026-11-09, M8): `cmd_` ids come from mctl-api. mctl-api is the only caller that
  starts the workflow; the workflow re-derives and compares its own id as defense in depth.
- `orchestrator/assistants/workflow.py` — `GlovoControlWorkflow`.
- `orchestrator/assistants/activities.py` — activities over the one port.
- `orchestrator/assistants/ports.py` — `ControlApiPort` (mctl-api) only. Amended
  2026-11-09 (M7): it carries `dispatch_order`, `cancel_order`, `read_command_result` and
  `read_approval` (round 7: exactly the four routes of mctl-api#985 §2a); there is no
  `ProviderBridgePort`, and no `revalidate_scope`, `resolve_connection` or
  `release_reservation`.
- `orchestrator/assistants/api_client.py` — HTTP `ControlApiPort` using
  a credential-provider port (amended 2026-11-10; replaces the static `MCTL_ASSISTANTS_TOKEN`) that yields a bearer whose audience is exactly `mctl-api-glovo-control` (`service:glovo-control-worker`, `glovo:control-dispatch`); a token that is not a control token is refused client-side, and a 403 `not_authorized` is terminal with no retry. Never `MCTL_TOKEN`. Base URL from env,
  no redirects (same pattern as `action_approvals._no_redirect_opener`).
  Route paths and body shapes are generated from the vendored mctl-api#985 contract
  files and gated by the `ASSISTANTS_API_CONTRACT` pin (design "Vendored contracts");
  (amended 2026-11-10: #985 is merged) tests exercise the client against a fake that is itself
  validated against those files; the real runtime stays gated.
- ~~`orchestrator/assistants/bridge.py`~~ — removed by the 2026-11-09 amendment (M7).
  The bridge is mctl-api#968 and the workflow reaches it only through mctl-api APIs.
  The integration gate moves to `api_client.py`: a real `ControlApiPort` refuses to
  construct (`BLOCKED_FOR_INTEGRATION`) until `ASSISTANTS_API_CONTRACT` pins the merged
  mctl-api#985 dispatch/cancel route contract (owner decision D3). No raw cross-namespace
  Activity and no Nexus endpoint is implemented here.
- `orchestrator/assistants/worker.py` — standalone entrypoint
  `python -m orchestrator.assistants.worker`.
- `Dockerfile.assistants-control` — python:3.12-slim pinned by digest,
  `uv sync --locked --no-dev`, copies only `orchestrator/__init__.py` and
  `orchestrator/assistants/` (plus the neutral shared Temporal client module and pure deps
  determined by the isolation test; amended 2026-11-10: not `orchestrator/action_approvals.py`,
  so the image does not carry the DevLoop admin-identity client); non-root uid; no Node, gh, Go,
  git. Entrypoint is the assistants worker.

### 2. Workflow

```
mctl-api --start(id derived from server scope, GlovoControlInput incl. aar_ + fingerprint)--> [mctl-assistants / mctl-assistants-control]
GlovoControlWorkflow   (amended 2026-11-09)
  check schema_version, re-derive workflow id          (no activity yet)
  awaiting_approval: poll read_approval(aar_) every approval_poll_interval_s, bounded by aar_ expiry
  dispatching: dispatch_order(order_ref, aar_, fingerprint) -> cmd_
              (mctl-api#985: order transition + aar_/revocation re-check + bridge Enqueue in one tx;
               refusals by "Control refusal mapping (M10b)")
  settling:   wait signal bridge-result{command_id, result_digest} | poll read_command_result
              every settle_poll_interval_s, up to settle_timeout_s; accept only the stored cmd_
              and, for a completed command, a matching digest; duplicates are no-ops
  completed:  return GlovoControlResult(order_status, reason_code)  (map: "Result mapping (M9)")
```

Rules:

- Temporal state never authorizes. Each step that mutates calls mctl-api, which
  re-runs its own checks in the same transaction (mctl-api#985 §5: membership, connection,
  install revision, `aar_` state and binding, fingerprint) and once more inside the write
  permit (#985 §7.2, #989 fence). The workflow only decides whether to ask.
- `hir_` is not a field of any input type; a test asserts the dataclass
  rejects it.
- Fingerprint and `approval_ref` arrive in the input and never change; mctl-api
  compares them with the `aar_` intent at dispatch and a mismatch ends in
  `refused/basket_changed` (amended 2026-11-09, M10). A retry with a different
  basket requires a new execution (`we_`) and a new `aar_` (mctl-api#989, #985 §2b).
- A control call that cannot be answered after bounded retries never lets the workflow
  proceed: `read_approval` unanswered keeps it waiting until the `aar_` expiry; an
  unconfirmed dispatch ends `unknown`/`dispatch_unconfirmed` (M10b); M1 never re-dispatches.
- Cancellation: a `CancelledError` handler runs in a
  `workflow.shield`-equivalent (non-cancellable) scope only `cancel_order(order_ref)`,
  whether or not a command exists (mctl-api#985 §6: before dispatch it revokes the
  pending or approved `aar_` and cancels the order; after dispatch it cancels the command
  and the order becomes `cancelled` only when the effect is `none`, else `unknown`). It is
  idempotent, so a repeat or a cancel after completion is a 200 that changes nothing. It
  never approves, never re-activates a revoked connection and never returns an `aar_` to
  `approved`.
- Provider `unknown` -> no re-dispatch; result `order_status=unknown`. The full
  mapping is "Result mapping (M9)".
- The signal arrives as one object argument `{command_id, result_digest}` (mctl-api
  `internal/temporalclient`, `BridgeResultSignalName`), at least once. A signal whose
  `command_id` is not the stored `cmd_`, including one that arrives before the dispatch
  activity has stored it, is ignored; the poll of `read_command_result` recovers it.
- The only signal is `bridge-result` (`command_id`, `result_digest`), never a payload, so no provider
  data or token enters history. Activities return ids, enums and bounded refs.
- Bounded wait: no separate workflow `execution_timeout` (amended 2026-11-10; the requirements
  say the lifetime is the approval wait plus `settle_timeout_s`), approval wait capped
  by `aar_` expiry, settle wait capped at `settle_timeout_s` (default 15 min, the
  `ttl_seconds` maximum of 900 s in the bridge command schema). The values come from the
  input `limits`; there is no workflow execution timeout, because the two waits
  and the bounded activity retries already bound the lifetime.

### 3. Worker

`orchestrator/assistants/worker.py`:

- Constants `ASSISTANTS_NAMESPACE = "mctl-assistants"`,
  `ASSISTANTS_TASK_QUEUE = "mctl-assistants-control"`.
- `main()` reads `TEMPORAL_NAMESPACE` with no default and refuses
  (`SystemExit`) unless it equals `ASSISTANTS_NAMESPACE`; refuses
  `MCTL_TOKEN` being set (wrong identity) and any provider credential env
  (`GLOVO_*`, `PROVIDER_*`). Temporal auth is passed through only as
  `TEMPORAL_TOKEN_FILE`, `TEMPORAL_TLS_CA_FILE` and `TEMPORAL_TLS_SERVER_NAME` (node A names of mctl-agents#1057, inert when unset, never logged; amended 2026-11-10, names UNVERIFIED until #1057 merges); deployment credentials are a #2457 concern.
- Registers exactly `GlovoControlWorkflow` and the assistants activities.
  No schedules, no dispatcher.
- Explicit limits from bounded env: `ASSISTANTS_MAX_CONCURRENT_ACTIVITIES`
  (default 20, range 1-100), `ASSISTANTS_MAX_CONCURRENT_WORKFLOW_TASKS`
  (default 20), activity start-to-close <= 30 s, schedule-to-close <= 5 min.
- At startup logs the `ASSISTANTS_API_CONTRACT` pin; if `ASSISTANTS_API=real` while
  the pin is missing or differs from the `PROVENANCE` of the vendored mctl-api#985
  contract set, exits with status `BLOCKED_FOR_INTEGRATION` (amended 2026-11-09, round 7).
- Noisy-tenant pressure reaches the workflow only as `rate_limited` (retried) or `tenant_busy` (refused)
  (mctl-api#985 §2b); the worker's slot limits cap total parallelism.

### 4. Test harness

`tests/assistants_harness.py`: starts `WorkflowEnvironment.start_local()`
(disposable dev server) with namespaces `mctl-assistants` and a decoy
`mctl-agents`, a fake `ControlApiPort` holding two tenants and two principals
in one tenant; the fake's `dispatch_order` mints server-style `cmd_` ids, keeps a
write counter per `cmd_`, answers replays with `Idempotent-Replayed`, can emit
`bridge-result` signals with digests, and returns the refusal codes and the
`read_command_result` triples of the vendored mctl-api#985 contract files; every fake
response is validated against those files so the fake cannot drift (amended
2026-11-09, round 7; there is no `LocalFakeBridge`). Time-skipping env is used for
poll and wait timers.

### 5. CI

- `pr-validation.yml`: new job `assistants-control-build` builds
  `Dockerfile.assistants-control`, runs the import-graph check inside the image,
  checks non-root uid, and verifies the worker refuses `TEMPORAL_NAMESPACE=mctl-agents`.
- The existing `docker-build` job and `release-please.yml` `values_path` are
  not changed. Image publishing is not added in this proposal (see Open
  questions); when approved it uses a distinct image name and is never added to
  release-deploy `values_path`.

## Alternatives

- **Add an `assistants` role to `orchestrator/temporal/worker.py`.** Reuses
  plumbing, but shares the module that defaults to namespace `mctl-agents`,
  owns schedules and the dispatcher, and ships in the image the DevLoop
  deployments run. Rejected: violates "DevLoop unchanged" and widens blast
  radius.
- **Reuse `ActionApprovalWaitWorkflow` as a child.** Semantics fit, but it
  calls the DevLoop policy-checkpoint gated activities and its registration
  would pull DevLoop workflow modules into the assistants worker. Rejected;
  the control workflow reimplements the bounded signal+poll wait and reuses
  nothing from `orchestrator.action_approvals` (amended 2026-11-10).
- **Wire a Nexus operation or a cross-namespace Activity now.** Rejected by
  the issue and by #1043: Nexus gates N2/N5 are unverified on OSS 1.31.0 and a
  raw cross-namespace Activity would require the provider to hold control
  authority. There is no bridge port (removed 2026-11-09, M7), so a later transport change would go through mctl-api.
- **Expose Temporal to the facade/provider, per-user namespaces, queue-only
  isolation, a second scheduler.** Rejected in the issue and by #2456 (no
  task-queue authorization dimension).

## Platform impact

- Migrations: none. New code, new Dockerfile, new CI job. No namespace,
  service, secret, schedule or gitops change; nothing is deployed.
- Backward compatibility: existing DevLoop modules, queues, image and release
  dispatch are untouched; a test asserts `orchestrator/temporal/` does not
  import `orchestrator.assistants` and vice versa.
- Resource impact: CI only (one extra image build, a few minutes). Runtime cost
  is zero until #2457 activates a deployment.
- Risks and mitigations:
  - Contracts drift from the mctl-api#985 control routes (merged; mctl-api#1001).
    Mitigation: the vendored contract set with its pinned `SHA256SUMS`, the generated route
    constants and the fake validated against them; integration stays
    `BLOCKED_FOR_INTEGRATION` for the runtime until the control-principal verifier (mctl-gitops#2506) exists and a dispatcher is attached (#985 is merged; vendoring is unblocked, amended 2026-11-10).
  - Local tests overstate isolation (dev server has no authorizer). Mitigation:
    tests are labelled structural; the live denial matrix (#1043 D1-D6) is a
    precondition of #2457 activation.
  - Someone deploys the image early. Mitigation: no publish step, worker refuses
    a wrong namespace and a DevLoop token, real bridge refuses to load.
  - Workflow determinism: new workflow type with no history; replay tests are
    added from the first commit, and later changes use `workflow.patched()`.
