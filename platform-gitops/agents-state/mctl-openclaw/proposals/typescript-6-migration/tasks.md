# Tasks: typescript-6-migration

- [ ] 1. Audit all `tsconfig.json` files in the workspace — DoD: A migration matrix is produced (as a PR comment or internal doc) listing every `tsconfig.json` path and the current explicit/implicit state of `strict`, `module`, `target`, `types`, and `moduleResolution`. Includes `extensions/*` and the workspace root.

- [ ] 2. Add explicit values to each `tsconfig.json` to preserve TS 5.x behaviour under TS 6.0 (depends on 1) — DoD: Every `tsconfig.json` in the workspace has explicit values for `strict`, `module`, `target`, `types`, and `moduleResolution` (replacing deprecated `node` with `node16` or `bundler` as appropriate). PR reviewed and approved; no code changes in this PR.

- [ ] 3. Bump `typescript` devDependency to `6.0.3` in the root `package.json` (depends on 2) — DoD: `package.json` and lockfile updated; `tsc --version` reports `6.0.3`.

- [ ] 4. Run full workspace build (`tsc -b`) with TypeScript 6.0.3 and collect errors (depends on 3) — DoD: Build output is recorded; all errors are catalogued with file paths, error codes, and root causes. Zero errors expected if Phase 2 was complete; any residual errors are filed as sub-tasks.

- [ ] 5. Fix all type errors surfaced in Phase 3/4 (depends on 4) — DoD: `tsc -b` across the entire workspace produces zero errors and zero deprecated-option warnings. Each fix is a discrete commit. Any fix requiring a semantic code change is reviewed independently. No `@ts-ignore` or `ts-nocheck` suppressions are added without a paired tracking task.

- [ ] 6. Run integration test suite against the migrated build (depends on 5) — DoD: All existing integration tests pass. Docker images built from the migrated workspace are verified to produce identical runtime behaviour to the pre-migration baseline (channel connect/reconnect paths pass).

- [ ] 7. Add CI lint gate to reject deprecated `tsconfig.json` options (depends on 5) — DoD: CI pipeline includes a step that fails if any `tsconfig.json` in the workspace specifies `moduleResolution: node` or omits explicit values for `strict`, `module`, `target`, or `types`. Gate verified by introducing a violation and confirming CI fails.

- [ ] 8. Update root CI type-check step to use `tsc -b --noEmit` with TypeScript 6.0.3 (depends on 6) — DoD: CI `typecheck` job runs `tsc -b --noEmit`; any type error fails the build. Step is listed as required in the PR gate checks.

- [ ] 9. Reconcile with `typescript-v6-migration` proposal (depends on 1) — DoD: The engineering team reviews both `proposals/typescript-v6-migration/` and `proposals/typescript-6-migration/` and closes one (or merges the task lists). A note is added to the closed proposal's folder indicating which one supersedes it.

- [ ] 10. Update workspace documentation and onboarding notes (depends on 8) — DoD: Any developer setup guide or CONTRIBUTING.md that references TypeScript version or `tsconfig` setup is updated to reflect TS 6.0.3 requirements. PR reviewed and merged.

## Tests

- [ ] T1. Compiler version check: `npx tsc --version` in the workspace root reports `6.0.3`.
- [ ] T2. Full build: `tsc -b` across the workspace completes with zero errors and zero deprecated-option warnings.
- [ ] T3. `--noEmit` CI gate: `tsc -b --noEmit` in CI fails on a branch where a deliberate type error is introduced, confirming the gate is live.
- [ ] T4. No deprecated options: a script scanning all `tsconfig.json` files for `moduleResolution: node` reports zero matches.
- [ ] T5. No implicit defaults: the migration matrix from Task 1 is verified to have zero `tsconfig.json` files with implicit values for `strict`, `module`, `target`, or `types`.
- [ ] T6. Integration test suite: all existing channel integration tests pass against Docker images built from the migrated workspace.
- [ ] T7. Lint gate enforcement: CI rejects a PR that introduces `"moduleResolution": "node"` into any `tsconfig.json`.
- [ ] T8. No `@ts-ignore` additions: `git diff origin/main` for the migration PR contains zero new `@ts-ignore` or `ts-nocheck` suppressions.

## Rollback

This is a build-time-only change. No deployed runtime or Kubernetes resource is modified.

**If the TypeScript bump causes unexpected CI failures after merging:**

1. Revert the `typescript` devDependency to the previous version in `package.json` and regenerate the lockfile.
2. Revert any `tsconfig.json` changes that introduced regressions.
3. The revert PR is merged; CI returns to the pre-migration state.
4. The problematic type errors or config conflicts are diagnosed and resolved in a follow-up PR before re-attempting the migration.

Because no Docker image or deployed service is changed by this proposal, a rollback has no impact on any running tenant (`labs`, `admins`, `ovk`). There is no S3 state or pod restart involved.
