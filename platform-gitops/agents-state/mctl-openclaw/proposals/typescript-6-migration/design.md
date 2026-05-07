# Design: typescript-6-migration

## Current state

The mctl-openclaw workspace uses TypeScript (see `context/architecture.md`). Workspace packages live in `extensions/*` and import from `openclaw/plugin-sdk/*`. Each package has its own `tsconfig.json`, and a root `tsconfig.json` ties them together via project references.

The workspace was authored against TypeScript 5.x, where the following defaults applied:
- `strict`: off by default
- `module`: `commonjs` by default
- `target`: `es5` by default
- `types`: includes all `@types/*` packages in `node_modules` by default
- `moduleResolution node`: supported (and commonly implicit)

TypeScript 6.0.3 (stable as of 2026-04-16) changes all of these defaults:

| Option | TS 5.x default | TS 6.0 default | Breaking? |
|---|---|---|---|
| `strict` | `false` | `true` | Yes — surfaces new errors in unguarded code |
| `module` | `commonjs` | `esnext` | Yes — changes emit format |
| `target` | `es5` | `es2025` | Yes — changes emit target |
| `types` | all `@types/*` | `[]` (empty) | Yes — removes implicit ambient types |
| `moduleResolution node` | supported | deprecated | Yes — must be replaced with `bundler` or `node16` |

Without explicit values for these options in every `tsconfig.json`, upgrading the `typescript` devDependency will immediately change build behaviour.

## Proposed solution

**Controlled, explicit-first migration**: audit every `tsconfig.json` in the workspace, add explicit values for each changed default to preserve current behaviour (or adopt the new default where it is safe), fix any type errors that the new strict settings surface, and pin `typescript` to `^6.0.3` across the workspace.

### Migration phases

**Phase 1 — Audit (no code changes)**
Enumerate all `tsconfig.json` files in `extensions/*` and the workspace root. For each file, record which of the five changed options is currently explicit vs. implicit. Produce a migration matrix.

**Phase 2 — Explicit baseline (tsconfig changes only)**
For each `tsconfig.json`, add explicit values that reproduce the existing TS 5.x behaviour under TS 6.0. For example, if the package currently builds fine with `strict: false`, add `"strict": false` explicitly. This phase makes the upgrade non-breaking before any code is touched.

**Phase 3 — Compiler bump and error surfacing**
Update `typescript` devDependency to `6.0.3` in the root `package.json`. Run `tsc -b` across the workspace. Collect any remaining type errors (these will arise from packages that were implicitly relying on ambient types removed by `types: []`, or from `moduleResolution node` deprecation warnings).

**Phase 4 — Error resolution**
Fix all type errors surfaced in Phase 3. Each fix is a discrete commit. Errors that require a semantic code change are tracked as separate tasks.

**Phase 5 — Optional strict adoption**
For packages where the team agrees to adopt the new stricter defaults (e.g., setting `strict: true`), do so incrementally per package in follow-up PRs. This phase is optional within this proposal's scope.

**Phase 6 — CI lint gate**
Add a CI step that runs `tsc --noEmit` with the TypeScript 6.0.3 compiler and fails if any error or deprecated-option warning is produced. Add a tsconfig lint rule (e.g., via a custom ESLint rule or a shell script) that rejects `tsconfig.json` files missing explicit values for the four changed defaults.

### Why explicit-first rather than adopt-new-defaults immediately

Adopting all new defaults at once (strict on, esnext module, es2025 target) across the entire workspace in one PR creates a large diff and a high risk of introducing subtle runtime behaviour changes in the emitted JavaScript. The explicit-first approach makes the TypeScript version bump a zero-diff-in-behaviour change, and then allows selective adoption of stricter settings on a per-package basis with targeted review.

## Alternatives

### A. Do nothing until a developer or CI hits the error

This is the status quo. The risk is a surprise build failure in a developer's local environment or in CI, triggered by an automatic toolchain upgrade outside our control. The remediation under time pressure is more expensive than the planned migration. Rejected.

### B. Adopt all TypeScript 6.0 new defaults immediately across the entire workspace

This produces the most modern and correct configuration but requires resolving all newly-surfaced type errors in a single PR. For a workspace with many extension packages and channel integrations, this is a large scope with significant review burden. If the PR is blocked by a hard-to-fix type error in one extension, it delays the entire migration. Rejected in favour of the phased approach, though individual packages may opt in via the optional Phase 5.

### C. Use `ts-nocheck` or `@ts-ignore` to suppress errors after the bump

This would technically unblock the build but hides real type-safety issues and accumulates tech debt. Rejected; the acceptance criteria explicitly prohibit suppression without a tracked fix.

## Platform impact

### Migrations

No runtime migration is required. TypeScript is a build-time devDependency; it is not included in the deployed Docker image. There is no S3 state, Kubernetes manifest, or ArgoCD change involved.

### Backward compatibility

The emitted JavaScript must be verified to be runtime-equivalent before and after the migration. The CI integration test suite is the gate for this. If a changed `target` or `module` setting changes emitted output, the explicit-first approach (Phase 2) preserves the previous behaviour until the team deliberately opts in.

### Resource impact (`labs`)

None. TypeScript is a build-time tool. The compiled JavaScript and Docker images are unaffected. There is zero RSS change for `labs` or any other tenant.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| An extension package has a hard-to-fix type error under strict mode | Phase 2 preserves `strict: false` for that package explicitly; strict adoption is deferred to Phase 5 and tracked separately. |
| `moduleResolution` change affects import resolution in an extension | Phase 2 replaces deprecated `node` with `node16` or `bundler` as appropriate for the package's module system; validated by build + integration tests. |
| `types: []` removes ambient types that an extension relied on implicitly | Phase 3 surfaces these errors; fix is to add the specific `@types/*` package to the `types` array explicitly. |
| Developer opens a PR that re-introduces a deprecated option | Phase 6 CI lint gate rejects the PR automatically. |
| Overlap with `typescript-v6-migration` proposal | The two proposals (`typescript-v6-migration` and `typescript-6-migration`) cover the same intent. One should be closed after review; this proposal reflects the analyst's 2026-05-07 framing and should be reconciled with the earlier one before work begins. |
