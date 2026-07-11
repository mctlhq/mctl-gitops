# Sync mctl-openclaw fork with upstream openclaw/openclaw

## Context

`mctlhq/mctl-openclaw` is a merge-based downstream fork of `openclaw/openclaw`. The repository carries a thin set of MCTL-specific patches (OAuth, gateway methods, Codex connect, skill filter, identity overlay, and deployment wiring) on top of the upstream codebase. The fork is normally kept current by a weekly automated workflow (`.github/workflows/upstream-sync.yml`) that creates a `sync/upstream-YYYY-MM-DD` branch, opens a PR, triggers a Codex review gate, and — once merged — dispatches an image build via `.github/workflows/upstream-sync-release.yml`.

As of 2026-07-11 the workflow had not been run in an extended period, leaving the fork 18,302+ upstream commits behind (the gap has since grown further as upstream continues to ship). The issue also asks for a one-time evaluation of "miniclaw" as a potential alternative base before deciding whether to continue the openclaw sync at all. The follow-up note in the issue specifies that this work is gated on `mctl-openclaw#34` (event-loop stall) being fully closed; PR #39, which merged on 2026-07-11, is the fix for that issue.

## User stories

- AS a platform operator I WANT the mctl-openclaw image to track a recent upstream openclaw release SO THAT tenants receive upstream bug fixes, security patches, and new features without long gaps.
- AS a maintainer I WANT the sync to pass through the existing Codex review gate SO THAT fork-specific patches are not silently regressed by upstream changes.
- AS a maintainer I WANT a documented evaluation of "miniclaw" SO THAT the team can make an informed, evidence-backed decision on whether to switch the fork base before investing further in the openclaw sync.
- AS a platform operator I WANT a new versioned image tag pushed to `ghcr.io/mctlhq/openclaw` and deployed to `labs-openclaw` after the sync merges SO THAT the gitops stack reflects the updated codebase.

## Acceptance criteria (EARS)

- WHEN the upstream sync workflow is triggered (manually or on schedule) AND upstream/main contains commits not yet in origin/main THE SYSTEM SHALL create or update a `sync/upstream-YYYY-MM-DD` branch and open a PR titled `chore(sync): merge upstream/main into main (sync/upstream-YYYY-MM-DD)`.
- WHEN the sync PR is created or updated THE SYSTEM SHALL post exactly one `@codex review` comment (deduplicated by the `<!-- codex-review-trigger -->` marker) to trigger the Codex review gate.
- WHEN manual conflict resolution is required THE SYSTEM SHALL have all touched areas documented in the PR body conflict checklist (per `.github/upstream_sync_pr_template.md`) before the PR is considered reviewable.
- WHEN a sync PR is merged into main THE SYSTEM SHALL create an annotated tag matching `v<package.json version>` (with numeric suffix if the tag already exists) and dispatch `build-image.yaml` in `mctlhq/mctl-gitops`.
- WHILE the sync PR is open EVERY Codex finding SHALL be either fixed in a follow-up commit to the sync branch or dismissed with a written justification before the PR is merged.
- WHEN the `labs-openclaw` ArgoCD app reports `Synced Healthy` on the new image tag THE SYSTEM SHALL have passed the four smoke checks: `mctl` connect/status/refresh, Codex connect, hook endpoint reachability, and one basic chat/session round trip.
- IF the upstream sync workflow encounters a merge conflict THEN THE SYSTEM SHALL fail the workflow without pushing a branch or creating a PR, requiring manual recovery per the procedure in `FORK_MAINTENANCE.md`.
- IF the "miniclaw" evaluation concludes that switching base is preferable THEN THE SYSTEM SHALL document the migration path as a separate issue before any action is taken; no migration work is in scope for this proposal.
- WHILE the evaluation of miniclaw is pending THE SYSTEM SHALL continue using openclaw as the fork base; no freeze on upstream syncs is implied.

## Out of scope

- Migrating the fork base from openclaw to any other project (miniclaw or otherwise); this proposal covers at most an evaluation recommendation.
- Upstreaming any fork-specific patch to `openclaw/openclaw`; patches may be noted in the sync PR but are not actioned here.
- Changes to the weekly sync cron schedule or the sync workflow logic itself.
- Promotion of the synced image beyond `labs-openclaw` to other tenants; that is a separate release gate.
- Any changes related to `mctl-openclaw#34` (event-loop stall); that issue must be closed before this work starts.

## Open questions

1. **What is "miniclaw"?** The issue author says it was "mentioned in passing" and is not yet researched. It is not referenced anywhere in the `mctlhq/mctl-openclaw` codebase, its documentation, or its CI workflows. It is unknown whether miniclaw is a public project, an internal prototype, a planned fork reduction, or simply a nickname for a proposed lighter-weight configuration of openclaw. The implementer must research what miniclaw actually is before the evaluation can be written. If no credible source can be found, the evaluation should say so explicitly and recommend staying on openclaw by default.
2. **Conflict surface size.** Given the large commit gap, the sync merge may produce conflicts in the high-risk files documented in `FORK_MAINTENANCE.md` (especially `src/gateway/auth.ts`, `src/gateway/server-methods.ts`, `src/agents/auth-profiles/oauth.ts`, and `ui/src/ui/views/chat.test.ts`, which upstream has already deleted). The actual conflict count and severity are unknown until the merge is attempted. The implementer should run the workflow first; if it exits with conflicts, scope a separate recovery session.
3. **Version bump required?** The fork is at `2026.5.2` (from `package.json`). After absorbing thousands of upstream commits the package version in the merged tree will be whatever upstream currently carries. If upstream's version is newer, the `upstream-sync-release.yml` tag resolution will still work (it reads `package.json` from the merged commit). If upstream's version has already been tagged in this fork, the suffix logic (`-1`, `-2`) kicks in. No version change is needed by the implementer, but the reviewer should sanity-check the tag output.
