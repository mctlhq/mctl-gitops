# Design: issue-38-sync-mctl-openclaw-fork-with-upstream-op

## Current state

### Fork relationship

`mctlhq/mctl-openclaw` is a merge-based downstream of `openclaw/openclaw`. The merge base (as of the clone used for this investigation) is the parent of `88f01335c4` (PR #39, `fix(gateway,agents,plugins): close remaining plugin-metadata-snapshot cache-miss paths`), which is the only commit on `origin/main` not yet present in `upstream/main`. Upstream carries approximately 18,302 commits (per the issue, filed 2026-07-11) that have not been merged into the fork; the gap continues to grow as upstream ships.

### Sync mechanism

The sync pipeline is fully in place and documented in `FORK_MAINTENANCE.md`.

**`.github/workflows/upstream-sync.yml`**
- Schedule: weekly on Mondays at 07:00 UTC (`cron: "0 7 * * 1"`).
- Manual trigger: `gh workflow run upstream-sync.yml -R mctlhq/mctl-openclaw`.
- Steps: fetch both remotes, create/reset `sync/upstream-YYYY-MM-DD` off `origin/main`, run `git merge --no-ff --no-edit upstream/main` under `set -euo pipefail`, push, create or update the PR using `.github/upstream_sync_pr_template.md`, post exactly one `@codex review` comment (deduplicated by `<!-- codex-review-trigger -->`).
- Conflict guard: if `git merge` exits non-zero the workflow fails immediately; no branch is pushed and no PR is created.
- Early-exit guard: if `upstream/main` is already an ancestor of the fork's `HEAD`, `changed=false` is set and the workflow exits without creating a PR.

**`.github/workflows/upstream-sync-release.yml`**
- Trigger: `pull_request` type `closed` on `main`, gated on `merged == true` and `head.ref` starting with `sync/upstream-`.
- Steps: read `package.json` version (must match `YYYY.M.D[-beta.N]`), create an annotated tag `v<version>` (with numeric suffix if the tag already exists), push the tag, dispatch `build-image.yaml` in `mctlhq/mctl-gitops` with `image_name=ghcr.io/mctlhq/openclaw`, `image_tag=<version>`, `git_ref=<tag>`, `team_name=labs`, `component_name=openclaw`.
- App-token strategy: primary app ID `2729701` with `GH_APP_PRIVATE_KEY`; fallback app ID `2971289` with `GH_APP_PRIVATE_KEY_FALLBACK`. Both target `mctlhq/mctl-gitops`.

**`.github/workflows/claude-review.yml`**
- Auto-reviews every non-draft, same-repo PR and `@claude review` comment from maintainers.
- The sync PR will receive an automatic review from this workflow in addition to the `@codex review` gate.

### Fork-specific patch surface

`FORK_MAINTENANCE.md` documents all files that diverge from upstream. The high-risk areas (most likely to conflict) are:

- `src/gateway/auth.ts`, `src/gateway/method-scopes.ts`, `src/gateway/server-methods.ts`, `src/gateway/server-methods-list.ts`, `src/gateway/server.auth.control-ui.suite.ts`, `src/gateway/server/ws-connection/message-handler.ts` — gateway integration with trusted-proxy and mctl method registration.
- `src/agents/auth-profiles/oauth.ts`, `src/agents/auth-profiles/store.ts` — serialized refresh-token rotation.
- `src/openai-codex/connect-flow.ts`, `src/openai-codex/connect-store.ts` — Codex localhost/manual callback flow.
- `src/auto-reply/reply/get-reply.ts`, `src/auto-reply/reply/skill-filter.ts` — incident hook session scoping to platform skills.
- `src/infra/json-file.ts` — atomic-write layer with symlink-chain walk; `FORK_MAINTENANCE.md` explicitly notes that if upstream has introduced its own atomic write, the fork behavior must be re-applied on top.
- `ui/src/ui/views/chat.test.ts` — upstream has **deleted** this file. The next merge will produce a "modify/delete" conflict; the resolution is to accept the deletion unless mctl-specific assertions here cover behavior not ported elsewhere.
- `ui/src/ui/controllers/codex-connect.ts`, `ui/src/ui/controllers/mctl-connect.ts` — fork-only controllers.

Fork-only files (no upstream analogue, therefore no conflict risk):
- `.github/workflows/mctl-ci.yml`, `.github/workflows/upstream-sync.yml`, `.github/workflows/upstream-sync-release.yml`, `.github/upstream_sync_pr_template.md`
- `src/mctl-identity/*`, `src/mctl-skills/mctl-platform/SKILL.md`
- `src/mctl/oauth-store.ts`
- `src/gateway/server-methods/mctl.ts`, `src/gateway/server-methods/codex.ts`, `src/gateway/server-methods.mctl.test.ts`
- `FORK_MAINTENANCE.md`

### Why the sync lapsed

The workflow runs weekly and is automatic on the happy path (no conflicts). The fact that it has not run implies either: (a) the workflow was not triggered because conflicts caused it to fail silently on a prior attempt, (b) the workflow was paused or the cron runner was unavailable, or (c) deliberate deferral pending resolution of `mctl-openclaw#34`. The issue author attributed the lapse to the follow-up ordering constraint (after #34), and PR #39 is the resolution of #34.

### "miniclaw" evaluation context

There are zero references to "miniclaw" in the `mctlhq/mctl-openclaw` codebase, its CI, its documentation, or its FORK_MAINTENANCE guide. The concept was mentioned in passing in the issue body by the author but not substantiated. No architecture, repository URL, or capability comparison exists in this repo. The evaluation is a research task, not a code task.

## Proposed solution

### Phase 1: prerequisite gate check

Before triggering the sync, confirm `mctl-openclaw#34` is closed. PR #39 (`88f01335c4`) is merged into `main` as of 2026-07-11, so this gate is already satisfied. No additional work is needed.

### Phase 2: attempt automated sync

Trigger the existing workflow:

```bash
gh workflow run upstream-sync.yml -R mctlhq/mctl-openclaw
```

Monitor the run. If the merge succeeds (no conflicts), the workflow will:
1. Push `sync/upstream-<date>` to `origin`.
2. Open a PR against `main` using `.github/upstream_sync_pr_template.md`.
3. Post `@codex review` to the PR.

Given the large commit gap, conflicts in the high-risk files listed above are probable. The workflow will fail at the merge step and exit without creating a branch or PR. If that happens, proceed to Phase 3.

### Phase 3: manual conflict resolution (if needed)

Follow the manual recovery procedure in `FORK_MAINTENANCE.md`:

```bash
git fetch origin main --prune --tags
git fetch upstream main --prune --tags

branch="sync/upstream-$(date -u +%Y-%m-%d)"
git checkout -B "$branch" origin/main
git merge --no-ff --no-edit upstream/main   # leaves conflict markers on failure

# Resolve each conflicted file, guided by the areas listed in FORK_MAINTENANCE.md.
# For each area:
#   - Accept upstream changes where the fork has no functional delta.
#   - Re-apply fork-specific behavior (e.g., mctl method registration,
#     trusted-proxy assumptions, skill-filter call) on top.
#   - For the chat.test.ts modify/delete conflict: accept deletion unless
#     mctl-specific assertions are present and not ported elsewhere.
#   - For json-file.ts: check whether upstream introduced its own atomic write;
#     if so, take upstream and re-layer mctl-only behaviors (symlink-chain walk,
#     fail-loud on unmounted targets).

git add -u
git commit --no-edit                         # finalize the merge commit

git push -u origin "$branch"
```

Open the PR with the standard title format and tick "Conflict resolution was needed" in the PR body checklist. Document every touched area with a one-line resolution note. Post `@codex review` manually.

### Phase 4: Codex and Claude review gate

Address all Codex findings (fix-up commits or in-thread dismissals with justification). Re-request review with `@codex review` after each push. Claude will auto-review via `.github/workflows/claude-review.yml`. Merge only when CI is green and all findings are resolved.

Merge command (merge commit, not squash):

```bash
gh pr merge <N> -R mctlhq/mctl-openclaw --merge --delete-branch
```

### Phase 5: release and smoke check

After the PR merges, `.github/workflows/upstream-sync-release.yml` fires automatically. Verify:
1. The `upstream-sync-release` job ran to completion without errors.
2. `build-image.yaml` in `mctlhq/mctl-gitops` started and produced `ghcr.io/mctlhq/openclaw:<version>`.
3. `labs-openclaw` ArgoCD app is `Synced Healthy` on the new tag.
4. Smoke checks: `mctl` connect/status/refresh, Codex connect, hook endpoint reachability, one basic chat/session round trip.

Do not promote to other tenants until `labs-openclaw` is healthy.

### Phase 6: miniclaw evaluation

Research "miniclaw" independently of the sync work:
- Search the openclaw/openclaw issue tracker, discussions, and any public references for "miniclaw" as a concept, fork, or project name.
- If a concrete project is found, compare it against openclaw on: maintenance activity, feature parity with the features mctl-openclaw uses, fork patch surface required, migration cost, and license.
- Document findings in a short evaluation note (can be a GitHub comment on issue #38 or a follow-up issue). If no credible source is found, state that explicitly and recommend staying on openclaw.
- This evaluation does not block or gate the sync itself.

## Alternatives

### Alternative 1: skip the sync and wait for miniclaw clarity first

Rationale: if miniclaw turns out to be a substantially lighter base that eliminates the fork patch surface, absorbing 18,000+ commits into the current fork might be wasted effort.

Reason dropped: the issue explicitly states not to assume either way without research, and the research is a lightweight task that runs in parallel. Meanwhile, the production `labs-openclaw` deployment continues to run on a stale image. Delaying the sync increases security and bug exposure. The rollback procedure (pin ArgoCD to the last known-good tag) is well-defined and low-risk if the sync introduces a regression.

### Alternative 2: rebase the fork rather than merging

Rationale: a rebase would produce a cleaner linear history and make the fork diff against upstream more legible.

Reason dropped: `FORK_MAINTENANCE.md` explicitly mandates `git merge --no-ff` (merge commits only). This is not a stylistic choice — it preserves fork branch history visibility in the graph and is required by the existing workflow and PR merge command. Rebasing would diverge from the documented process and break the merge-base logic used by `upstream-sync.yml`'s early-exit guard.

### Alternative 3: run the sync workflow on a scheduled cadence and let it catch up incrementally

Rationale: rather than doing a large catch-up merge, let the weekly Monday cron accumulate smaller merges over time.

Reason dropped: the weekly cron fires only when there is no conflict — it fails silently on the first conflicted merge and stops. Given the size of the gap, there are almost certainly conflicts already waiting. The weekly cron will keep failing until a human performs manual recovery. This alternative does not actually solve the problem; it just defers the manual resolution work indefinitely.

## Platform impact

### Migrations

No database migrations, config schema changes, or client protocol changes are introduced by this proposal itself. Any upstream migrations pulled in by the sync merge are upstream's responsibility; the implementer must check `CHANGELOG.md` and migration notes in the merged commits for anything that requires gitops config updates (environment variables, health paths, ingress changes).

### Backward compatibility

The fork's MCTL-specific behavior (OAuth, trusted-proxy, Codex connect, skill filter) must be preserved verbatim through conflict resolution. Regressions in `src/gateway/server-methods-list.ts` (missing `mctl.*` method exports) or `src/auto-reply/reply/get-reply.ts` (missing skill-filter call) will silently break production webhook and auto-reply behavior without a test failure. The smoke checks in Phase 5 are the runtime verification layer for these.

### Resource impact

The sync produces a new Docker image (`ghcr.io/mctlhq/openclaw:<version>`) via `mctl-gitops` `build-image.yaml`. Build time and image size are upstream's responsibility; no changes to `Dockerfile` or `Dockerfile.whisper-cache-builder` are anticipated unless upstream modifies their equivalents.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Merge conflicts in gateway/auth/OAuth files regress MCTL-specific behavior | Follow the conflict-area checklist in `FORK_MAINTENANCE.md`; run `src/gateway/server-methods.mctl.test.ts` and the OAuth/Codex test suite before opening the PR |
| `ui/src/ui/views/chat.test.ts` modify/delete conflict causes test suite to fail | Accept the deletion; verify any mctl-specific assertions have been ported to upstream test files |
| `upstream-sync-release.yml` dispatch to `mctl-gitops` fails silently (fire-and-forget) | Manually verify in `mctl-gitops` Actions that `build-image.yaml` started; `FORK_MAINTENANCE.md` already documents this as a required manual step |
| ArgoCD does not self-heal on the new tag within expected SLA | Pin `labs-openclaw` back to last known-good tag (do not revert the merge commit); open a hotfix branch |
| "miniclaw" turns out to require significant migration work | The evaluation is research-only; no migration is in scope here; open a new issue if migration is warranted |
