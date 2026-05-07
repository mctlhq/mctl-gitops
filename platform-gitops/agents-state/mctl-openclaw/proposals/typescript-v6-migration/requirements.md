# Migrate build toolchain to TypeScript 6.0.3

## Context

mctl-openclaw is a Node.js + TypeScript workspace. TypeScript 6.0.3 introduces several breaking changes that affect projects carrying legacy compiler settings: `moduleResolution: classic` is removed, `esModuleInterop: false` is forbidden, the default `target` changes to ES2023, and the default `types` is changed to an empty array. Many projects — including this one — were set up with these legacy settings and have not yet been updated. As TypeScript v7 (the upcoming Go-based rewrite of the compiler) approaches, the cost of migrating later will increase: more code may need to change, and tooling compatibility windows will narrow.

Migrating now eliminates the growing tech debt and delivers a 20–50% build time improvement that benefits all three tenants' CI pipelines. There is no runtime impact: TypeScript is a build-time tool only. The compiled JavaScript output and the deployed Docker images are unaffected by the compiler version itself, and no new memory is consumed by the running service.

## User stories

- AS a developer I WANT the mctl-openclaw workspace to compile cleanly under TypeScript 6.0.3 SO THAT I can use current TypeScript features without fighting legacy compiler warnings or errors.
- AS a CI engineer I WANT the build to be 20–50% faster SO THAT pull-request feedback loops are shorter and CI minutes are reduced.
- AS a platform engineer I WANT the TypeScript migration completed before TypeScript v7 is released SO THAT we are not forced into a rushed migration under tighter tooling constraints.

## Acceptance criteria (EARS)

- WHEN `tsc --version` is run in the workspace, THE SYSTEM SHALL report version `6.0.3`.
- WHEN the full workspace build (`tsc -b`) is run against the updated `tsconfig` files, THE SYSTEM SHALL complete with zero errors and zero warnings related to removed or forbidden compiler options.
- WHEN a CI pipeline runs, THE SYSTEM SHALL execute `tsc -b --noEmit` as a required type-check step and fail if any type error is reported.
- WHILE the upgraded compiler is in use, THE SYSTEM SHALL NOT have any `tsconfig.json` in the workspace that specifies `moduleResolution: classic` or `esModuleInterop: false`.
- IF a new `tsconfig.json` is added to the workspace, THEN THE SYSTEM SHALL enforce via CI lint that it does not re-introduce `moduleResolution: classic` or `esModuleInterop: false`.
- WHEN the migration is complete, THE SYSTEM SHALL produce Docker images byte-for-byte equivalent in observable runtime behavior to the pre-migration images (verified by the existing integration test suite).
- WHEN CI build time is measured on the migrated workspace, THE SYSTEM SHALL show a build time improvement of at least 15% compared to the TypeScript 5.x baseline (measured over three consecutive runs).

## Out of scope

- Migrating to TypeScript 7 (Go-based compiler); that is a separate, future initiative.
- Changing the Node.js runtime version (covered by the separate `nodejs-runtime-upgrade` proposal).
- Adding new TypeScript strict-mode options beyond those required for compatibility with 6.0.3.
- Changes to the deployed Docker image content, Kubernetes manifests, or ArgoCD configuration.
- Any change to production behavior of the running service.
