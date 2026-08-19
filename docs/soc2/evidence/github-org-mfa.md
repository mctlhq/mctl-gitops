# Evidence: GitHub org two-factor requirement

Control: CC6 logical access — GitHub is the identity provider for humans
(OAuth, git, Actions). Org-wide MFA is the sample a CPA takes on day one.

## Probe

```bash
gh api orgs/mctlhq --jq .two_factor_requirement_enabled
```

| When (UTC) | Result | How |
|---|---|---|
| 2026-08-17T06:45Z | `false` | Type I readiness audit |
| 2026-08-17T06:52Z | `false` | `PATCH /orgs/mctlhq` is a no-op; field is not writable via REST |
| 2026-08-19T16:37Z | `true` | Owner enabled in org Authentication security UI. Also "Only allow secure two-factor methods" (authenticator / passkey / security key / GitHub Mobile; SMS disallowed). |

The control is the **org requirement**, not whether one account happens to
have TOTP.

## Residual after enable

Two org members still have 2FA unset (`gh api 'orgs/mctlhq/members?filter=2fa_disabled'`).
They cannot use org resources until they enroll. Do not list logins here.
Track them in the next access review (`access-review.md`).
