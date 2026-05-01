# Tasks: typescript-6-upgrade

> Sequencing note: this proposal is non-urgent. Do not start task 1 until all open security
> proposals have been merged.

- [ ] 1. Audit TypeScript 6.0 breaking changes against the portal codebase — DoD: a written list
  (can be a PR description or internal comment) enumerates every breaking change from the TS 6.0
  release notes that is relevant to code patterns used in `packages/app`, `packages/backend`, and
  `plugins/*`; patterns with zero occurrences in the repo are explicitly noted as "not applicable".

- [ ] 2. Confirm `backstage-cli` compatibility with TypeScript 6 (depends on 1) — DoD: the version
  of `backstage-cli` currently pinned in `package.json` is verified (via its peer-dependency
  declaration or community issue tracker) to support TypeScript 6.0.x; if it does not, the minimum
  compatible `backstage-cli` version is identified and a separate pin PR is raised and merged before
  proceeding.

- [ ] 3. Update root `package.json` and Yarn resolution (depends on 2) — DoD: `typescript` dev-
  dependency is set to `^6.0.3`; a `resolutions` entry in `package.json` (or equivalent in
  `.yarnrc.yml`) pins the TypeScript version workspace-wide; `yarn install` completes without
  errors; `node -e "console.log(require('typescript').version)"` at repo root prints `6.0.x`.

- [ ] 4. Update root `tsconfig.json` compiler options (depends on 3) — DoD: root `tsconfig.json`
  uses TypeScript 6-aligned `target`, `module`, and `moduleResolution` values consistent with
  `backstage-cli`'s expected configuration; `"strict": true` remains enabled; changes are documented
  with inline comments explaining each option choice.

- [ ] 5. Fix compilation errors in `packages/app` (depends on 4) — DoD: `yarn tsc --noEmit` scoped
  to `packages/app` exits with code 0; no new `@ts-ignore` or `@ts-expect-error` directives are
  introduced without an explanatory comment; all fixes are reviewable in the PR diff.

- [ ] 6. Fix compilation errors in `packages/backend` (depends on 4) — DoD: same criteria as task
  5, applied to `packages/backend`.

- [ ] 7. Fix compilation errors in `plugins/*` (depends on 4) — DoD: `yarn tsc --noEmit` run
  across all plugin packages exits with code 0; same `@ts-ignore` policy as tasks 5 and 6.

- [ ] 8. Add CI version-assertion step (depends on 5, 6, 7) — DoD: the CI pipeline includes a step
  that runs `node -e "const v=require('typescript').version; if(!v.startsWith('6.0'))process.exit(1)"`
  (or equivalent); the step is positioned before the build step so a version regression fails fast.

- [ ] 9. Full CI pipeline validation (depends on 8) — DoD: the upgrade branch CI run is fully green:
  `yarn tsc --noEmit` passes, `backstage-cli package build` passes for all packages, all unit tests
  pass, Playwright e2e suite passes, and the version-assertion step passes.

- [ ] 10. Peer review and merge (depends on 9) — DoD: at least one peer review approval is recorded;
  the PR description links to the breaking-change audit from task 1; the branch is merged into main
  via the standard mctl-gitops process; ArgoCD syncs successfully in tenant `admins`.

## Tests

- [ ] T1. TypeScript version assertion — `node -e "require('typescript').version"` returns `6.0.x`
  in CI after `yarn install`. Covers task 3.

- [ ] T2. Root type-check — `yarn tsc --noEmit` at repo root exits 0. Covers tasks 4-7.

- [ ] T3. Per-package build — `yarn workspaces foreach -A run build` (or equivalent Backstage build
  command) completes without error for every workspace. Covers tasks 5-7.

- [ ] T4. Unit test suite — `yarn test` (or `yarn workspaces foreach -A run test`) exits 0. Confirms
  no runtime behaviour was broken by type-only changes.

- [ ] T5. Playwright e2e — full Playwright suite runs against a locally-started or staging portal
  instance and all scenarios pass. Covers end-to-end portal functionality post-upgrade.

- [ ] T6. No rogue suppressions — `grep -rn "@ts-ignore\|@ts-expect-error" packages/ plugins/`
  output is reviewed; every occurrence added during this upgrade has an explanatory comment on the
  preceding line.

- [ ] T7. ArgoCD sync health — after merge, ArgoCD reports the `mctl-portal` application in tenant
  `admins` as `Synced` and `Healthy` within the standard rollout window.

## Rollback
If a regression is discovered after merge:

1. Revert the merge commit on `main` (or the mctl-gitops GitOps repo) using
   `git revert <merge-sha>` and push. ArgoCD will detect the revert and redeploy the previous image
   automatically.
2. If the regression is in a deployed image rather than source, roll back the ArgoCD application to
   the previous revision via `argocd app rollback mctl-portal` (requires `admins` cluster access).
3. Re-pin `typescript` in `package.json` to the pre-upgrade version and restore the original
   `tsconfig.json` if the revert is not sufficient (e.g., the upgrade branch was squash-merged).
4. Open a follow-up issue documenting the failure mode before re-attempting the upgrade, with
   specific attention to the `backstage-cli` compatibility matrix.

No database migrations, secrets rotations, or infrastructure changes are involved, so rollback is
limited to a code revert and an ArgoCD sync.
