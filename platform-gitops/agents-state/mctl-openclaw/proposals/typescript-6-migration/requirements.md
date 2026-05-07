# Migrate workspace to TypeScript 6.0 ahead of breaking compiler defaults

## Context

The mctl-openclaw workspace is a Node.js + TypeScript monorepo. TypeScript 6.0.3 was released as stable on 2026-04-16 and introduces several breaking default changes: `strict` is now on by default, `module` defaults to `esnext`, `target` defaults to `es2025`, `types` defaults to `[]`, and `--moduleResolution node` is deprecated and will be removed in a future release. The workspace packages were originally authored against TypeScript 5.x defaults; without an explicit opt-in or opt-out for each changed default, upgrading to TypeScript 6.0 will produce unexpected type errors and build failures.

Without a controlled migration, developers who update their local toolchains to TypeScript 6.0 — or when CI tooling auto-upgrades — will encounter surprise build failures across `extensions/*` and core workspace packages. Running the migration now, while the team has planned capacity, avoids a reactive scramble. This is a pure build-time change: TypeScript is not part of the deployed Docker image, there is no runtime or memory impact, and the change is safe for `labs`.

Note: a prior proposal `typescript-v6-migration` (in `proposals/typescript-v6-migration/`) covers substantially the same topic. This proposal (`typescript-6-migration`) was created from the analyst's 2026-05-07 Top-3 and should be reviewed against the earlier proposal to determine whether one should be closed.

## User stories

- AS a developer I WANT all workspace `tsconfig.json` files to be explicit about every TypeScript 6.0 default change SO THAT upgrading TypeScript does not cause unexpected build failures.
- AS a CI engineer I WANT the build to pass cleanly under TypeScript 6.0.3 SO THAT pull-request checks are reliable regardless of the developer's local toolchain version.
- AS a platform engineer I WANT the migration completed before TypeScript v7 (Go-native compiler) is released SO THAT future compiler upgrades face a clean, explicit baseline.

## Acceptance criteria (EARS)

- WHEN `tsc --version` is run in the workspace, THE SYSTEM SHALL report version `6.0.3` or later.
- WHEN the full workspace build (`tsc -b`) is run with TypeScript 6.0.3, THE SYSTEM SHALL complete with zero errors and zero warnings related to changed or deprecated compiler options.
- WHILE TypeScript 6.0.3 is in use, THE SYSTEM SHALL NOT have any `tsconfig.json` in the workspace that omits an explicit value for `strict`, `module`, `target`, or `types` where the 6.0 default differs from the 5.x default.
- WHILE TypeScript 6.0.3 is in use, THE SYSTEM SHALL NOT have any `tsconfig.json` that specifies `--moduleResolution node` (deprecated in 6.0).
- WHEN a new `tsconfig.json` is added to the workspace, THE SYSTEM SHALL fail the CI lint step if it omits explicit values for the four defaulted options or uses `--moduleResolution node`.
- WHEN the migration is complete, THE SYSTEM SHALL produce Docker images whose runtime behaviour is identical to the pre-migration images, verified by the existing integration test suite.
- IF any type error is introduced during the migration that cannot be resolved without a semantic code change, THEN THE SYSTEM SHALL track that error as a separate task with a documented fix rather than suppressing it with `@ts-ignore`.

## Out of scope

- Migrating to TypeScript 7 (the upcoming Go-native compiler rewrite); that is a separate future initiative.
- Changing the Node.js runtime version or Docker base image — covered by `nodejs-security-patch`.
- Upgrading the openclaw application version — covered by `openclaw-cve-upgrade`.
- Adding new strict-mode options beyond those required for TypeScript 6.0 compatibility.
- Any changes to deployed Kubernetes manifests, ArgoCD configuration, or runtime behaviour.
- Resolving pre-existing type errors that were already suppressed under TypeScript 5.x (tracked separately).
