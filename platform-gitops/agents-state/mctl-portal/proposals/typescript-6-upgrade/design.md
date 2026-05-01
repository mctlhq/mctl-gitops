# Design: typescript-6-upgrade

## Current state
`mctl-portal` is a Backstage monorepo compiled with `backstage-cli` on top of TypeScript (version
below 6.0 — the exact pinned version is not recorded in `context/architecture.md`). Yarn Berry
manages three workspace groups: `packages/app`, `packages/backend`, and `plugins/*`. Each package
has its own `tsconfig.json` that extends a shared root `tsconfig.json`. TypeScript is invoked both
by `backstage-cli package build` (per-package compilation) and by a root-level `tsc --noEmit` step
in CI for type-checking. Node.js 22 is the runtime. Playwright covers end-to-end scenarios;
Prettier and the Backstage ESLint preset cover formatting and linting.

See `context/architecture.md` for the full tech-stack description.

## Proposed solution

### Overview
Pin TypeScript to `^6.0.3` in the root `package.json` (dev dependency) and let Yarn Berry's
`packageExtensions` or `resolutions` field ensure every workspace package resolves the same
TypeScript binary. Update the root `tsconfig.json` to use `"target": "ES2022"` and the
`"module": "Node16"` / `"moduleResolution": "Node16"` settings that TypeScript 6 recommends as
defaults. Run a workspace-wide compilation to surface all errors, then fix them iteratively.

### Step-by-step approach

1. **Audit breaking changes.** Review the TypeScript 6.0 release notes
   (https://github.com/microsoft/TypeScript/releases/tag/v6.0.3) and produce a list of checks that
   affect the portal's code patterns (e.g., stricter template-literal narrowing, changes to
   `namespace` handling, `verbatimModuleSyntax` defaults).

2. **Update the root `package.json`.** Change the `typescript` dev-dependency specifier to
   `^6.0.3`. Add or update a `resolutions` (or `packageExtensions`) entry in `.yarnrc.yml` so
   transitive deps that peer-depend on TypeScript do not pull in an older version.

3. **Update root `tsconfig.json`.** Align compiler options to TypeScript 6 recommendations while
   preserving the settings that Backstage's scaffolded tsconfigs expect. Specifically:
   - Set `"moduleResolution": "Bundler"` or `"Node16"` as appropriate for `backstage-cli`.
   - Enable `"exactOptionalPropertyTypes": true` only if the codebase audit confirms zero regressions
     (otherwise leave for a follow-up).
   - Retain `"strict": true`.

4. **Fix compilation errors per workspace.** Work through `packages/app`, `packages/backend`, then
   `plugins/*` in dependency order. Errors are expected in areas the TS 6 breaking-change audit
   identified.

5. **Validate `backstage-cli` compatibility.** Confirm that the version of `backstage-cli` in use
   declares TypeScript 6 as a supported peer dependency. If not, identify the minimum `backstage-cli`
   version that does, pin it, and run `yarn backstage-diff` to surface any scaffolding drift.

6. **CI green gate.** Add a version-assertion step (`node -e "require('typescript').version"`)
   to CI that fails if the resolved TypeScript version is not `6.0.x`.

### Why this approach
Pinning at the root and using Yarn resolutions is the standard Backstage monorepo practice for
tooling dependencies. It avoids having to touch each workspace's `package.json` individually and
guarantees a single TypeScript binary is used across all compilation steps.

## Alternatives

### A. Upgrade TypeScript per-workspace only
Update `typescript` in each `packages/*/package.json` and `plugins/*/package.json` individually.
Rejected because it increases diff size, risks version drift between workspaces, and does not follow
Backstage's recommended monorepo setup.

### B. Defer upgrade until Backstage officially requires TypeScript 6
Wait for a future `backstage-cli` release that drops support for TypeScript 5.x. Rejected because
TypeScript 6 strict checks already provide measurable DX value today, and deferring means
accumulating a larger fix burden when the upgrade becomes mandatory.

### C. Use TypeScript 6 only in a type-checking pass, keep 5.x for build
Configure a second `tsconfig.check.json` with TypeScript 6 while `backstage-cli` continues to
compile with TypeScript 5.x via its own bundled resolution. Rejected because it creates two sources
of truth and does not actually pin the runtime TypeScript version used by `backstage-cli`.

## Platform impact

### Migrations
- `package.json` root dev-dependency change (`typescript` version bump).
- `.yarnrc.yml` or `package.json` `resolutions` addition.
- Root `tsconfig.json` compiler-option changes.
- Per-file source fixes for compilation errors surfaced by TypeScript 6 strict checks.

### Backward compatibility
The change is entirely in compile-time tooling. No API surface, HTTP contracts, or runtime behaviour
of `mctl-portal` changes. Rollback restores the previous TypeScript version and tsconfig.

### Resource impact
Compilation time may increase slightly (TypeScript 6's additional analysis). This is a CI-only cost;
there is no runtime memory or CPU impact on the deployed pod. Tenant `admins` is not near its memory
limit, and no `labs` workloads are affected by this change.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| `backstage-cli` is incompatible with TypeScript 6 at upgrade time | Medium | Confirm compatibility before merging; block on a `backstage-cli` bump if needed |
| Large volume of compilation errors requiring extended fix time | Medium | Time-box the fix phase; open a follow-up proposal for `exactOptionalPropertyTypes` if needed |
| Transitive plugin dependency pins an older TypeScript version | Low | Yarn `resolutions` override prevents this |
| Post-merge runtime regression (unlikely for a compile-only change) | Low | Playwright e2e suite must pass before merge; rollback procedure documented in `tasks.md` |
