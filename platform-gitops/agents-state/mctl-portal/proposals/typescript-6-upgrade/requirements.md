# Upgrade TypeScript to v6.0.3

## Context
TypeScript 6.0.3 became the stable release on the 6.0 major branch on April 16, 2026. The new major
version introduces stricter type-checking rules — in particular around type narrowing, control-flow
analysis, and module resolution — that surface latent bugs at compile time rather than at runtime.
Keeping the portal on an older TypeScript release means the development team misses these guardrails
and cannot adopt TypeScript 6-only language features such as improved `satisfies` ergonomics and
stricter `exactOptionalPropertyTypes` enforcement.

The mctl-portal is a Backstage monorepo managed through Yarn Berry workspaces (`packages/app`,
`packages/backend`, `plugins/*`). A TypeScript major upgrade must be validated across every workspace
package because each package compiles independently via `backstage-cli`. The upgrade is a non-urgent
developer-experience improvement and is explicitly sequenced after any open security proposals.

## User stories
- AS a portal developer I WANT the codebase to compile under TypeScript 6.0.3 SO THAT newly
  introduced strict checks catch type errors before they reach production.
- AS a portal developer I WANT a single root `tsconfig.json` that targets TypeScript 6 SO THAT all
  workspace packages share consistent compiler options and I do not have to update each package
  individually.
- AS a CI maintainer I WANT the full test suite (unit + e2e) to pass after the upgrade SO THAT I can
  merge the change with confidence.
- AS an on-call engineer I WANT a documented rollback procedure SO THAT I can revert the upgrade
  quickly if a post-merge regression is discovered.

## Acceptance criteria (EARS)

### Compilation
- WHEN a developer runs `yarn tsc --noEmit` at the repository root THE SYSTEM SHALL report zero
  TypeScript errors across `packages/app`, `packages/backend`, and all `plugins/*` packages.
- WHEN `backstage-cli package build` is executed for any workspace package THE SYSTEM SHALL complete
  successfully without TypeScript compilation errors.
- IF the TypeScript compiler version resolved by Yarn is not 6.0.x THEN the CI pipeline SHALL fail
  with an explicit version-check error.

### Strict-mode compliance
- WHEN TypeScript 6 strict-mode flags are enabled in the root `tsconfig.json` THE SYSTEM SHALL
  compile the entire workspace without suppressed `@ts-ignore` comments introduced solely to work
  around the new checks.
- IF a new `@ts-ignore` or `@ts-expect-error` directive is added during the upgrade THE SYSTEM SHALL
  require an accompanying inline comment that explains why the suppression is necessary.

### Backstage-cli compatibility
- WHEN `backstage-cli` is invoked after the TypeScript upgrade THE SYSTEM SHALL operate without
  version-incompatibility warnings or runtime failures.
- IF `backstage-cli` does not yet declare support for TypeScript 6 THEN the upgrade SHALL be blocked
  until a compatible `backstage-cli` version is confirmed and pinned.

### CI / test suite
- WHEN the CI pipeline executes on the upgrade branch THE SYSTEM SHALL pass all unit tests and
  Playwright e2e tests without modification to test logic.
- WHILE the upgrade pull request is open THE SYSTEM SHALL enforce branch protection so that no merge
  is possible unless the full CI pipeline is green.

### Sequencing
- IF any security proposal is still open and unmerged THEN this proposal SHALL NOT be merged ahead
  of it.

## Out of scope
- Adopting TypeScript 6-exclusive language features beyond what is required to fix compilation
  errors (new feature usage can follow in separate proposals).
- Upgrading `backstage-cli` itself or any Backstage plugin versions as part of this change.
- Changes to the Playwright test scenarios or Prettier configuration.
- Any work in tenants other than `admins`.
- Memory or CPU tuning of the portal pod (no runtime behaviour changes are expected).
