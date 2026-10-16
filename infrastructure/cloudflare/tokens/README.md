# Account API tokens

A root of checks, not resources. It declares every account-owned Cloudflare
API token in `manifest.tf` and fails its plan when the live list differs. That
plan runs on every pull request touching `infrastructure/cloudflare/` and every
night in `cloudflare-drift.yml`, so a token created, widened, narrowed,
expired or revoked outside Git turns both red.

Nothing here creates or changes a token. Tokens are made in the dashboard
(*Manage account -> Account API tokens*). The value is shown once, at creation,
and goes straight into the GitHub secret, Vault path or Kubernetes Secret that
uses it. Only the name and the scope are recorded here. Managing tokens as
resources would put their values in state, which is why this root only reads.

## Rules

- **CI tokens are account-owned.** A token owned by a person's profile is
  invisible to `GET /accounts/{id}/tokens`, so this check cannot see it, and
  it stops working when that person loses access to the account.
- **Change the dashboard and the manifest in one pull request.** The plan of
  this root on that pull request is the proof that they agree. A pull request
  that changes only the manifest goes red, and so does a dashboard change with
  no pull request.
- **Name tokens after their consumer**, for example
  `mctl-gitops-apply-account (cloudflare-iac #1111)`. The dashboard's R2 page
  names every token `R2 Account Token`. Those are declared as found, but their
  consumers are not recorded.

## What is compared

Per token: name, status, expiry, IP condition, and each policy's effect,
permission group IDs and resources. The manifest has no field for status,
expiry or IP condition: every entry is declared active, without expiry and
without an IP condition, and a live token that differs in any of them fails
the check like any other difference. Token IDs, issue dates and last use are
not compared, so rotating a token with the same scope needs no change here.
Names are not unique, so the comparison counts each distinct fingerprint on
both sides. Two identical live tokens need two entries.

One blind spot: the provider cannot represent a nested resource map (an
account with a zone wildcard under it) and returns `resources = null` for it.
`Edit zone DNS` is such a token, so its zone scope is not verified, only its
name, status and permission groups. The `token_scopes_observable` check block
warns about every such token, and the drift summary reports it as UNVERIFIED
rather than in sync. Re-issuing the token with its zones listed flat removes
the gap.

A failed read is a failed plan, never an empty list. Without
`Account API Tokens Read` the API answers 9109 and the data source errors. A
listing that does come back empty fails the first postcondition.

## Credentials

Plan and drift use `CF_ACCOUNT_READ_TOKEN`, which carries
`Account API Tokens Read`. The root has no resources and no apply token, so
`cloudflare-apply.yml` refuses it.
