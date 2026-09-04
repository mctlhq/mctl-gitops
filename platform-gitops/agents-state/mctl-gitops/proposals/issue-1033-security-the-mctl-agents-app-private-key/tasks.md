# Tasks: issue-1033-security-the-mctl-agents-app-private-key

- [ ] 1. In `.github/workflows/gitops-bump.yaml`, add
      `permission-contents: write` to the `Generate GitHub App token` step
      (the `create-github-app-token@d72941d797fd3113feb6b93fd0dec494b13a2547`
      step around lines 64-71), alongside the existing `app-id`,
      `private-key`, `owner: mctlhq`, `repositories: mctl-gitops` inputs —
      DoD: `git diff` on this file shows only the added
      `permission-contents: write` line under that step's `with:` block;
      no other input changes; the job's own `permissions: contents: write`
      block (lines 45-46) is untouched.
- [ ] 2. In `.github/workflows/release-deploy.yaml`, add the same
      `permission-contents: write` to the equivalent
      `create-github-app-token` step in the `bump` job (around lines
      120-127) — DoD: same shape as task 1; `git diff` shows only the
      added input line; the job's `permissions: contents: write` block
      (around lines 98-102) is untouched.
- [ ] 3. Write `docs/runbooks/agents-app-secret-exposure.md` — DoD: file
      exists and contains, at minimum:
      - The finding that App-permission narrowing (#761,
        `docs/runbooks/github-app-scope-audit.md`) and per-call-site
        permission scoping (tasks 1-2) both leave the raw
        `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` readable by any workflow
        in any mctlhq repo (visibility `ALL`, set 2026-08-13), and that
        only secret-visibility narrowing or removing the raw key from
        callers (a central-mint reusable workflow) closes that gap.
      - A table of the three in-repo consumers
        (`gitops-bump.yaml`, `release-deploy.yaml`, `release-drift.yml`)
        with file:line citations, what each mints for, and their
        `repositories:`/`permission-*` scoping state after tasks 1-2.
      - A table of the externally-reported consumers from issue #1033
        (`mctl-telegram` release-please + preview-deploy, `mctl-api`
        release-please, `mctl-web` release-please, `mctl-agents`
        release-please), explicitly labeled "unverified from this clone",
        each with the org-wide `gh api`/`gh secret list` verification
        command from design.md's "Proposed solution" section 2.
      - The issue's three remediation options (central-mint reusable
        workflow, per-purpose Apps, secret visibility `selected`) with the
        recommended sequencing from design.md: tasks 1-2 now, visibility
        `selected` next (manual, org-owner, five-minute change per the
        issue), central-mint reusable workflow as a tracked follow-up
        issue in `mctlhq/.github`, per-purpose Apps deferred.
      - A `## Manual follow-up` section (matching
        `github-app-scope-audit.md`'s pattern) listing exactly: (a) run
        this runbook's verification commands and update the "unverified"
        table with real findings; (b) flip `AGENTS_APP_ID`/
        `AGENTS_APP_PRIVATE_KEY` org secret visibility from `ALL` to
        `selected`, seeded with the confirmed consumer repo list; (c)
        smoke-test `gitops-bump`/`release-deploy` and `release-drift`
        after narrowing; (d) file a tracking issue in `mctlhq/.github` for
        the central-mint reusable workflow, explicitly noting
        `release-drift.yml`'s no-`repositories:`, multi-permission,
        cross-repo-read shape as a requirement that design must support.
- [ ] 4. Cross-link the new runbook: add one line to
      `docs/runbooks/github-app-scope-audit.md` (e.g. under "Consumers" or
      a short new section) pointing at
      `docs/runbooks/agents-app-secret-exposure.md`, and one line to
      `CLAUDE.md` (depends on 3, so both link to a file that exists) — DoD:
      both files contain a one-line reference to the new runbook's path.

## Tests

- [ ] T1. After tasks 1-2, `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/gitops-bump.yaml'))"`
      and the equivalent for `release-deploy.yaml` both parse without
      error (confirms no YAML indentation break from the added line).
- [ ] T2. Diff-review both edited files to confirm `repositories:
      mctl-gitops` and the new `permission-contents: write` are the only
      two inputs under each `create-github-app-token` step's `with:`
      block besides `app-id`/`private-key`/`owner` — no `permission-actions`,
      `permission-pull-requests`, `permission-issues`, or
      `permission-workflows` accidentally added or left implicit.
- [ ] T3. After merge, trigger (or wait for) the next real
      `gitops-bump.yaml` or `release-deploy.yaml` run (e.g. via
      `mctl_deploy_service` against any service, which dispatches
      `release-deploy.yaml`) and confirm via
      `mctl_get_workflow_status`/Actions logs that the `Generate GitHub App
      token` step still succeeds and the subsequent `checkout` +
      `git push` to `main` still completes — this is the regression signal
      that `permission-contents: write` alone is sufficient for the bump
      job's actual git operations.
- [ ] T4. After merge, confirm `release-drift.yml`'s next scheduled run
      (cron `17 7 * * *`, or a manual `workflow_dispatch`) still succeeds
      unchanged — it was not edited by this proposal, but its shared App
      is the same one tasks 1-2 touch, so this is a cheap confirmation
      nothing about the App's installed permission ceiling changed
      underneath it.
- [ ] T5. Once the org owner completes the manual follow-up (task 3's
      "Manual follow-up" item b — visibility flipped to `selected`),
      re-run T3 and T4 against the narrowed visibility and confirm both
      still succeed; separately confirm a workflow in a repo deliberately
      left off the `selected` list can no longer read
      `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` (e.g. by checking that
      repo's Actions secrets listing via the GitHub UI, or
      `gh api repos/mctlhq/<repo>/actions/secrets` returning no matching
      entry — org secrets are not enumerable per-repo via that endpoint,
      so the practical check is that a `create-github-app-token` step
      added experimentally to that repo's workflow fails to resolve the
      secret).

## Rollback

- Tasks 1-2 (permission-scoping edits): revert the commit(s). Both edits
  are additive single-line changes to an existing step; reverting restores
  the prior (unscoped-but-functional) behavior with no data or state to
  migrate — the next `gitops-bump`/`release-deploy` run simply mints an
  unscoped-again token as it did before this proposal.
- Tasks 3-4 (runbook + cross-links): revert the commit(s). Documentation
  only, no runtime effect.
- The manual org-secret-visibility follow-up (task 3's "Manual follow-up"
  item b, executed by a human outside this proposal's automation) is
  reversible directly in GitHub's org Actions secrets settings: switch
  visibility back to `All repositories`. If a legitimate consumer missing
  from the `selected` list breaks after narrowing, that UI revert is the
  fastest mitigation — nothing in this repo needs to change to undo the
  GitHub-side visibility setting.
- The recommended `mctlhq/.github` central-mint follow-up is not
  implemented by this proposal, so there is nothing to roll back for it
  here; any rollback for that work belongs to whichever proposal
  eventually implements it in that repo.
