# Design: issue-1089-feat-assistant-runtime-field-on-assistan

## Current state

- `docs/adr/0008-managed-runtime.md` (Proposed, written before the code) fixes the contract:
  section 1 (consent value `managed-data-flow/v1`, verbatim consent text, stored
  `managed_consent_version` / `managed_consent_at`, audited, new version holds existing
  managed installs) and section 3 (`agent_profiles.runtime TEXT NOT NULL DEFAULT 'own'`; the
  claim predicate itself belongs to slice 2).
- `assistants/schemas/assistant-install.schema.json`: `spec` has `additionalProperties: false`
  and the properties `assistant, mode, paused, listening, values, disclosureLevels,
  intentTiers, limits, audience, disclosure, schedule, ownerNotes`. It is compiled in
  `internal/assistant/assistant.go` (`c.Compile("assistant-install.schema.json")`), so an
  unknown `runtime` is rejected today.
- `internal/assistant/assistant.go`: `Install.Spec` mirrors the schema; `Profile` is what an
  install resolves to; `Resolve(def, in)` builds it; `ProfileRequest` maps it to the body of
  `PUT /api/admin/agent/profile`.
- `internal/db/agent_domain.go`: `AgentProfile`, `AgentAssistant` (decrypted install +
  `InstallRevision`, `Mode` read in one row), `AgentAssistantRef`, and `AgentProfileUpdate`
  (nil pointer = leave column). `updateAgentProfileFields(ctx, ex, userID, u)` builds one
  UPDATE, with `ExpectedInstallRevision` as a compare-and-set and `installRevisionMiss` to
  explain a zero-row result. It runs on `s.DB` (`UpdateAgentProfileFields`) or inside a tx
  (`InstallAgentAssistant` in `assistant_definitions.go`, `InstallAgentFork` in
  `assistant_forks.go`).
- `internal/db/agent_schema.go`: columns are added with
  `addColumnIfMissing(ctx, dbConn, pg, table, col, pgType, sqliteType)`, idempotent, both
  dialects.
- `internal/db/assistant_forks.go` `beginForkTx` shows the repo's serialization idiom: resolve
  the dialect first, then lock a row (`SELECT ... FOR UPDATE` on Postgres, `UPDATE users SET
  id = id` on SQLite) before counting a quota (`MaxForksPerAccount`, `ErrForkLimit`).
- `internal/assistantinstall/service.go`: `Kind` enum (`KindInvalid` .. `KindForksDisabled`),
  `*Error{Kind, Msg, Detail, CurrentRevision, Err}`, `Service{Store, Catalog, Registry,
  ForksEnabled, Now}`. `Commit` reads `GetAgentAssistantRef`, decides lifecycle/visibility
  gates, builds one `db.AgentProfileUpdate` with `BumpInstallRevision` and a CAS, and writes it
  through one of three store paths. `Patch` decrypts the stored install, RFC 7396-merges the
  spec and calls `Apply` -> `Commit`. `AuditText` maps kinds to audit strings. `Settings` /
  `SettingsOf` / `Current` feed the MCP and web surfaces. `Commit` does not audit itself; the
  surfaces do (`s.audit` in MCP, `s.auditManage` on the web).
- `internal/mcp/assistant_tools.go`: `installArgKeys` are copied into `spec` by
  `install_assistant`; `unknownArgs` refuses anything else; `update_install` takes `patch` and
  `expected_revision` only; `assistantErrResult` maps kinds to `error` codes and audit reasons
  (`ReasonRefused`, `ReasonCapabilityDisabled`, ...); `list_assistants.mine` is
  `assistantInstalled{assistant, version, install_revision, installed}`.
- `internal/mcp/descriptors_test.go` holds `docs/tool-descriptors.json` byte-equal to the
  registry (`-update-descriptors` regenerates it and the per-profile snapshots); ADR 0007
  requires an approved `docs/product-updates/*.yaml` entry for a tool change (example:
  `docs/product-updates/tool-list-follows-scopes.yaml`).
- `internal/web/manage_assistant.go`: assistant section template with field rows
  (`assistant-mode`), one-setting forms posting `setting`/`value`/`expected_revision` to
  `/telegram/connect/manage/assistant/update`; `assistantPatchFromForm` whitelists `paused`,
  `listening`, `mode`; `assistantFailure` maps kinds to HTTP status and owner text.
- `internal/agent/control/router.go` `handleAssistant` prints Assistant, From an install,
  Mode, Autopilot paused, Listening, limits, intents, hours, audience, senders.
- `internal/agentapi/profilehandler.go` `NewAdminAgentProfileHandler`: strict decoder against
  `upsertAgentProfileKeys`, admin scope `admin:users`, writes `db.UpdateAgentProfileFields`
  directly (not through `assistantinstall`), audits via `store.LogToolCall`.
- `internal/config/config.go`: env parsing with `envBool(...)` (e.g.
  `ASSISTANT_FORKS_ENABLED`), wired in `cmd/server/main.go` (`assistantSvc.ForksEnabled =
  cfg.AssistantForksEnabled`, line ~653).
- Audit: `db.Store.LogToolCall(ctx, db.ToolCall{UserID, Tool, PeerRedacted, Status, ErrMsg,
  CallPath, Reason})` in `internal/db/store.go`, hash-chained per user; non-fatal by contract.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: production tenant `labs`;
  `ASSISTANT_REGISTRY_ENABLED: "true"`; no `MANAGED_RUNTIME_*` or
  `MANAGED_MAX_INFLIGHT_PER_ACCOUNT` key, so the new flag would default to off.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: grep for `MANAGED_`
  returned nothing; same conclusion for preview. Enabling there is mctlhq/mctl-gitops#2345.
- mctl MCP tools were not called: this slice changes no deployed configuration and the gitops
  files answered the only deployment question (current flag values).

## Proposed solution

### 1. Schema and `internal/assistant`

- Schema `spec.properties` gains `"runtime": {"enum": ["own", "managed"], "default": "own"}`
  and `"consent": {"type": "string", "maxLength": 64}` with descriptions pointing at ADR 0008.
  `docs/assistants/spec.md` documents both.
- `Install.Spec` gains `Runtime string \`json:"runtime"\`` and `Consent string
  \`json:"consent"\``.
- `Profile` gains `Runtime string`; `Resolve` sets `p.Runtime = s.Runtime`, defaulting to
  `RuntimeOwn` when empty. `Resolve` never interprets consent.
- `ProfileRequest` adds `"runtime": p.Runtime`, and `"consent": in.Spec.Consent` when non-empty.
- Constants live in `internal/db` (the lowest layer): `RuntimeOwn = "own"`,
  `RuntimeManaged = "managed"`, `ManagedConsentCurrent = "managed-data-flow/v1"`, and the
  verbatim `ManagedConsentText`. `assistant` imports `db` only if it already does; otherwise it
  keeps local string constants checked equal to the db ones by a test.

### 2. `internal/db`

- `agent_schema.go`: four `addColumnIfMissing` calls on `agent_profiles`:
  `runtime` (`TEXT NOT NULL DEFAULT 'own'` both), `managed_consent_version`
  (`TEXT NOT NULL DEFAULT ''`), `managed_consent_at` (`TIMESTAMPTZ` / `DATETIME`, nullable),
  `budget_paused_until` (`TIMESTAMPTZ` / `DATETIME`, nullable; read by nobody yet).
- `AgentProfile` gains `Runtime`, `ManagedConsentVersion`, `ManagedConsentAt time.Time`
  (zero = never), `BudgetPausedUntil time.Time`; `GetAgentProfile` scans them. A method
  `NeedsManagedReconsent() bool` returns `Runtime == RuntimeManaged &&
  ManagedConsentVersion != ManagedConsentCurrent`. This is the single predicate slice 2 will
  reuse to hold jobs.
- `AgentAssistant` and `AgentAssistantRef` gain `Runtime` and `ManagedConsentVersion`, read in
  the same row as `InstallRevision`, so the transition decision and the CAS cover the same
  state.
- `AgentProfileUpdate` gains `Runtime *string`, `ManagedConsentVersion *string`,
  `ManagedConsentAt *time.Time`, and `ManagedQuota *int`. When `ManagedQuota` is set (only for
  an own -> managed write), `updateAgentProfileFields`:
  - requires a transaction: `UpdateAgentProfileFields` opens one when it would otherwise run on
    `s.DB`; `InstallAgentAssistant` / `InstallAgentFork` already have one;
  - takes a global managed-runtime lock first: Postgres `SELECT pg_advisory_xact_lock($1)` with
    a fixed key constant; SQLite needs none because the guarded UPDATE is a single write
    statement under SQLite's writer lock;
  - appends `AND (SELECT COUNT(*) FROM agent_profiles o WHERE o.runtime = 'managed' AND
    o.user_id <> $u) < $max` to the WHERE;
  - on zero rows, re-checks the count on the same `ex` and returns `ErrManagedQuota` if it is
    the cause, else falls through to `installRevisionMiss`.
- `CountManagedAccounts(ctx)` for the gauge/diagnostics (cheap, used by tests).

### 3. `internal/assistantinstall`

- New kinds appended after `KindForksDisabled` (iota order preserved):
  `KindManagedConsentRequired`, `KindManagedDisabled`, `KindManagedQuota`; `AuditText` maps them
  to `managed consent required`, `managed disabled`, `managed quota`.
- `Service` gains `Managed ManagedRuntime{Enabled bool; MaxAccounts int}`, set from config in
  `cmd/server/main.go` next to `ForksEnabled`.
- An exported pure function, shared with the admin route:

  ```go
  // DecideRuntime returns the profile columns a write must set, or a refusal.
  func (m ManagedRuntime) DecideRuntime(currentRuntime, requested, consent string, now time.Time) (RuntimeChange, *Error)
  ```

  `requested == ""` means "unchanged" (admin route) and `RuntimeChange` is empty. Rules, in
  this order so the least actionable refusal wins (the owner is never asked to consent to a
  runtime the server cannot offer): own -> managed requires `Enabled` (`KindManagedDisabled`),
  then consent == `ManagedConsentCurrent` (`KindManagedConsentRequired`), then sets
  `ManagedQuota = &MaxAccounts` (the store refuses `KindManagedQuota`). managed -> managed with the current consent refreshes version/time;
  without it, sets only `Runtime`. managed -> own sets only `Runtime`, no checks.
  `RuntimeChange{Runtime, ConsentVersion, ConsentAt, Quota, Changed, Consented}` is copied onto
  the `db.AgentProfileUpdate`.
- `Commit`: reads `current.Runtime` from `GetAgentAssistantRef` (already read for the CAS),
  calls `DecideRuntime(current.Runtime, p.resolved.Runtime, p.consent, now)` before the write,
  merges the result into `update`, and maps `db.ErrManagedQuota` to `KindManagedQuota`.
- `prepare` captures `spec.consent` into `Prepared.consent` and removes `consent` from the
  canonical document before it becomes `p.document`, so the encrypted install never carries
  it and a later `Patch` can never inherit a consent.
- After a successful write, when `RuntimeChange.Changed || Consented`, `Commit` writes
  `Store.LogToolCall(ctx, db.ToolCall{UserID: userID, Tool: "assistant.runtime", Status:
  "ok", Reason: "<from>-><to> consent=<version|none>"})`. The tool name is hash-chained; the
  reason carries no user data.
- `Settings` gains `Runtime string` and `ManagedReconsentRequired bool`; `Installed` gains
  `Runtime` and `ManagedReconsentRequired`; `SettingsOf` / `Current` fill them.
- `Patch(ctx, userID, patch, expected)` gets a sibling `PatchWithConsent(..., consent string)`
  (or an options struct) so a surface can pass consent outside the merge patch; `Patch` keeps
  its signature for existing callers.

### 4. `internal/mcp/assistant_tools.go`

- `installArgKeys` gains `runtime`; `install_assistant` gains `mcplib.WithString("runtime",
  mcplib.Enum("own","managed"), ...)` and `mcplib.WithString("consent", ...)`; `consent` is an
  allowed key placed into `spec.consent`.
- `update_install` gains a top-level `consent` argument passed to `PatchWithConsent`
  (`runtime` travels in the patch like any spec member; `consent` inside the patch is also
  honoured since it reaches `prepare` the same way).
- Descriptions state the consent value, the verbatim consent text, that `managed -> own` needs
  no consent, and the three new errors.
- `assistantErrResult`: `KindManagedConsentRequired -> "managed_consent_required",
  ReasonRefused`; `KindManagedDisabled -> "managed_disabled", ReasonCapabilityDisabled`;
  `KindManagedQuota -> "managed_quota", ReasonRefused`, retryable false. The consent error's
  `action` names the exact `consent` value to send after showing the text to the user.
- `assistantInstalled` gains `runtime` and `managed_reconsent_required`; the `list_assistants`
  description documents them.
- Regenerate `docs/tool-descriptors*.json`; add
  `docs/product-updates/assistant-runtime-managed.yaml` (`kind: new_capability` or the kind the
  schema requires, `tools: [install_assistant, update_install, list_assistants]`, evidence of
  the text changes, `status: approved` after review).

### 5. `internal/web/manage_assistant.go`

- A `Runtime` field row (`id="assistant-runtime"`) showing `managed (platform worker)` or
  `own (your worker)`, and a re-consent notice when needed.
- A new runtime form posting `setting=runtime`, `value=own|managed`, `expected_revision`, and a
  checkbox `consent` whose value is `managed-data-flow/v1` and whose label is
  `db.ManagedConsentText` verbatim. `assistantPatchFromForm` accepts `runtime` with the two
  values; `HandleAssistantUpdate` passes `r.PostForm.Get("consent")` to `PatchWithConsent`.
- `assistantFailure`: consent required -> 422 "Tick the box to agree ... Nothing was changed.";
  disabled -> 403; quota -> 409 "No managed capacity is available right now".

### 6. `internal/agent/control/router.go`

`handleAssistant` prints `Runtime: managed (platform worker)` or `Runtime: own (your worker)`
after the Mode line, and `Managed consent: needs renewal (open the manage page)` when
`profile.NeedsManagedReconsent()`.

### 7. `internal/agentapi/profilehandler.go`

`upsertAgentProfileRequest` gains `Runtime *string` only; `runtime` is added to
`upsertAgentProfileKeys` and `consent` is NOT (the strict decoder answers 400 for it). The admin
route never carries consent: consent is an act of the account owner on their own surfaces. The
handler gets the `ManagedRuntime` gate (constructor argument), reads the current runtime and
stored `managed_consent_version`, and calls `DecideRuntime(current, requested,
storedConsentIfCurrent, now)`, i.e. it passes the stored version as the consent only when it
equals `ManagedConsentCurrent`; `own -> managed` on a profile whose owner never consented (or
consented to an older version) is therefore 409 `managed_consent_required`, 403
`managed_disabled` and 409 `managed_quota` follow as for the owner surfaces, and `managed ->
own` always succeeds. A change is audited with the same
`assistant.runtime` row under the target user, and the admin's own `admin.agent_profile.upsert`
row as today. The response gains `runtime`.

### 8. `internal/config`

`ManagedRuntimeEnabled bool` (`MANAGED_RUNTIME_ENABLED`, false), `ManagedRuntimeMaxAccounts
int` (`MANAGED_RUNTIME_MAX_ACCOUNTS`, 1, must be >= 0), `ManagedMaxInflightPerAccount int`
(`MANAGED_MAX_INFLIGHT_PER_ACCOUNT`, 1, must be >= 1; parsed only). Startup log line as for
forks.

## Alternatives

1. Store consent inside the install document and compare documents. Dropped: a merge patch
   would carry the old consent forward, so `managed -> own -> managed` would silently reuse an
   earlier agreement; consent must be an act of the call, recorded as version and time.
2. Check the quota in Go (`CountManagedAccounts` then UPDATE). Dropped: two concurrent
   switches both pass the count under READ COMMITTED. The guarded UPDATE plus an advisory
   transaction lock follows the existing `beginForkTx` pattern and holds under concurrency.
3. Keep runtime outside the install (a separate `set_runtime` tool and column only). Dropped:
   the ADR and issue make it an install field so it bumps `install_revision`, which is what
   fences an in-flight attempt when the runtime switches (ADR section 3), and one
   install/update path keeps a single validation surface.

## Platform impact

- Migrations: four additive columns with defaults; existing rows read `own` and an empty
  consent. No backfill, no data rewrite; idempotent on restart. Rolling back the binary leaves
  unused columns behind, which is harmless.
- Backward compatibility: installs without `runtime` resolve to `own`; the admin route without
  `runtime` is unchanged; the MCP surface only gains optional arguments and output fields
  (descriptor snapshot and product-update entry make the change visible). `ProfileRequest`
  gains a key the admin route now accepts, so they ship together.
- Behaviour: no claim query changes, so even a `managed` account is still claimed by an own
  worker in this slice; with the flag off (deployed default in `labs`), nobody can become
  managed at all.
- Resource impact: one indexed-by-pk UPDATE with a COUNT subquery over `agent_profiles`
  (small table) only on own -> managed writes; an advisory lock held for one statement.
- Risks and mitigations:
  - Consent bypass via a path that skips `DecideRuntime` (e.g. a new store writer). Mitigation:
    the mutation test (drop the consent check) must fail; the admin route goes through the same
    function.
  - Audit row written after commit can be lost. Mitigation: `LogToolCall` failure is logged and
    surfaces in `VerifyAuditChain`; the consent version/time are in the profile row itself.
  - Verbatim text drift between ADR, web and MCP. Mitigation: one constant, and a test that
    reads `docs/adr/0008-managed-runtime.md` and asserts it contains the constant.
