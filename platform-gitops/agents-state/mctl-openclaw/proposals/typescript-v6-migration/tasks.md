# Tasks: typescript-v6-migration

- [ ] 1. Inventory current TypeScript version and affected config sites — DoD: a comment in the PR (or a committed `docs/ts6-migration-inventory.md`) lists every `tsconfig.json` in the workspace, the current TypeScript version, and which files contain `moduleResolution: classic`, `esModuleInterop: false`, implicit `types`, or an implicit `target`; baseline build time (three consecutive `tsc -b` runs) recorded for comparison.

- [ ] 2. Upgrade TypeScript devDependency to 6.0.3 (depends on 1) — DoD: root `package.json` (and any per-package `package.json` that pins TypeScript) specifies `"typescript": "6.0.3"`; `npm install` succeeds; `package-lock.json` updated and committed; `tsc --version` reports `6.0.3` in the workspace; the build is expected to fail at this point — failure output is captured in the PR description as the starting point for subsequent tasks.

- [ ] 3. Fix `moduleResolution: classic` across all tsconfig files (depends on 2) — DoD: no `tsconfig.json` in the workspace contains `moduleResolution: classic`; each affected config uses `moduleResolution: node16` or `moduleResolution: bundler` as appropriate for its module format; all import paths that required implicit resolution have been updated to explicit paths where the new resolver demands it; `tsc -b` no longer reports `moduleResolution`-related errors.

- [ ] 4. Fix `esModuleInterop: false` across all tsconfig files (depends on 2) — DoD: no `tsconfig.json` in the workspace contains `esModuleInterop: false`; any import statements that relied on the old interop behavior have been updated; `tsc -b` no longer reports `esModuleInterop`-related errors.

- [ ] 5. Audit and fix `types` arrays (depends on 2) — DoD: every `tsconfig.json` that previously omitted `types` (relying on the old auto-include default) now has an explicit `"types": [...]` array listing only the `@types/*` packages that the package actually uses; no `@types/*` package is missing at compile time; `tsc -b` produces no errors related to missing type declarations.

- [ ] 6. Audit and fix `target` fields (depends on 2) — DoD: every `tsconfig.json` has an explicit `target` field; configs that were relying on the old implicit default now specify `"target": "ES2023"` (or a justified older target with a comment explaining why); `tsc -b` produces no warnings or errors related to `target`.

- [ ] 7. Full clean build with zero errors (depends on 3, 4, 5, 6) — DoD: `tsc -b --force` completes with zero errors and zero warnings in the workspace; build output artifacts are present and structurally identical to the pre-migration artifacts (same file set, same module shapes as verified by a diff of the compiled output directories).

- [ ] 8. Add `tsconfig-lint` CI step (depends on 7) — DoD: a CI job (or step within an existing job) runs a grep-based check that exits non-zero if any `tsconfig.json` in the workspace contains `moduleResolution.*classic` or `esModuleInterop.*false`; the job also runs `tsc -b --noEmit` and fails on any type error; the job is marked required and blocks merges; confirmed passing on the migrated branch.

- [ ] 9. Measure and record build time improvement (depends on 7) — DoD: three consecutive `tsc -b` runs executed on the migrated branch in CI; median build time recorded; improvement relative to the task 1 baseline documented in the PR description; result is at least 15% faster (if not, an explanation is provided but the task is not blocked).

- [ ] 10. Update `CONTRIBUTING.md` with TypeScript version policy (depends on 8) — DoD: a section "TypeScript Compiler Version" is added explaining that the workspace targets TypeScript 6.x, that `moduleResolution: classic` and `esModuleInterop: false` are prohibited, that `types` and `target` must always be explicit, and that any TypeScript version bump follows the normal PR review process.

## Tests

- [ ] T1. Clean build assertion — `tsc -b --force` in CI on the migrated branch exits 0 with no errors or warnings.

- [ ] T2. `tsconfig-lint` rejects legacy settings — introduce a temporary `tsconfig.json` containing `moduleResolution: classic` in a test branch; confirm the `tsconfig-lint` CI step exits non-zero and names the offending file.

- [ ] T3. Integration test suite passes — the full existing integration test suite (all three tenant configurations if applicable) passes against the compiled output of the migrated build; no behavioral regressions detected.

- [ ] T4. Docker image behavior equivalence — build the Docker image from the migrated source and run the smoke-test suite against it; confirm all endpoints respond as expected and no startup errors appear in logs.

- [ ] T5. Build time benchmark — median of three `tsc -b` runs on the migrated branch is at least 15% lower than the baseline recorded in task 1.

- [ ] T6. `types` completeness — run `tsc --strict --noEmit` after removing all `node_modules/@types` packages not listed in the explicit `types` arrays; confirm the build still passes, proving no phantom type inclusions are in use.

## Rollback

TypeScript is a build-time-only dependency. Rolling back is straightforward:

1. Revert the `package.json` TypeScript version change to the previous 5.x pin.
2. Run `npm install` to restore the previous `package-lock.json` state (or restore it from git).
3. Revert any `tsconfig.json` changes.
4. Rebuild the Docker image using the restored build toolchain.
5. No running tenant is affected — the rollback only touches CI and the developer build environment.

No ArgoCD sync, no Kubernetes change, and no S3 state change is required to roll back this migration.
