# Evidence: GitHub org two-factor requirement

Control: CC6 logical access — GitHub is the identity provider for humans
(OAuth, git, Actions). Org-wide MFA is the sample a CPA takes on day one.

## Probe

```bash
gh api orgs/mctlhq --jq .two_factor_requirement_enabled
gh api 'orgs/mctlhq/members?filter=2fa_disabled'
```

| When (UTC) | Requirement | `2fa_disabled` | How |
|---|---|---|---|
| 2026-08-17T06:45Z | `false` | (not counted) | Type I readiness audit |
| 2026-08-17T06:52Z | `false` | (not counted) | `PATCH /orgs/mctlhq` is a no-op; field is not writable via REST |
| 2026-08-19T16:37Z | `true` | 2 | Owner enabled in org Authentication security UI. Also "Only allow secure two-factor methods" (authenticator / passkey / security key / GitHub Mobile; SMS disallowed). |
| 2026-08-19T16:44Z | `true` | 0 | Owner removed the two members who had not enrolled. Do not list logins here. |

The control is the **org requirement**, not whether one account happens to
have TOTP. After 2026-08-19T16:44Z both the requirement and the membership
set match: six members, none without 2FA.
