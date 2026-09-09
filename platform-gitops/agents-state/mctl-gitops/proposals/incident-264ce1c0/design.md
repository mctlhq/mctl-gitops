# Design: incident-264ce1c0

## Confidence: LOW

## Diagnosis
`MctlTelegramToolAvailabilitySlowBurn` is a multi-window burn-rate alert on MCP
tool availability for the labs tenant's mctl-telegram service; it escalated
because it is a generic-type alert with no matching diagnostic skill. In the
sampled log window (2026-09-08T20:00-20:12Z, about 12 minutes of the last 6h
requested), the tenant's production instance (`labs-mctl-telegram-base-service-*`)
looks healthy: synthetic canary probes (`mcp_init`, `oauth_metadata`,
`list_dialogs`, `get_unread_messages`) all report `probe ok` / `canary run
complete ok=true`, and every sampled `mcp tool call` log line shows
`status=ok`. The one clear anomaly in the window is on the tenant's preview
instance (`labs-mctl-telegram-preview-base-service-*`): repeated `WARN auth
failed err="invalid JWT signature"` entries, each cycle preceded by a fresh
OAuth dynamic client registration request/audit pair from the same class of
client (e.g. "Google Antigravity"). That register-then-fail-then-re-register
pattern is consistent with the preview instance validating bearer tokens
against a JWT signing secret that does not match the one used to issue them —
e.g. the preview overlay was provisioned with its own signing secret, or is
pointing at a stale/rotated one instead of the one production issues tokens
with. Since every MCP tool call requires a valid bearer token, this would
make MCP tool calls against the preview instance fail consistently, which —
if the tool-availability SLO this alert tracks is computed across the
tenant's instances rather than production only — would produce exactly this
kind of elevated-but-not-saturating (slow burn) failure ratio over 6 hours.

Also present but unexplained: very frequent OAuth dynamic client registration
requests (multiple per minute) from client `cmg0c9xxt020wec596hjg563i` against
the *production* instance, with no accompanying failure logged. This may be
an unrelated, normally-behaving integration and is noted only as an
observation, not folded into the fix below.

## Proposed Fix
In mctl-gitops, locate the labs tenant's mctl-telegram **preview** overlay
(the values/ExternalSecret reference used by
`labs-mctl-telegram-preview-base-service`, e.g. under
`platform-gitops/services/labs/mctl-telegram/` or the preview-specific
values file for that service) and inspect the OAuth/JWT signing secret it is
configured with. If it references a different Vault path/secret than the one
the OAuth authorization server uses to sign tokens for the `labs-mctl-telegram`
host, repoint it at the correct/current signing secret so tokens issued for
the preview host validate against it.

## Scope
Minimal. Only touch the preview overlay's JWT/OAuth signing secret
reference. Do not touch the production instance's configuration, which shows
no evidence of a problem in the sampled logs.
