# Design: typescript-v6-migration

## Current state

The mctl-openclaw workspace uses TypeScript (version in the 5.x series) configured across multiple `tsconfig.json` files in the workspace packages. Legacy settings are present in at least the root and several package-level configs:

- `moduleResolution: classic` (removed in TypeScript 6.0).
- `esModuleInterop: false` (forbidden in TypeScript 6.0).
- `target` set to an ES version older than ES2023 (TypeScript 6.0 changes the default to ES2023; any explicit override older than ES2023 still compiles, but legacy-default-relying configs will shift behavior).
- `types` may be relying on the old default (all `@types/*` packages auto-included), while TypeScript 6.0 changes the default to an empty array, requiring explicit `types` declarations.

Build artifacts (JavaScript files) are produced at build time and baked into Docker images. TypeScript is a devDependency only; it is not present in production images and has no runtime memory footprint.

Reference: `context/architecture.md`.

## Proposed solution

### Step 1: Inventory

Run `tsc --version` across every workspace package to confirm the current TypeScript version. Run `tsc -b 2>&1 | grep -E "(classic|esModuleInterop)"` to enumerate all affected config sites. Document findings in the PR description.

### Step 2: Upgrade the TypeScript devDependency

Update `package.json` (root and any package that pins TypeScript independently) to `"typescript": "6.0.3"`. Run `npm install` (or `npm ci`) to update the lockfile. This will cause the build to fail on legacy settings — those failures are the guide for subsequent steps.

### Step 3: Fix `moduleResolution`

Replace every `"moduleResolution": "classic"` with `"moduleResolution": "bundler"` or `"moduleResolution": "node16"` depending on the package's module format. For workspace packages that use CommonJS output (the typical case for a Node.js service), `"moduleResolution": "node16"` is the correct replacement. This may require adding explicit file extensions or `index` entries to some import paths that TypeScript Classic was resolving implicitly.

### Step 4: Fix `esModuleInterop`

Remove any explicit `"esModuleInterop": false`. TypeScript 6.0 enforces `esModuleInterop: true` as the only valid value. Update any import statements that relied on the old behavior (typically `import foo = require('foo')` patterns become `import foo from 'foo'`).

### Step 5: Audit `types` and `target`

- For packages that relied on the old default `types` (all `@types/*` auto-included), add an explicit `"types": [...]` array listing only the types actually used. This prevents phantom type availability.
- Review `target` in each config. If any config omits `target` and relied on an old default, set it explicitly to `"ES2023"` to match the new default. If a package intentionally targets an older ES version, that explicit setting is preserved.

### Step 6: CI enforcement

Add a `tsconfig-lint` CI step (using `tsc --noEmit` plus a small shell grep check) that fails if any `tsconfig.json` in the workspace contains `moduleResolution: classic` or `esModuleInterop: false`. This prevents regressions as new packages are added.

### Why this approach

The incremental fix-per-error approach (upgrade first, then fix failures) is preferred over rewriting configs speculatively. It ensures every change is driven by an actual compiler error, minimizing over-correction. The migration touches only build tooling; the compiled output and Docker images are the end product, so the risk surface is limited to CI and developer workflow.

## Alternatives

### Option A: Stay on TypeScript 5.x indefinitely

Deferred but not dropped. TypeScript 6.0 is already released; remaining on 5.x means accumulating divergence from upstream type definitions (which increasingly target 6.0+), missing build performance improvements, and facing a larger migration when TypeScript 7 eventually drops 5.x compatibility. The cost of migrating grows over time. Rejected.

### Option B: Migrate to TypeScript 6.0.3 and simultaneously adopt `verbatimModuleSyntax` and other new strict options

The additional strict options (`verbatimModuleSyntax`, stricter `noUncheckedIndexedAccess`, etc.) are desirable but orthogonal to the compatibility migration. Bundling them would increase the PR scope and review burden, and would likely surface a larger set of pre-existing type errors that are not related to the 6.0 breaking changes. Rejected for this proposal; the additional strictness options can be adopted incrementally in follow-on PRs.

### Option C: Use a TypeScript version shim / compatibility layer

No production-grade shim exists for TypeScript 6.0 breaking changes. The only viable path is updating the configs. Not applicable.

## Platform impact

### Migrations

- `package.json` root and per-package: `typescript` devDependency updated to `6.0.3`.
- `package-lock.json`: updated to reflect the new TypeScript version; committed.
- All `tsconfig.json` files in the workspace: `moduleResolution` and `esModuleInterop` fields corrected; `types` and `target` reviewed and made explicit where previously relying on defaults.
- New CI step `tsconfig-lint` added to the pipeline.

### Backward compatibility

TypeScript is a build-time-only dependency. The compiled JavaScript output must be verified to be behaviorally identical via the existing integration test suite. No runtime API, HTTP endpoint, Kubernetes manifest, or ArgoCD configuration changes.

### Resource impact (`labs`)

TypeScript is not installed in production Docker images and has no memory footprint in any running tenant. This proposal carries zero memory risk for `labs` or any other tenant.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `moduleResolution: node16` requires explicit file extensions in imports, causing build failures | Medium | Compiler errors surface all affected files; fixes are mechanical and reviewable in the same PR |
| A workspace package had undeclared `@types/*` dependencies that worked via the old default `types` | Medium | The `types` audit in step 5 catches these; failing CI on the feature branch confirms before merge |
| Compiled output differs in subtle ways (e.g., default export interop) | Low | Existing integration test suite catches behavioral regressions |
| Build time improvement is less than the 15% threshold | Low | The threshold is conservative; even if the improvement is smaller, the migration is still required for compatibility |
