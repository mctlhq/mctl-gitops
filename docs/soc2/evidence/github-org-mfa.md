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
| 2026-08-17T06:52Z | `false` | `PATCH /orgs/mctlhq` with `two_factor_requirement_enabled=true` is a no-op; the field is not writable via this REST endpoint |

GitHub does not expose an org-owner REST toggle for this setting. It is an
Authentication security control in the org UI.

## Enable (org owner)

1. Open https://github.com/organizations/mctlhq/settings/security
2. Under "Authentication", enable **Require two-factor authentication**
3. Re-run the probe above. Required value: `true`
4. Update the table in this file with the new timestamp

Do not record member 2FA status here. The control is the **org requirement**,
not whether one account happens to have TOTP.

## Residual until enabled

`two_factor_requirement_enabled=false` remains a Type I CC6 sample fail.
Members may already use 2FA personally; that is not the control.
