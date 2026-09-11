# Tasks: issue-283-feat-agent-platform-publish-and-resolve

- [ ] 1. Add the v1alpha2 record types in `internal/agentregistry/v1alpha2_types.go`
      (`DefinitionVersion`, `ProfileVersion`, `SourceManifest`, `ReleaseBinding`,
      `ResolvedBinding`), plus lifecycle constants (`LifecyclePublished`,
      `LifecycleDeprecated`, `LifecycleDisabled`), binding-source constants
      (`BindingSourceRegistry`, `BindingSourceManual`,
      `BindingSourceCompatibilityFixture`) and new sentinel errors
      (`ErrDefinitionVersionNotFound`, `ErrProfileVersionNotFound`,
      `ErrVersionDeprecated`, `ErrVersionDisabled`, `ErrIncompatibleProfile`,
      `ErrFixtureNotPromotable`, `ErrBindingNotFound`, `ErrInvalidRange`,
      `ErrInvalidLifecycleTransition`, `ErrMissingPolicyFields`) — DoD:
      `go build ./...` passes; every error follows the existing
      `errors.New("agentregistry: ...")` convention in `store.go:32-40`.

- [ ] 2. Write `internal/agentregistry/semver.go` (depends on 1) — `ParseVersion`,
      `ParseRange`, `Range.Satisfies`, supporting `MAJOR.MINOR.PATCH` and
      `>= > <= < =`, `^`, `~` comparators joined by spaces or commas, returning
      `ErrInvalidRange` for anything else — DoD: no new module in `go.mod`;
      `go vet` clean; unknown syntax is rejected, never silently satisfied.

- [ ] 3. Extend `agentRegistrySchema` in `internal/agentregistry/store.go`
      (depends on 1) with `agent_definition_versions`, `agent_profile_versions`,
      `agent_release_bindings` (+ `agent_release_bindings_current` index) and the
      four `ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS`
      (`definition_version`, `profile`, `profile_version`, `binding_revision`) —
      DoD: `NewStore` against an existing pre-change database creates everything
      with no error and no change to existing rows; re-running is a no-op.

- [ ] 4. Implement publish + lifecycle in `internal/agentregistry/v1alpha2_store.go`
      (depends on 2, 3): `PublishDefinitionVersion`, `PublishProfileVersion`,
      `ListDefinitionVersions`, `ListProfileVersions`,
      `SetDefinitionVersionLifecycle`, `SetProfileVersionLifecycle` — DoD:
      duplicate `(agent, version)` / `(profile, version)` maps pg `23505` to
      `ErrVersionConflict` and `23503` to `ErrDefinitionNotFound`, exactly as
      `PublishVersion` does today; an unparseable `profile_range` is rejected
      before insert; only `published -> deprecated`, `published -> disabled`,
      `deprecated -> disabled` are accepted.

- [ ] 5. Implement `CreateBinding` (depends on 4) with the transaction shape of
      `Store.promote` (`store.go:337-425`): `BEGIN`,
      `pg_advisory_xact_lock(hashtext(agent + "/" + environment))`, load both
      versions `FOR SHARE`, lifecycle check, `semver` compatibility check,
      `compatibility-fixture` rejection, `MAX(revision)+1` insert, `COMMIT` —
      DoD: every rejection returns its specific sentinel error and writes
      nothing; concurrent binds never duplicate or skip a revision.

- [ ] 6. Implement `ResolveBinding(agent, environment)`,
      `ResolveExplicit(agent, definitionVersion, profileVersion)`,
      `GetBinding(agent, environment, revision)`, `ListBindings(agent, environment)`
      and `RollbackBinding(agent, environment, revision, reason, actor)`
      (depends on 5) — DoD: resolve returns the active binding as
      `ORDER BY revision DESC LIMIT 1` with no stored `active` flag anywhere;
      rollback appends a new revision with `rollback_of` set to the restored
      row's `id` and re-validates lifecycle/compatibility inside the same
      transaction.

- [ ] 7. Extend `AgentExecution` / `RecordExecution` / `ListExecutions` in
      `internal/agentregistry/store.go` (depends on 3) with
      `DefinitionVersion`, `Profile`, `ProfileVersion`, `BindingRevision` —
      DoD: all four are optional; an existing caller sending only today's
      fields still succeeds and the stored row is unchanged in every other
      column.

- [ ] 8. Add `writeErrorCode(w, status, code, message, details)` next to
      `writeError` in `internal/api/handlers_read.go:856` — DoD: `writeError`
      is untouched; the new helper emits `{"error","code","details"}`.

- [ ] 9. Add `internal/api/handlers_agent_platform.go` (depends on 6, 8) with
      `ListAgents`, `GetAgent`, `PublishDefinitionVersion`,
      `ListDefinitionVersions`, `SetDefinitionVersionLifecycle`,
      `PublishProfileVersion`, `ListProfileVersions`,
      `SetProfileVersionLifecycle`, `CreateBinding`, `ListBindings`,
      `GetBinding`, `ResolveBinding`, `RollbackBinding` — DoD: every handler
      starts with `requireAgentRegistryAdmin`; sentinel errors map to
      404/409/422/400 per requirements.md; `ResolveBinding` accepts either
      `environment` or `definition_version[&profile_version]` and rejects a
      request giving both or neither with 400; required-field and
      policy-ceiling validation lists every missing field in one response.

- [ ] 10. Register the new routes in `internal/api/router.go` next to the
      existing `// Agent registry` block (depends on 9), including the
      2-segment `GET /agents/{name}` the comment at router.go:327-331
      anticipated, and update that comment — DoD: `GET /api/v1/agents/executions`
      still reaches `ListAgentExecutions`, not `GetAgent`.

- [ ] 11. Add the seven MCP tools in `internal/mcp/server.go` (depends on 10):
      `mctl_publish_agent_definition_version`, `mctl_publish_agent_profile_version`,
      `mctl_set_agent_version_lifecycle`, `mctl_bind_agent_release`,
      `mctl_rollback_agent_binding`, `mctl_list_agents`, `mctl_get_agent`;
      register them in the `// Agent registry` block at server.go:169-176; gate
      the three destructive ones with `requireConfirm` as `toolPromoteAgent`
      does — DoD: every tool declares readOnly/destructive/idempotent hints.

- [ ] 12. Extend `toolResolveAgent` (depends on 11) with optional `api_version`
      (enum `v1`, `v1alpha2`, default `v1`), `definition_version` and
      `profile_version` arguments — DoD: a call passing only `agent_name` +
      `environment` produces the exact same request path and response as before.

- [ ] 13. Update the three MCP test contracts (depends on 11): tool count
      74 -> 81 at `internal/mcp/server_test.go:173`, `recordedHints` plus the
      pinned read-only set in `internal/mcp/annotations_test.go` (adding
      `mctl_list_agents` and `mctl_get_agent`), and an explicit
      `"enabled": false` entry with a reason for each of the seven tools in
      `docs/portal-allowlist.json` — DoD: `go test ./internal/mcp/...` passes.

- [ ] 14. Write `docs/agent-platform-registry.md` (depends on 9) — the
      `ResolvedBinding` response contract for `orchestrator/resolver.py`
      (naming the fields it copies into the `ExecutionPlan`: `agent`,
      `environment`, `revision`, `definition.version`, `profile.name`,
      `profile.version`, `definition.sourceManifest.gitSha`), the frozen
      compatibility-range grammar, the error-code table, and the push-based
      gitops reconciliation contract mapping `ReleaseBindingIntent` YAML fields
      to the `POST /bindings` payload, including that `bindingSource: registry`
      + `promotable: true` is the supported path and `compatibility-fixture`
      stays non-promotable — DoD: a reader can implement both the resolver call
      and the mctl-gitops follow-up PR from this document alone.

- [ ] 15. Add `scripts/seed-agent-platform.sh` (depends on 10) publishing a real
      `issue-investigator` definition version and its execution-profile version
      and binding them in `shadow` — DoD: running it against a live API leaves
      `GET /api/v1/agents/issue-investigator` showing one published definition
      version, one published profile version and revision 1 in `shadow`.

- [ ] 16. Update `README.md` (depends on 10, 14) with the new endpoints and a
      pointer to `docs/agent-platform-registry.md` — DoD: the agent-registry
      section states which endpoints are v1 image/release and which are
      v1alpha2 definition/profile/binding.

- [ ] 17. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
      `go test ./...` (depends on all above) — DoD: clean, per `CLAUDE.md`.

## Tests

- [ ] T1. `internal/agentregistry/semver_test.go` — table-driven over the full
      supported grammar plus rejected syntax (`>=1.0`, `1.x`, `latest`, empty),
      boundary cases (`>=2.0.0 <3.0.0` against `2.0.0`, `2.9.9`, `3.0.0`),
      `^1.2.3` and `~1.2.3` edges. No Postgres needed.
- [ ] T2. `internal/agentregistry/v1alpha2_store_test.go` publish paths
      (TEST_DATABASE_URL-gated, extending `newTestStore`'s cleanup list with the
      three new tables) — duplicate version conflicts, unknown agent,
      unparseable range, missing policy fields, lifecycle transition matrix.
- [ ] T3. Binding happy path: publish definition + profile, bind, resolve
      `(agent, environment)` returns revision 1 with both exact versions,
      both source manifests and `bindingSource`.
- [ ] T4. Binding rejections, one case each: incompatible range,
      `deprecated` definition, `disabled` profile, missing version,
      `compatibility-fixture` source, invalid environment — each asserting the
      specific sentinel error AND that no row was appended.
- [ ] T5. Append-only and rollback: bind A, bind B, roll back to revision 1 —
      revisions 1, 2, 3 all exist, revision 3 carries `rollback_of` pointing at
      revision 1's id and repeats its pair, and resolve returns revision 3.
      Plus: disable revision 1's profile, then assert rollback to it is rejected.
- [ ] T6. Concurrency: N goroutines calling `CreateBinding` for the same
      `(agent, environment)` produce N distinct gapless revisions (mirrors the
      race `Store.promote`'s advisory lock closed).
- [ ] T7. `internal/api/handlers_agent_platform_test.go` — status-code mapping
      for every sentinel error, 503 with no registry configured, 401
      unauthenticated, 403 non-admin, and `ResolveBinding` rejecting both-or-
      neither selector combinations with 400.
- [ ] T8. Explicit-pin resolve: `?definition_version=&profile_version=`
      returns the same envelope shape as the environment resolve and does not
      require any binding to exist.
- [ ] T9. `mctl_list_agents` / `mctl_get_agent` integration: an agent with both
      a v1 `agent_versions` row and v1alpha2 versions shows both, with
      per-version lifecycle and the active binding per environment.
- [ ] T10. Backward-compatibility regression: `POST /agents/{name}/versions`,
      `POST /agents/{name}/releases`, `GET /agents/{name}/resolve?environment=`
      and `POST /agents/executions` (without the new fields) produce
      byte-identical response shapes to before the change.
- [ ] T11. Router test pinning that `GET /api/v1/agents/executions` routes to
      `ListAgentExecutions` and not to the new `GET /agents/{name}`.
- [ ] T12. Execution identity: record an execution carrying
      `definition_version` / `profile` / `profile_version` / `binding_revision`
      and assert `GET /agents/executions` returns all four; and that a record
      omitting them still succeeds.
- [ ] T13. Schema idempotency: run `NewStore` twice against the same database
      and assert no error and no row loss (guards the ALTER/CREATE block).

## Rollback

Blast radius is bounded by construction: no existing table, column, route,
response field or MCP tool argument is modified, so a revert is a pure
removal.

1. **Disable the surface without a deploy.** The new endpoints are
   admin-only and every write requires an explicit MCP `confirm`. If a bad
   binding is published, `POST /api/v1/agents/{name}/bindings/rollback` with
   the last-known-good revision restores it as a new append-only revision —
   no redeploy, no gitops PR. Nothing consumes v1alpha2 bindings in
   production during this change (the resolver is still in `legacy` mode),
   so a broken binding cannot affect a running dev-loop.
2. **Revert the code.** `git revert` the PR and redeploy. The v1 image/release
   path is untouched, so the dev-loop pipeline keeps resolving through
   `agent_releases` exactly as before. The MCP tool count, annotation record
   and portal allowlist revert with it, so the build stays consistent.
3. **Leave the tables.** The new tables and the four `agent_executions`
   columns are additive and defaulted; a reverted binary simply ignores them.
   Drop them only if the feature is abandoned:
   `DROP TABLE agent_release_bindings, agent_profile_versions,
   agent_definition_versions;` then
   `ALTER TABLE agent_executions DROP COLUMN IF EXISTS definition_version, ...`
   — in that order, because of the foreign keys.
4. **If startup itself fails** (a schema statement erroring against the live
   database), `NewStore` returns an error and `cmd/api/main.go:214-234` logs
   it and leaves `AgentRegistry` nil: the agent-registry endpoints return 503
   while the rest of the API keeps serving. That is a degraded, not a fatal,
   failure mode — but it takes the v1 registry down with it, so T13 (schema
   idempotency against a pre-existing database) is the gate that must pass
   before merge.
