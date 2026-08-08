# Design: issue-81-evaluate-migrating-github-sign-in-from-a

## Current state

GitHub sign-in in `mctl-academy` runs entirely through better-auth's built-in
social provider, wired in `server/auth.mjs`:

```js
socialProviders: {
  ...(process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET
    ? {
        github: {
          clientId: process.env.GITHUB_CLIENT_ID,
          clientSecret: process.env.GITHUB_CLIENT_SECRET,
          mapProfileToUser: (profile) => ({ githubLogin: profile.login }),
        },
      }
    : {}),
  ...
}
```

The provider is only registered when both env vars are set (a deliberate
choice per the comment above it, so a misconfigured environment gets
better-auth's clean "provider not found" instead of a broken OAuth
handshake). `mapProfileToUser` stores `profile.login` into a custom
`githubLogin` field (`user: { additionalFields: { githubLogin: ... } }`),
because `MCTL_ACADEMY_MODERATORS` allowlists by GitHub username and
better-auth's built-in user table has no such column.

The client side (`client/src/components/UserNav.tsx`) triggers sign-in via
`authClient.signIn.social({ provider: "github", callbackURL: "/" })`
(`client/src/authClient.ts` wraps better-auth's React client with no
provider-specific code). Nothing here changes regardless of which kind of
GitHub OAuth client issues the credentials — the provider id stays
`"github"` either way.

Read directly from the `better-auth` package (`packages/core/src/social-
providers/github.ts`, `main` branch — installed version is `^1.6.26` per
`package.json`; this clone has no `node_modules`, so a lockfile-pinned
version diff is a task, not assumed here):

- Authorize URL is hardcoded: `https://github.com/login/oauth/authorize`.
- Token URL is hardcoded: `https://github.com/login/oauth/access_token`.
- `createAuthorizationURL` always requests
  `scopes = options.disableDefaultScope ? [] : ["read:user", "user:email"]`,
  plus anything in `options.scope`. `server/auth.mjs` sets neither
  `disableDefaultScope` nor `scope`, so today's request always carries
  `scope=read:user user:email`.
- `getUserInfo` calls `GET https://api.github.com/user` then
  `GET https://api.github.com/user/emails`, both with
  `Authorization: Bearer <token>`, and falls back to the primary/first email
  from the emails endpoint if `profile.email` is null (which it is for OAuth
  App tokens without `user:email`, and would be for a GitHub App token
  without the Account permission the issue calls for).
- The only credential inputs are `clientId` / `clientSecret`
  (`GithubOptions extends ProviderOptions`). There is no branch in this file
  for "this client id belongs to a GitHub App" — better-auth treats every
  `github` social login identically regardless of which GitHub product
  issued the OAuth client.

GitHub's own docs for "Generating a user access token for a GitHub App"
confirm the App's user-to-server flow reuses the identical two endpoints
above, with PKCE optional (recommended, not required). That is the basis for
the issue's central claim, and it checks out: **swapping which kind of
GitHub OAuth client issues `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` requires
no change to `server/auth.mjs` or any client code.**

better-auth's `account` table (`migrations/1754607600000_better-auth-
schema.mjs`) keys each linked identity on `(providerId, accountId)`, where
`accountId` for GitHub is `profile.id` — GitHub's numeric user id, which is
stable and does not depend on which OAuth client (App or classic App)
authorized a given sign-in. This matters directly for a safe cutover: an
existing learner who already has a `user`/`account` row from the current
OAuth App will resolve to the *same* row after the credential swap, because
their GitHub numeric id is unchanged; better-auth does not key on
`providerId` + client id.

`"user"."email"` is `not null unique` in that same migration, and
`PRIVACY.md` ("A note on email") documents that better-auth requires an
email address regardless of provider. This is why the issue's proposed
App permission (`Account permissions -> Email addresses: Read-only`) is not
an optional hardening nice-to-have — without it, `getUserInfo`'s email
fallback returns nothing and `"user".email`'s `not null` constraint fails
sign-in outright, for both today's OAuth App and any future GitHub App.

Deployment: `mctl_get_service_config` shows `mctl-academy` is live in team
`labs`, image `0.1.23`, host `academy.mctl.ai`, with a database provisioned.
`PLAN.md` section 8 documents the two platform constraints that shape how
credentials are set: `env_vars` silently drops any value containing `:`
(irrelevant here — client id/secret are colon-free — but the callback/base
URL values that travel alongside them are not, so everything OAuth-related
already goes through `secret_env_vars`, not `env_vars`), and
`action=deploy` re-renders `values.yaml` and has previously erased a
populated `env:` block on a tag bump. The existing OAuth App credential
delivery already respects both constraints (bootstrap step 6 in `PLAN.md`);
a credential swap should use the identical `update-config` /
`secret_env_vars` path, not a new one.

## Proposed solution

Two-stage plan, gated on an empirical spike because one detail (see
`requirements.md`'s Open questions) cannot be settled from documentation
alone:

**Stage 1 — Spike (no production impact).**
Create a throwaway or explicitly-test-labeled GitHub App under `mctlhq`
(or a personal account, whichever is faster to tear down) with *only*
`Account permissions -> Email addresses: Read-only` and a
`localhost`/loopback callback. Point a local or preview instance of
`mctl-academy` at its client id/secret (via `secret_env_vars` in a preview
environment, or a local `.env` — never committed) and walk through
`authClient.signIn.social({ provider: "github" })` end to end. Confirm:

1. The authorize redirect succeeds despite better-auth's unconditional
   `scope=read:user user:email` parameter (the one behavior GitHub's docs
   don't state either way for a GitHub App client).
2. `GET /user/emails` returns data with the App's user-to-server token,
   given only the Email read permission.
3. The resulting `githubLogin` / `email` mapping in the `user` table matches
   what the OAuth App produces today for the same GitHub account.

This is cheap, fully reversible, and touches nothing in production — it is
the "independent verification" the issue asks for, taken from documentation
review to an actual run.

**Stage 2 — Migration (only if Stage 1 passes).**
1. Create the permanent, dedicated GitHub App for `mctl-academy` under
   `mctlhq` (issue's Option 3): name distinct from `mctl-agents`,
   `Account permissions -> Email addresses: Read-only` only, no `contents`,
   `issues`, or `pull_requests` permission, production + any preview
   callback URLs registered.
2. `mctl_deploy_service action=update-config`, `team_name=labs`,
   `component_name=mctl-academy`, with `secret_env_vars` carrying the new
   `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` (same mechanism `PLAN.md`
   already prescribes for the OAuth App — no new plumbing).
3. Verify: an existing account's next GitHub sign-in resolves to its
   existing `user` row (no duplicate), a fresh sign-in for a new learner
   works, and `githubLogin` continues to populate correctly.
4. Only after a confirmed soak period, deauthorize/delete the old OAuth App
   ("mctl Academy", app id 3779821). Keep it intact until then — it is the
   entire rollback path.

No change to `server/auth.mjs`, `authClient.ts`, `UserNav.tsx`, or any
migration file. `mapProfileToUser` reads `profile.login`, which the GitHub
REST `/user` response returns identically whether the caller authenticated
via an OAuth App or a GitHub App's user-to-server token.

## Alternatives

1. **Status quo (issue's Option 1).** Keep the classic OAuth App. Zero
   migration risk, zero engineering cost. Correct choice if Academy never
   grows past sign-in, and the safe fallback if Stage 1's spike fails.
   Dropped as the *default* recommendation only because the issue's stated
   motivation (future practical exercises needing scoped, short-lived
   installation tokens) is a real, deliberate reason to prefer a GitHub App
   now rather than re-migrating later under time pressure — but it remains
   the fallback, not a rejected option, pending the spike.
2. **Reuse the `mctl-agents` GitHub App (issue's Option 2)**, installation
   150422769 / app id 4450852. Rejected per the issue's own reasoning and
   confirmed by reading the issue body's link to `mctl-gitops#761`: that App
   currently holds `contents`/`issues`/`pull-requests: write` across all 16
   org repos. Wiring academy's login through it would make a leaked academy
   env var carry that entire blast radius, and conflates two different
   trust domains (a learner's login vs. the agent-PR pipeline) even after
   #761 narrows the grant. Not revisited by this proposal.
3. **Migrate now without a spike, on documentation alone.** Rejected: the
   `scope` parameter behavior against a GitHub App's authorize endpoint is
   the one piece this session could not confirm from GitHub's docs or
   better-auth's source (both describe GitHub Apps as scope-less/
   permission-based without stating what happens when a scope-shaped
   parameter arrives anyway). Migrating production credentials on an
   unconfirmed detail is exactly the mistake the issue was opened to avoid
   ("this needs independent verification before any implementation").

## Platform impact

- **Migrations:** none. No schema change — `providerId` stays `"github"`,
  `accountId` stays the GitHub numeric user id regardless of which client
  authorized the request.
- **Backward compatibility:** existing `user`/`account` rows are preserved
  automatically (see Current state — keyed on GitHub numeric id, not client
  id). No data backfill, no forced re-registration.
- **Resource impact:** none. This is a credential/config change only; no new
  service, no new database, no replica or resource-request change to the
  existing `mctl-academy` deployment (`requests 50m/128Mi`, `limits
  200m/512Mi` per `PLAN.md`).
- **Risks and mitigations:**
  - *Risk:* the unconfirmed `scope` parameter behavior breaks the authorize
    step against a GitHub App client in a way that only surfaces in
    production. *Mitigation:* Stage 1's spike runs this exact flow against a
    real GitHub App before any production credential change.
  - *Risk:* a credential swap mid-flight briefly breaks sign-in for users
    mid-session. *Mitigation:* `update-config` only changes the OAuth
    client used for *new* authorize requests; existing sessions are
    unaffected (better-auth sessions do not re-validate against the OAuth
    provider). Swap during low-traffic hours as a precaution given this is a
    live, if low-traffic, education product.
  - *Risk:* the new GitHub App is misconfigured (wrong callback URL, missing
    Email permission) and locks out sign-in entirely. *Mitigation:* keep the
    old OAuth App live and unmodified until a confirmed soak period passes;
    rollback is a second `update-config` call restoring the previous
    `GITHUB_CLIENT_ID`/`SECRET`, no deploy/rebuild required.
  - *Risk:* scope creep — the new App accumulates permissions over time the
    way the issue warns `mctl-agents`'s App did. *Mitigation:* explicit
    acceptance criterion that the App carries only the Email permission at
    creation; any future permission (for practical exercises) is a separate,
    deliberate proposal, not bundled here.
