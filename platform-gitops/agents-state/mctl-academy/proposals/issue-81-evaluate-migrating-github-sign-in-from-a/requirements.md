# Evaluate migrating GitHub sign-in from a classic OAuth App to a GitHub App

## Context

`mctl-academy` signs users in through better-auth's `socialProviders.github`
(`server/auth.mjs`), configured with a plain `GITHUB_CLIENT_ID` /
`GITHUB_CLIENT_SECRET` pair from a classic GitHub **OAuth App** ("mctl
Academy", app id 3779821, org `mctlhq`). The service is live at
`academy.mctl.ai` (image `0.1.23`, team `labs`) and GitHub sign-in works
correctly today — this is not a bug fix.

Issue #81 asks whether that OAuth App should be replaced with a dedicated
GitHub App, on the premise that a GitHub App gives fine-grained, short-lived,
repo-scoped installation tokens that would matter if Academy grows beyond
"just a login button" (e.g. practical exercises that open a PR against a
starter repo and get verified via checks/webhooks). The issue explicitly
flags a claim that needs verification before any implementation: that
better-auth's GitHub provider needs no code change to work against a GitHub
App's user-to-server OAuth flow, provided the App has `Account permissions ->
Email addresses: Read-only`.

This proposal performs that verification against the actual better-auth
source and GitHub's documentation, confirms what is safe to conclude
mechanically, and scopes the migration work — gated on a runtime spike for
the one detail that cannot be settled from documentation alone.

## Verification performed (this proposal)

Read `packages/core/src/social-providers/github.ts` from the `better-auth`
GitHub repository (main branch; the installed version is `^1.6.26`, no
`node_modules` in this clone to check a lockfile-pinned copy against, so this
should be re-checked against the exact resolved version before cutover):

- `createAuthorizationURL` hardcodes
  `authorizationEndpoint: "https://github.com/login/oauth/authorize"`.
- `validateAuthorizationCode` hardcodes
  `tokenEndpoint = "https://github.com/login/oauth/access_token"`.
- The only required option is `clientId` (`GithubOptions extends
  ProviderOptions`); `clientSecret` comes from the shared `ProviderOptions`
  type used by every provider. There is no GitHub-App-specific code path,
  no separate "app type," and no field for an App's installation id.
- `getUserInfo` calls `GET https://api.github.com/user` and
  `GET https://api.github.com/user/emails`, both with
  `Authorization: Bearer <token>`.

GitHub's own docs ("Generating a user access token for a GitHub App")
confirm the GitHub App user-to-server flow uses the **same two endpoints**
(`/login/oauth/authorize`, `/login/oauth/access_token`) as a classic OAuth
App, and that PKCE is optional (recommended, not required), so no additional
parameter is mandatory on top of what better-auth already sends.

**Conclusion: the core claim holds.** Pointing `GITHUB_CLIENT_ID` /
`GITHUB_CLIENT_SECRET` at a GitHub App's client id/secret requires no
better-auth code change in `server/auth.mjs`.

**One detail does not resolve from documentation and must be verified at
runtime (see Open questions and `design.md`):** better-auth's
`createAuthorizationURL` unconditionally requests
`scope=read:user user:email` on the authorize call. GitHub's docs state that
GitHub Apps use fine-grained permissions instead of OAuth scopes for
user-to-server tokens ("the scope field returns an empty string"), but do
not document whether an OAuth-shaped `scope` parameter sent to a GitHub
App's authorize endpoint is silently ignored or causes an error. This is
exactly the kind of claim the issue asks not to take on faith.

Also confirmed independently, relevant to why the email permission is not
optional: `migrations/1754607600000_better-auth-schema.mjs` defines
`"user"."email"` as `not null unique`, and `PRIVACY.md` ("A note on email")
states better-auth requires an email address regardless of provider. Any
GitHub credential this app uses — OAuth App or GitHub App — must be able to
read the user's email, or sign-in breaks outright.

## User stories

- AS the maintainer I WANT the better-auth-against-GitHub-App claim verified
  against real source and real GitHub behavior SO THAT a credential swap in
  production is not based on an unconfirmed external claim.
- AS the maintainer I WANT a scoped, dedicated GitHub App (if the migration
  proceeds) SO THAT `mctl-academy`'s login flow never inherits permissions it
  does not use, and never shares a trust boundary with the `mctl-agents`
  App's org-wide `contents`/`issues`/`pull-requests: write` grant.
- AS a learner who already has an `mctl-academy` account WANT sign-in to keep
  working after any credential change SO THAT I am not locked out or
  double-registered under a new account.
- AS the maintainer I WANT the migration reversible within one deploy SO THAT
  a broken GitHub App configuration does not cause extended sign-in downtime.

## Acceptance criteria (EARS)

- WHEN this proposal is implemented THE SYSTEM SHALL document, in
  `design.md`, the verified better-auth source behavior and the GitHub
  user-to-server OAuth flow, citing the specific files/paths read.
- WHEN the spike task (see `tasks.md`) is run against a real, newly created
  GitHub App configured with only `Account permissions -> Email addresses:
  Read-only` THE SYSTEM SHALL record whether the authorize request
  containing `scope=read:user user:email` succeeds unmodified against that
  App's `/login/oauth/authorize` endpoint.
- IF the spike succeeds THEN THE SYSTEM SHALL proceed with creating a
  dedicated, minimally-scoped GitHub App for `mctl-academy` (issue's Option
  3) and swapping `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` via
  `mctl_deploy_service action=update-config` using `secret_env_vars` only
  (never plain `env_vars`, per `PLAN.md` section 8 and this repo's
  `CLAUDE.md`, since both values and any callback URL may contain `:`... in
  practice these two values do not contain `:`, but the callback/base URL
  values already routed through `secret_env_vars` do, and the swap should
  not open a second, inconsistent path).
- IF the spike fails (GitHub rejects or silently strips the flow in a way
  that breaks email retrieval) THEN THE SYSTEM SHALL NOT proceed with the
  credential swap, and the proposal's recommendation reverts to Option 1
  (status quo) until better-auth or GitHub changes behavior.
- WHEN the credential swap is deployed THE SYSTEM SHALL preserve existing
  users' accounts: because better-auth's `account` table keys on
  `(providerId="github", accountId=<GitHub numeric user id>)` and GitHub
  numeric user ids do not change based on which App or OAuth App authorized
  the request, an existing learner signing in again after the swap SHALL
  resolve to their existing `user`/`account` row, not create a duplicate.
- WHILE the new GitHub App exists THE SYSTEM SHALL grant it only `Account
  permissions -> Email addresses: Read-only` — no `contents`, `issues`, or
  `pull_requests` permission, and no repository access beyond what account
  identity requires.
- IF the credential swap causes sign-in failures in production THEN THE
  SYSTEM SHALL be revertible by restoring the previous OAuth App's
  `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` via the same `update-config`
  path within one deploy, with no schema or code rollback required.
- WHERE Google sign-in is concerned THE SYSTEM SHALL make no change: Google
  has no OAuth-App/GitHub-App distinction, and `server/auth.mjs`'s `google`
  provider block is untouched by this proposal.

## Out of scope

- Actually building GitHub-App-only capabilities (installation tokens,
  repo-scoped checks/webhooks for practical exercises). This proposal is
  login-transport only; the "practical exercises" idea referenced in the
  issue is not designed or scheduled here.
- Reusing the existing `mctl-agents` GitHub App (installation 150422769, app
  id 4450852) for login. The issue itself rules this out until
  `mctl-gitops#761` narrows that App's org-wide write access, and probably
  not even then (different trust domains). This proposal does not revisit
  that conclusion.
- Any change to Google sign-in.
- Any change to what user data is stored (`PRIVACY.md`'s table is unaffected
  — email, GitHub login, name, and avatar are still the only fields read).
- Deep-diving `better-auth`'s exact resolved version behavior beyond what is
  readable from the upstream `main` branch source in this session (no
  `node_modules` present in this clone to check the lockfile-pinned build
  directly — flagged as a task, not assumed away).

## Open questions

- Does GitHub's `/login/oauth/authorize` endpoint, when the OAuth `client_id`
  belongs to a GitHub App rather than an OAuth App, accept an OAuth-shaped
  `scope` parameter (`read:user user:email`) without error, since
  better-auth sends one unconditionally and offers no built-in way to
  suppress it short of `disableDefaultScope` (which better-auth's config in
  `server/auth.mjs` does not currently set)? Not resolved by documentation
  in this session. Recorded as the spike task in `tasks.md` (Task 1) —
  proceed with the recommended interpretation (most GitHub API surfaces
  ignore unrecognized/inapplicable query parameters rather than erroring,
  and GitHub's own docs for the flow show `scope` as accepted-but-optional
  for the redirect step) but verify empirically before touching production
  credentials.
- Does the installed `better-auth@^1.6.26` (no lockfile-pinned copy present
  in this read-only clone) match the `main`-branch source read here closely
  enough that the conclusions hold? Recorded as a task (Task 2): diff
  against the actual resolved version before cutover.
- Should the new dedicated GitHub App be user-owned or org-owned under
  `mctlhq`, matching how the existing OAuth App and the `mctl-agents` App are
  organized? The issue does not say. Proceeding with org-owned under
  `mctlhq`, consistent with both existing GitHub identities referenced in
  the issue.
- Timeline: the issue is explicitly non-urgent ("not a bug fix"). This
  proposal does not assume a deadline; `tasks.md` sequences work so the
  spike (cheap, reversible, no production impact) happens before any
  decision to touch production credentials.
