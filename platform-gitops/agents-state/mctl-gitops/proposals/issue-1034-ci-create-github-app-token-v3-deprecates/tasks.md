# Tasks: issue-1034-ci-create-github-app-token-v3-deprecates

- [ ] 1. (Manual, outside this repo/PR) Create org/repo secrets
      `APP_CLIENT_ID` and `AGENTS_APP_CLIENT_ID` in the mctlhq GitHub
      settings, holding the client ID of the MCTL App and the mctl-agents
      App respectively (visible on each App's settings page, not secret
      material, but kept alongside `APP_PRIVATE_KEY`/`AGENTS_APP_PRIVATE_KEY`
      per this repo's existing pairing convention) — DoD: both secrets
      exist and are readable by the workflows in this repo (same
      scope — repo or org — as the existing `APP_ID`/`AGENTS_APP_ID`).
      This must land before task 5 is merged.

- [ ] 2. Fix `release-drift.yml` — DoD: line 47's `app-id: ${{
      secrets.AGENTS_APP_ID }}` becomes `client-id: ${{
      secrets.AGENTS_APP_CLIENT_ID }}`; no other lines change; a run of
      `release-drift.yml` after merge shows no `app-id` deprecation
      warning in the "Generate read token" step's log.

- [ ] 3. Look up the current `actions/create-github-app-token` v3.x.x tag
      SHA (`gh api repos/actions/create-github-app-token/tags` or
      `git ls-remote --tags`) and record the `sha # vX.Y.Z` pair to reuse
      across tasks 4a/4b — DoD: SHA independently confirmed against the
      GitHub API response, not copied from memory or an old PR.

- [ ] 4a. Fix `gitops-bump.yaml` and `release-deploy.yaml` (depends on 3) —
      DoD: both files' `uses: actions/create-github-app-token@<old v1 sha> # v1`
      become `uses: actions/create-github-app-token@<v3 sha> # v3.x.x`, and
      `app-id: ${{ secrets.AGENTS_APP_ID }}` becomes `client-id: ${{
      secrets.AGENTS_APP_CLIENT_ID }}` in both. `private-key` line
      untouched (already satisfies v3's `required: true`).

- [ ] 4b. Fix `build-image.yaml` (depends on 3) — DoD:
      - the action pin bumped the same way as 4a
      - `app-id: ${{ secrets.APP_ID }}` becomes `client-id: ${{
        secrets.APP_CLIENT_ID }}`
      - `on: workflow_call: secrets:` gains `APP_CLIENT_ID: { required:
        false }` alongside the existing `APP_ID` entry
      - the comment above that `secrets:` block ("These four are every
        inheritable secret build-image references...") is updated to
        say five and lists `APP_CLIENT_ID`

- [ ] 5. Update `release-deploy.yaml`'s call to `build-image.yaml`
      (depends on 4b) — DoD: the `secrets:` block at
      `release-deploy.yaml:92-93` gains `APP_CLIENT_ID: ${{
      secrets.APP_CLIENT_ID }}` next to the existing `APP_ID` passthrough.

- [ ] 6. Open one PR on a feature branch containing tasks 2, 4a, 4b, 5 (not
      pushed directly to main — this touches workflow step definitions, not
      the `image.tag`-only class of change this repo's CLAUDE.md exempts
      from review) — DoD: PR passes `claude-review.yml` and
      `validate-manifests.yml`, and is merged only after task 1's secrets
      are confirmed present.

## Tests

- [ ] T1. After merging, trigger or wait for the next `release-drift.yml`
      run and inspect its "Generate read token" step log — confirm the
      `##[warning]Input 'app-id' has been deprecated` line is gone and a
      token is still produced (job proceeds past that step).
- [ ] T2. After merging, trigger `gitops-bump.yaml` (or wait for the next
      image build it fires on) and confirm the "Generate GitHub App token"
      step succeeds and the subsequent `checkout` + push-to-main step
      completes — proves the App is still correctly identified via
      `client-id` post-pin-bump.
- [ ] T3. Same as T2 for `release-deploy.yaml`'s own token step.
- [ ] T4. Trigger a `build-image.yaml` run (directly or via
      `release-deploy.yaml`) covering the `has_pat != 'true'` branch so the
      App-token tier actually executes, and confirm it still succeeds with
      `client-id`; separately confirm the reusable-workflow secret
      passthrough by checking the step actually receives a non-empty
      client ID (e.g. via the App-token step's own success/failure, since
      the value itself must never be logged).
- [ ] T5. `helm lint` / manifest validation is not applicable here (no Helm
      chart touched); rely on `validate-manifests.yml` / YAML lint
      (`yamllint.yml`) catching any structural YAML error in the diff.

## Rollback

- Each of the four files can be reverted independently (`git revert` of
  the single commit touching that file, or a follow-up PR restoring
  `app-id: ${{ secrets.APP_ID }}` / `AGENTS_APP_ID }}` and the prior pin)
  without affecting the other three — `app-id` continues to work in v3, so
  reverting is not time-pressured.
- If task 1's secrets are missing or misnamed when a fixed workflow runs,
  the affected step fails outright (unlike today's warn-but-succeed):
  - `release-drift.yml` — the read-token step has no `continue-on-error`,
    so the whole run fails; revert task 2's change to restore `app-id`
    immediately.
  - `gitops-bump.yaml` / `release-deploy.yaml` — same, no fallback tier;
    revert task 4a's change.
  - `build-image.yaml` — this step already runs under
    `continue-on-error: true` inside a documented credential-fallback
    ladder, so a missing `APP_CLIENT_ID` degrades to the next weaker tier
    (logged, per the existing comment at `build-image.yaml:70-88`) rather
    than failing the job outright; still revert task 4b/5 to restore the
    App-token tier's actual functionality.
- No data migration and no cluster resources are involved, so rollback is
  purely a workflow-file git revert with no other cleanup.
