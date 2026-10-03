# Tasks: techdocs-mkdocs-code-exec-v2

- [ ] 1. Confirm current resolved version of `@backstage/plugin-techdocs-node`
      in `yarn.lock` and whether `techdocs-mkdocs-code-exec` (1.14.3 bump)
      has already been applied — DoD: version status documented, and this
      proposal's starting point (bump-from-1.14.3 vs bump-from-earlier) is
      clear.
- [ ] 2. Bump `@backstage/plugin-techdocs-node` to `>=1.14.6` (1.14.x line)
      or `>=1.15.4` (1.15.x line) in `packages/backend` (depends on 1) —
      DoD: `yarn.lock` resolves to a compliant version; `yarn install`
      succeeds with no unresolved peer-dependency conflicts.
- [ ] 3. Switch the MkDocs config parser to a safe-only YAML loader that
      rejects unsafe Python tags (`!!python/object`, `!!python/name`, etc.)
      (depends on 2) — DoD: parser rejects a test fixture containing an
      unsafe tag before any MkDocs invocation.
- [ ] 4. Extend the existing plugin/hook allowlist check (from
      `techdocs-mkdocs-code-exec`) to also validate `markdown_extensions`
      entries against an approved allowlist (depends on 3) — DoD: a test
      fixture with a non-allowlisted extension is rejected with an
      ERROR-level log entry naming the field.
- [ ] 5. Add validation for `theme` options, restricting to an allowlisted
      key set (depends on 3) — DoD: a fixture with a disallowed theme
      option (e.g. arbitrary `custom_dir`) is rejected.
- [ ] 6. Add validation for `extra_templates` paths, rejecting any path
      that resolves outside the component's declared docs root (depends
      on 3) — DoD: a fixture with a path-traversal `extra_templates` entry
      is rejected.
- [ ] 7. Update the CI dependency-audit gate's version floor from 1.14.3 to
      1.14.6/1.15.4 (depends on 2) — DoD: CI fails a synthetic build pinned
      below the new floor.
- [ ] 8. Roll out validation in warn-only mode for one cycle, then flip to
      hard-enforce (depends on 4, 5, 6) — DoD: warn-only log volume
      reviewed with no unexpected legitimate-build breakage before
      enforcement is turned on.

## Tests
- [ ] T1. Unit test: unsafe YAML tag in `mkdocs.yml` is rejected before
      MkDocs invocation, no external process spawned.
- [ ] T2. Unit test: non-allowlisted `markdown_extensions` entry is
      rejected with a named-field ERROR log.
- [ ] T3. Unit test: disallowed `theme` option is rejected.
- [ ] T4. Unit test: `extra_templates` path traversal is rejected.
- [ ] T5. Integration test: a fully allowlist-compliant `mkdocs.yml` builds
      and publishes successfully end-to-end.
- [ ] T6. Dependency-audit CI test: a synthetic lock-file pinned below
      1.14.6/1.15.4 fails the audit gate.
- [ ] T7. Regression smoke test: sample of real catalog components' docs
      builds still succeed after warn-only rollout, before hard enforcement.

## Rollback
Revert the `@backstage/plugin-techdocs-node` version bump and the new
validation checks via a single revertible commit/PR. Because validation is
additive (fails closed only on new checks), rollback restores the
`techdocs-mkdocs-code-exec` (1.14.3) baseline behavior, which remains a
valid, if less complete, mitigation for CVE-2026-29186 while this follow-on
fix is reworked. If warn-only rollout surfaces high false-positive rates,
roll back to warn-only (do not hard-enforce) rather than fully reverting.
