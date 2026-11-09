# Tasks: issue-986-feat-bridge-versioned-typed-read-result

- [ ] 1. Vendor the canonical v1alpha2 `command.schema.json`, `result.schema.json`
  and `read-result.schema.json` from mctl-agents into
  `internal/bridge/schema/v1alpha2/`, together with a `PROVENANCE` file (repo,
  PR, merge commit, three sha256). Do not touch the v1alpha1 files. This task is
  gated: if the canonical files are not merged upstream, stop here and do not
  author them locally. — DoD: the files are byte-identical to upstream, and
  `PROVENANCE` digests match.
- [ ] 2. (depends on 1) Extend `internal/bridge/schema.go`:
  - embed and compile the v1alpha2 URLs next to v1alpha1;
  - add `SchemaVersionV1Alpha2`;
  - make `ParseResult` dispatch on `schema_version`;
  - add `ReadResult` typed structs (per kind) and `Result.ReadResult` with
    `omitempty`;
  - extend `SchemaDigests` (or add a v1alpha2 variant).

  DoD: the v1alpha1 parse output and `Digest()` are unchanged for existing
  fixtures, and v1alpha2 fixtures parse.
- [ ] 3. (depends on 2) Add read kinds to `store.go`:
  - add the `Kind*` constants and an `IsReadKind` helper;
  - in `bridgeSchema`, add the `wire_version` column, the widened
    `bridge_commands_kind_chk`, `bridge_commands_read_wire_chk`, and the
    `bridge_read_results` table and index;
  - make `Enqueue` set `wire_version` from the kind;
  - make `projection()` emit the stored wire version.

  DoD: the DDL applies twice cleanly on an existing v1alpha1 database, and
  read-kind commands are claimed with `schema_version=bridge.mctl.ai/v1alpha2`.
- [ ] 4. (depends on 3) Extend `submitTx` with the read rules from design.md
  section 3:
  - the version binding and the read/kind consistency checks;
  - the 8 KiB canonical size cap and the server digest check;
  - the server-minted `res_`;
  - the same-transaction `bridge_read_results` insert;
  - the reference-only `redacted()` form;
  - the replay lookup;
  - `SubmitOutcome.ResultRef`.

  Extend `ReadOutcome` with ref and digest fields. DoD: the existing
  `submitTx` behaviour for v1alpha1 is unchanged, and the new code paths return
  only existing codes from `errors.go`.
- [ ] 5. (depends on 3) Add the `ConnectionChecker` interface,
  `DenyConnectionChecker` (fail-closed default) and `Store.SetConnectionChecker`.
  Add `Store.FetchReadResult` with the check order from design.md section 4,
  using constant-time digest compare. Add a new sentinel for "checker
  unavailable". DoD: every refusal maps to an existing closed code.
- [ ] 6. (depends on 5) Add the HTTP handler `BridgeReadResult` in
  `internal/api/handlers_bridge.go`:
  - add `FetchReadResult` to `BridgeService`;
  - mount `GET /api/v1/glovo/read-results/{result_ref}` in `router.go` only
    under `opts.BridgeEnabled`;
  - add the exact method and path to `glovoAudienceRoutes`;
  - map the checker-unavailable sentinel to `bridge_unavailable` 503;
  - set `Cache-Control: no-store`;
  - audit ids, digests and codes only.

  Return `result_ref` from `BridgeResult`. DoD: the route answers 404 when
  disabled and 403 for bridge providers.
- [ ] 7. (depends on 3) Add `EraseExpiredReads` and call it from the `Expirer`
  tick. Add the `mctl_api_bridge_read_results_erased_total` metric and the
  `MCTL_BRIDGE_READ_RESULT_TTL` env in `cmd/api/main.go` (default 600 s,
  clamped 1..900 s). DoD: expired rows have `data IS NULL` after a sweep.
- [ ] 8. (depends on 4-7) Update `docs/bridge.md` with a "Read results
  (v1alpha2)" section: wire, route, codes, data-handling guarantees, v1alpha1
  compatibility and rollback. Run `go fmt`, `go vet` and `golangci-lint`. DoD:
  the lint is clean and the docs match the code.

## Tests

- [ ] T1. Provenance: v1alpha1 digests are unchanged
  (`TestVendoredSchemasMatchProvenance`), and the v1alpha2 files match their
  own `PROVENANCE`.
- [ ] T2. Compatibility golden: pinned `testdata/v1alpha1/*.golden.json`
  (command projection, result digest) is unchanged after the change. The
  existing `command.valid.json` and `result.valid.json` still parse, and a
  v1alpha1 result containing `read_result` is refused (`invalid_document`).
- [ ] T3. v1alpha2 fixtures: one valid fixture per read kind, and invalid
  fixtures for each of these:
  - extra field;
  - non-synthetic `provenance`;
  - over `maxItems`;
  - wrong kind under `data`.
- [ ] T4. Cross-tenant fetch: a caller from tenant B with a valid ref and digest
  of tenant A gets 404 `command_not_found`, and the body is identical to an
  unknown ref.
- [ ] T5. Cross-principal fetch: same tenant, different principal gets 404
  `command_not_found`.
- [ ] T6. Expired result: after the TTL the fetch returns `command_expired`, and
  after the sweep `data` is NULL.
- [ ] T7. Revoked connection: the fake checker returns inactive, or the
  install revision has changed, and the fetch returns `binding_mismatch`. When
  the checker errors, the fetch returns `bridge_unavailable` 503. The default
  checker always refuses.
- [ ] T8. Replay. An identical resubmission returns `replayed:true`, the same
  `result_ref` and one row. Resubmitting with different data returns
  `result_conflict`, and the row is unchanged.
- [ ] T9. Wrong digest on submission (declared differs from computed) returns
  `binding_mismatch`, and no read row is created. A wrong digest on fetch
  returns `binding_mismatch`.
- [ ] T10. Oversize: canonical data over 8 KiB returns `invalid_document`. A
  body over `bridgeMaxBody` returns `invalid_document`. Nothing is stored.
- [ ] T11. Concurrent submissions (N goroutines, Postgres test, as in
  `store_pg_test.go`) create exactly one read row and one outbox row.
  Concurrent fetches return byte-identical bodies.
- [ ] T12. Consistency: each of the following returns `result_inconsistent`:
  - a read kind with `provider_effect=applied`;
  - a provider `result_ref` on a read kind;
  - a missing `read_result` on success;
  - a kind mismatch;
  - a `read_result` on `quote`.

  A v1alpha1 result for a v1alpha2 command returns `binding_mismatch`.
- [ ] T13. Write fence: `IssueWritePermit` on every read kind returns
  `not_mutating`, and the existing permit tests pass unchanged.
- [ ] T14. No data leakage. A sentinel string inside `data` must not appear in
  any of these:
  - `bridge_commands.result`;
  - `bridge_signal_outbox`;
  - `ReadOutcome`;
  - audit entries;
  - the captured slog output.
- [ ] T15. Route gating: the fetch route answers 404 when the bridge is
  disabled, 403 `bridge_provider_gate` for a bridge provider, and is reachable
  by a Glovo-audience token. The Glovo-audience token is still refused on every
  other route (extend `glovo_audience_test.go`).

## Rollback

- Unset `MCTL_BRIDGE_ENABLED` (already the default). The read route and all
  bridge routes then answer 404, and nothing else changes.
- Revert the PR. The added column, table and constraints are harmless when
  left in place: `wire_version` has a default, and the widened CHECK accepts
  everything the old one did.
- To remove the storage, cancel open read-kind commands through `Store.Cancel`
  and then run `DROP TABLE bridge_read_results`. The
  `wire_version` column can stay or be dropped once no v1alpha2 commands
  remain.
- The v1alpha1 vendored schemas never change, so v1alpha1 consumers are
  unaffected by both forward and rollback.
