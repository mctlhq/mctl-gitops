# Tasks: issue-38-sync-mctl-openclaw-fork-with-upstream-op

- [ ] 1. Confirm prerequisite gate: verify `mctl-openclaw#34` is closed and PR #39 (`88f01335c4`) is merged into `origin/main` — DoD: `gh pr view 39 -R mctlhq/mctl-openclaw --json state,mergedAt` shows `state: MERGED`.

- [ ] 2. Research "miniclaw" (parallel, does not block sync tasks) — DoD: a written evaluation note posted to issue #38 (or a linked follow-up issue) covering: what miniclaw is (or a statement that no credible source was found), maintenance activity, feature parity with mctl-openclaw's used surface, estimated fork patch surface reduction, migration cost, and a recommendation (continue openclaw OR open a migration issue OR defer for N months).

- [ ] 3. Trigger the upstream sync workflow — DoD: `gh workflow run upstream-sync.yml -R mctlhq/mctl-openclaw` succeeds without error and the run appears in the Actions list. Command: `gh run list -R mctlhq/mctl-openclaw --workflow=upstream-sync.yml --limit 3` confirms a new run.

- [ ] 4. Assess workflow outcome — DoD: the run completes with either (a) `changed=false` (upstream already ancestor — not expected given the gap) or (b) a `sync/upstream-<date>` PR open and `@codex review` posted. If the run fails at the merge step due to conflicts, proceed to task 5; otherwise skip to task 6.

- [ ] 5. Manual conflict resolution (only if task 4 produced merge conflicts) (depends on 4) — DoD: a `sync/upstream-<date>` branch exists on `origin`, the merge commit is present, all conflicted files are resolved per the area guidance in `FORK_MAINTENANCE.md`, the "Conflict resolution was needed" checkbox is ticked in the PR body, and every touched area has a one-line resolution note. Specific files to verify post-resolution: `src/gateway/auth.ts`, `src/gateway/server-methods.ts`, `src/gateway/server-methods-list.ts`, `src/agents/auth-profiles/oauth.ts`, `src/openai-codex/connect-flow.ts`, `src/auto-reply/reply/get-reply.ts`, `src/auto-reply/reply/skill-filter.ts`, `src/infra/json-file.ts`, `ui/src/ui/views/chat.test.ts` (expected deletion — accept it).

- [ ] 6. Post `@codex review` if not already present (depends on 4 or 5) — DoD: the PR has a comment containing `<!-- codex-review-trigger -->` and `@codex review`. On the automated happy path the workflow posts this automatically; on the manual conflict path the implementer posts it.

- [ ] 7. Address all Codex findings (depends on 6) — DoD: every Codex inline comment and summary comment is either (a) addressed by a fix-up commit pushed to the sync branch, or (b) dismissed in-thread with a written justification. A second `@codex review` is posted if any fix-up commits were pushed, and the follow-up review is also resolved.

- [ ] 8. Verify CI green (depends on 7) — DoD: the PR's status checks are all green. The relevant checks are those triggered by `.github/workflows/ci.yml` and `.github/workflows/mctl-ci.yml` (if any MCTL overlay files were touched during conflict resolution). The `claude-review.yml` automatic review may also fire; address its findings by the same fix-or-dismiss standard.

- [ ] 9. Merge the sync PR (depends on 7, 8) — DoD: `gh pr merge <N> -R mctlhq/mctl-openclaw --merge --delete-branch` exits 0. The PR is closed as merged and the `sync/upstream-<date>` branch is deleted.

- [ ] 10. Verify release workflow (depends on 9) — DoD: `gh run list -R mctlhq/mctl-openclaw --workflow=upstream-sync-release.yml --limit 3` shows a successful run that reached the "Trigger mctl-gitops image build" step. The run summary shows the created tag (e.g. `v2026.5.2` or with a suffix) and the dispatched image tag.

- [ ] 11. Verify image build in mctl-gitops (depends on 10) — DoD: `gh run list -R mctlhq/mctl-gitops --workflow=build-image.yaml --limit 5` shows a successful `build-image.yaml` run for `ghcr.io/mctlhq/openclaw:<version>` triggered by the sync dispatch.

- [ ] 12. Verify labs-openclaw deployment (depends on 11) — DoD: ArgoCD reports `labs-openclaw` as `Synced Healthy` on the new image tag. Check via `mctl get service status labs-openclaw` or the ArgoCD UI.

- [ ] 13. Run smoke checks (depends on 12) — DoD: all four checks pass: (a) `mctl` connect, `mctl.connect.status`, and token refresh complete without error; (b) Codex connect flow completes; (c) the mctl-agent hook endpoint responds to a test request; (d) one basic chat/session round trip through the Gateway returns a reply.

- [ ] 14. Post completion note on issue #38 (depends on 2, 13) — DoD: a comment on `mctlhq/mctl-openclaw#38` summarizing the sync outcome (PR number, merged commit SHA, image tag, ArgoCD state) and the miniclaw evaluation result (or a link to the evaluation follow-up issue). Close the issue if the miniclaw evaluation concludes "continue with openclaw" or "open a migration issue" (in the latter case, close #38 and link the new issue).

## Tests

- [ ] T1. `src/gateway/server-methods.mctl.test.ts` passes after conflict resolution — verifies that all `mctl.*` gateway methods are still registered and reachable. Run with: `pnpm test src/gateway/server-methods.mctl.test.ts`.
- [ ] T2. `src/agents/auth-profiles/oauth.openai-codex-refresh-fallback.test.ts` passes — verifies serialized refresh-token rotation behavior. Run with: `pnpm test src/agents/auth-profiles/oauth.openai-codex-refresh-fallback.test.ts`.
- [ ] T3. `src/openai-codex/connect-flow.test.ts` and `src/openai-codex/connect-store.test.ts` pass — verifies Codex localhost/manual callback flow. Run with: `pnpm test src/openai-codex/`.
- [ ] T4. `src/auto-reply/reply/skill-filter.test.ts` passes — verifies that incident hook sessions are still scoped to platform skills. Run with: `pnpm test src/auto-reply/reply/skill-filter.test.ts`.
- [ ] T5. `src/infra/json-file.test.ts` passes — verifies atomic-write, symlink-chain walk, and fail-loud behaviors. Run with: `pnpm test src/infra/json-file.test.ts`.
- [ ] T6. `pnpm check:changed` passes in Testbox after conflict resolution commits are staged — confirms no typecheck or broader changed-lane failures were introduced by the merge or resolution commits. Run via Testbox: `blacksmith testbox run --id <ID> "pnpm check:changed"`.

## Rollback

**Do not revert the sync merge commit in `main`.** Upstream merges carry thousands of commits; a revert will corrupt the merge graph and make future syncs much harder.

Instead:

1. In `mctlhq/mctl-gitops`, pin the `labs-openclaw` ArgoCD app image tag back to the last known-good fork tag (the tag that was `Synced Healthy` before this sync). ArgoCD will reconcile and return to healthy on the previous image.
2. Open a hotfix branch off the current `main` (post-merge), fix the regression forward, open a new PR through the normal review process (Claude auto-review + Codex gate), merge it, and let `upstream-sync-release.yml` cut a new tag.
3. Once the hotfix image is verified healthy on `labs-openclaw`, un-pin the ArgoCD image tag.

Do not promote the regressed image to other tenants. If the regression is in `src/gateway/server-methods-list.ts` (missing mctl method exports) or `src/auto-reply/reply/get-reply.ts` (missing skill-filter call) and was not caught by T1 or T4, update those tests to cover the regression before closing the hotfix PR.
