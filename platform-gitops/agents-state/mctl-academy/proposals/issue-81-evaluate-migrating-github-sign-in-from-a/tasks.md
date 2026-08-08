# Tasks: issue-81-evaluate-migrating-github-sign-in-from-a

- [ ] 1. Run the spike: create a throwaway/test-labeled GitHub App (org
      `mctlhq` or personal, whichever is faster to create and delete) with
      only `Account permissions -> Email addresses: Read-only` and a
      `localhost` callback. Point a local or preview `mctl-academy` instance
      at its client id/secret and exercise
      `authClient.signIn.social({ provider: "github" })` end to end. — DoD:
      written record (proposal follow-up comment or a note in this repo) of
      whether the authorize redirect succeeds with better-auth's
      unconditional `scope=read:user user:email` parameter against a
      GitHub App client, whether `GET /user/emails` returns data, and
      whether the resulting `githubLogin`/`email` values match what the
      current OAuth App produces for the same account.
- [ ] 2. Diff the installed `better-auth` version's actual
      `dist/social-providers/github.mjs` (or `node_modules` source) against
      the `main`-branch `packages/core/src/social-providers/github.ts` read
      in `design.md`, using the version pinned by `bun.lock` /
      `package.json` (`^1.6.26`) — this clone had no `node_modules` to check
      directly. (depends on none; can run in parallel with Task 1) — DoD:
      confirmed no material difference in endpoint URLs, default scope
      behavior, or `getUserInfo` call shape for the actually-deployed
      version.
- [ ] 3. Decide go/no-go based on Tasks 1-2. (depends on 1, 2) — DoD: a
      recorded decision — proceed to Task 4 if the spike passed cleanly;
      otherwise stop here and the recommendation reverts to status quo
      (issue's Option 1), with the reason logged for future reference if the
      question is revisited later.
- [ ] 4. Create the permanent, dedicated GitHub App for `mctl-academy` under
      `mctlhq`: name distinguishable from `mctl-agents`'s App, `Account
      permissions -> Email addresses: Read-only` only (no `contents`,
      `issues`, `pull_requests`, no repository access), production callback
      (`https://academy.mctl.ai/api/auth/callback/github`, matching
      better-auth's callback path convention) plus any preview/localhost
      callbacks the team uses. (depends on 3) — DoD: GitHub App exists,
      permissions verified in its settings page to be exactly the one
      Account permission, app id and installation recorded alongside app id
      3779821 and 4450852 for future reference (e.g. in this proposal's
      follow-up or a platform note).
- [ ] 5. Swap production credentials via
      `mctl_deploy_service action=update-config team_name=labs
      component_name=mctl-academy` with `secret_env_vars` carrying the new
      App's `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` — the same delivery
      path `PLAN.md` already uses for the OAuth App, never plain `env_vars`.
      (depends on 4) — DoD: workflow completes successfully: poll
      `mctl_get_workflow_status`; ExternalSecret/Vault path confirmed
      updated; do not touch `env:` plain vars in the same call, to avoid
      tripping the documented `action=deploy` `values.yaml`-erasure bug's
      cousin behavior on `update-config`.
- [ ] 6. Verify in production: an existing learner's GitHub sign-in resolves
      to their existing account (no duplicate `user` row for the same
      GitHub numeric id), a brand-new learner can sign in and get a correct
      `githubLogin`, and `MCTL_ACADEMY_MODERATORS` allowlisting still
      resolves moderators correctly. (depends on 5) — DoD: at least one
      known existing account and one fresh account both verified signed-in
      successfully post-swap; `mctl_get_service_logs team=labs
      service=mctl-academy` shows no new auth-related error class.
      Recommend a low-traffic time window for this step, and a hold at Task
      6 (soak) before Task 7.
- [ ] 7. After a soak period with no sign-in regressions, deauthorize or
      delete the classic OAuth App (app id 3779821). (depends on 6) — DoD:
      old App removed or explicitly disabled; `PLAN.md` section 8 and this
      proposal both stay accurate about which App issues production
      credentials (update `PLAN.md`'s bootstrap step 5 language from
      "Create the GitHub OAuth App" to reflect the GitHub App going
      forward, in a follow-up doc PR).

## Tests

- [ ] T1. Spike-stage manual test (Task 1): full sign-in round trip against
      the throwaway GitHub App succeeds and produces the expected
      `user`/`account`/`githubLogin` state — this is the test that answers
      the issue's central open question and gates everything after it.
- [ ] T2. Existing `tests/` suite (whatever currently exercises
      `/api/auth/callback/github` — the CI comment in
      `.github/workflows/ci.yml` references a "real-redirect regression
      test") continues to pass unmodified after the credential swap, since
      no code changes: confirm CI is green on the branch that performs Task
      5's `update-config` follow-up (if that work produces a code/doc PR;
      `update-config` itself is an MCP operation, not a code change, so
      there is no CI run to gate it directly — this is a check on any
      companion PR, e.g. the `PLAN.md` update in Task 7).
- [ ] T3. Post-swap production smoke test (Task 6): existing-account
      sign-in and new-account sign-in both verified manually against
      `academy.mctl.ai`.
- [ ] T4. Confirm Google sign-in is unaffected: sign in with Google
      post-swap and verify no regression (the `google` block in
      `server/auth.mjs` is untouched, but this is a one-command check worth
      doing given both providers share `auth.mjs`'s `socialProviders` map
      construction).

## Rollback

Every stage before Task 7 is trivially reversible:

- **Tasks 1-3 (spike, decision):** no production changes made; delete the
  throwaway GitHub App when done. Nothing to roll back.
- **Task 4 (create App):** delete the new GitHub App if the decision changes
  before Task 5. No production impact yet.
- **Task 5 (credential swap):** roll back with a second
  `mctl_deploy_service action=update-config` call restoring the previous
  `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` (the OAuth App's credentials,
  app id 3779821) via `secret_env_vars`. No redeploy, no rebuild, no schema
  change — this is why Task 7 (deleting the old OAuth App) is deliberately
  held until after a soak period: the old App must stay live and
  authorized for this rollback path to work.
- **Task 6 (verification finds a regression):** same rollback as Task 5;
  additionally capture the failure mode (which step of sign-in broke, what
  `mctl_get_service_logs` shows) before rolling back, since that evidence is
  exactly what the spike (Task 1) was supposed to catch and would indicate a
  gap in the spike's coverage worth recording for next time.
- **Task 7 (old App deauthorized):** this is the point of no easy return for
  the *old* App specifically, but the *service* itself is still recoverable
  by creating a fresh OAuth App and repeating Task 5's `update-config` swap
  in the other direction — slower (new App to create) but not destructive to
  any data, since `providerId`/`accountId` keying is unaffected either way.
