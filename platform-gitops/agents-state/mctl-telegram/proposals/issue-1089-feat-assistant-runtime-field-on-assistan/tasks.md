# Tasks: issue-1089-feat-assistant-runtime-field-on-assistan

- [ ] 1. Config: add `ManagedRuntimeEnabled` (`MANAGED_RUNTIME_ENABLED`, false),
  `ManagedRuntimeMaxAccounts` (`MANAGED_RUNTIME_MAX_ACCOUNTS`, 1, >= 0) and
  `ManagedMaxInflightPerAccount` (`MANAGED_MAX_INFLIGHT_PER_ACCOUNT`, 1, >= 1) to
  `internal/config/config.go` — DoD: defaults and invalid values covered by config tests;
  documented next to `ASSISTANT_FORKS_ENABLED`.
- [ ] 2. DB constants and columns: `RuntimeOwn`, `RuntimeManaged`, `ManagedConsentCurrent =
  "managed-data-flow/v1"`, `ManagedConsentText` (verbatim ADR text); four
  `addColumnIfMissing` calls in `internal/db/agent_schema.go` (`runtime`,
  `managed_consent_version`, `managed_consent_at`, `budget_paused_until`) — DoD: migration runs
  twice on Postgres and SQLite without error; existing rows read `own`.
- [ ] 3. DB types (depends on 2): `AgentProfile` (+`Runtime`, `ManagedConsentVersion`,
  `ManagedConsentAt`, `BudgetPausedUntil`, `NeedsManagedReconsent()`), `AgentAssistant` and
  `AgentAssistantRef` (+`Runtime`, `ManagedConsentVersion`), scans in `GetAgentProfile`,
  `GetAgentAssistant`, `GetAgentAssistantRef` — DoD: round-trip tests pass.
- [ ] 4. DB update path (depends on 3): `AgentProfileUpdate.Runtime`, `ManagedConsentVersion`,
  `ManagedConsentAt`, `ManagedQuota`; guarded WHERE with the COUNT subquery; Postgres
  `pg_advisory_xact_lock`; `UpdateAgentProfileFields` wraps in a tx when `ManagedQuota` is set;
  `ErrManagedQuota` distinguished from a revision miss; `CountManagedAccounts` — DoD: quota
  tests, including a concurrent one, pass on both dialects.
- [ ] 5. Schema and `internal/assistant` (depends on 2): `spec.runtime` enum and `spec.consent`
  string in `assistants/schemas/assistant-install.schema.json`; `Install.Spec.Runtime`,
  `Install.Spec.Consent`; `Profile.Runtime` defaulted to own in `Resolve`; `ProfileRequest`
  emits `runtime` (and `consent` when set); `docs/assistants/spec.md` updated — DoD: schema and
  Resolve tests pass.
- [ ] 6. `internal/assistantinstall` (depends on 4, 5): new kinds `KindManagedConsentRequired`,
  `KindManagedDisabled`, `KindManagedQuota` and their `AuditText`; `ManagedRuntime` gate on
  `Service`; exported `DecideRuntime`; `prepare` strips `consent` from the stored document;
  `Commit` applies the decision, maps `db.ErrManagedQuota`, audits `assistant.runtime`;
  `PatchWithConsent`; `Settings` / `Installed` gain runtime and re-consent fields; wire
  `cmd/server/main.go` — DoD: service tests below pass.
- [ ] 7. MCP (depends on 6): `runtime` / `consent` on `install_assistant`, `consent` on
  `update_install`, error mapping, `list_assistants.mine.runtime` and
  `managed_reconsent_required`, descriptions; regenerate `docs/tool-descriptors*.json` with
  `go test ./internal/mcp -run TestToolDescriptorsSnapshotMatchesRegistry -update-descriptors`;
  add an approved `docs/product-updates/assistant-runtime-managed.yaml` — DoD: descriptor and
  product-update gates green.
- [ ] 8. Manage page (depends on 6): Runtime row, runtime form with the consent checkbox and the
  verbatim label, `assistantPatchFromForm` accepts `runtime`, failure messages for the three
  kinds — DoD: web tests pass; page renders unchanged for an own account apart from the new
  row and form.
- [ ] 9. `/mctl assistant` (depends on 3): Runtime line and re-consent line in
  `handleAssistant` — DoD: router tests pass.
- [ ] 10. Admin profile route (depends on 6): `runtime` / `consent` in
  `upsertAgentProfileRequest` and `upsertAgentProfileKeys`, `DecideRuntime` validation, status
  codes, audit, `runtime` in the response; constructor gains the gate — DoD: agentapi tests pass.
- [ ] 11. Update ADR 0008 only where implemented names differ from the record (ADR says the code
  becomes authoritative) — DoD: names in the ADR match the code.
- [ ] 12. `go fmt`, `go vet`, `golangci-lint`, `go test ./...`; the PR body states the mutation
  for every regression test (issue requirement).

## Tests

Every test below must fail with the bug reintroduced; the mutation is named in brackets.
Fixtures use the existing personas (Alice, Bob, Carol, Dana) and ids already used for them.

- [ ] T1. Schema: `runtime` `own` / `managed` accepted, `"remote"` and `1` rejected; `consent`
  string accepted, number rejected [mutation: drop `runtime` from the schema / widen the enum].
- [ ] T2. `Resolve` without `runtime` gives `Profile.Runtime == "own"`; with `managed` gives
  managed; `ProfileRequest` carries `runtime` [mutation: remove the default].
- [ ] T3. Migration adds the four columns idempotently on both dialects; an old row reads
  `own`, empty consent, zero times [mutation: default `''`].
- [ ] T4. own -> managed without consent, and with `consent: "managed-data-flow/v0"`, is
  `KindManagedConsentRequired`; the profile, revision and install are unchanged
  [mutation: drop the consent check in `DecideRuntime`].
- [ ] T5. own -> managed with consent while `Enabled == false` is `KindManagedDisabled`; nothing
  changes [mutation: drop the flag check].
- [ ] T6. With `MaxAccounts = 1` and Bob already managed, Alice's own -> managed is
  `KindManagedQuota`; with Bob switched back to own it succeeds; a reinstall of an already
  managed account does not count itself [mutation: remove the WHERE guard / count self].
- [ ] T7. Two concurrent own -> managed commits with `MaxAccounts = 1` (Postgres test DB when
  available, SQLite otherwise): exactly one succeeds, the other is `KindManagedQuota`
  [mutation: drop the advisory lock].
- [ ] T8. A successful switch stores `managed_consent_version = "managed-data-flow/v1"` and
  `managed_consent_at` equal to `Service.Now`, bumps `install_revision`, and writes one
  `assistant.runtime` audit row whose reason names `own->managed` and the version and contains
  no install value [mutation: skip `LogToolCall` / skip setting the consent columns].
- [ ] T9. The stored, decrypted install document has no `consent` member after a consented
  install; a later `update_install` patch `{"runtime":"managed"}` after switching back to own
  is refused for missing consent [mutation: keep consent in the document].
- [ ] T10. managed -> own succeeds without consent, with the flag off, with quota exhausted;
  consent columns are kept [mutation: require consent both ways].
- [ ] T11. Re-consent: a row with `runtime = 'managed'` and `managed_consent_version =
  "managed-data-flow/v0"` reports `NeedsManagedReconsent() == true`, `list_assistants.mine.
  managed_reconsent_required == true`, and `/mctl assistant` prints the renewal line; a
  managed -> managed write with the current consent clears it and refreshes the time
  [mutation: compare against an empty version only].
- [ ] T12. MCP: `install_assistant` accepts `runtime` and `consent`; unknown args still
  refused; the three kinds map to `managed_consent_required`, `managed_disabled`,
  `managed_quota`; audit rows hold only the kind; `update_install` honours top-level
  `consent` [mutation: drop a mapping case].
- [ ] T13. Descriptor snapshot test passes with regenerated files; product-update gate claims
  the change.
- [ ] T14. Manage page: renders the Runtime row and the checkbox with `db.ManagedConsentText`;
  posting `setting=runtime&value=managed` without the checkbox returns 422 and changes nothing;
  with it (flag on) saves; `value=own` saves without the checkbox [mutation: ignore the
  checkbox].
- [ ] T15. `/mctl assistant` prints `Runtime: own (your worker)` for a default profile and
  `Runtime: managed (platform worker)` for a managed one.
- [ ] T16. Admin route: `runtime` omitted leaves it unchanged; `runtime: "managed"` without
  consent is 409 `managed_consent_required`; flag off is 403; quota is 409; invalid value 400;
  `consent` and `runtime` keys accepted by the strict decoder [mutation: write `runtime`
  without `DecideRuntime`].
- [ ] T17. The verbatim consent constant appears in `docs/adr/0008-managed-runtime.md` after
  whitespace normalisation and stripping the italic markers.
- [ ] T18. Regression: an own-runtime install, update, `/mctl assistant` and admin upsert with
  the flag off produce the same profile as before (existing test suites unchanged).

## Rollback

- Revert the PR and redeploy. The added columns stay and are ignored by the old binary; no
  data is lost and no down-migration is needed.
- Faster, without a deploy: keep `MANAGED_RUNTIME_ENABLED` false (the deployed default), so no
  account can become managed; any account already managed can be switched back with
  `update_install {"runtime":"own"}` or the admin route, which needs no consent. No claim
  behaviour depends on the column in this slice, so a managed row is inert until #1090.
