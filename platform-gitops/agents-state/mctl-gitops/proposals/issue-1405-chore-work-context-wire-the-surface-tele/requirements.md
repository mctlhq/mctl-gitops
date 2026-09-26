# Wire the surface:telegram token and work-context config into mctl-api and mctl-telegram, off by default

## Context

`mctlhq/mctl-telegram#443` shipped the Telegram work-context adapter in
0.69.0 and `labs-mctl-telegram` runs that image
(`platform-gitops/services/labs/mctl-telegram/values.yaml`, `image.tag:
"0.69.0"`), but no deployment receives the configuration the feature reads.
mctl-telegram reads `WORK_CONTEXT_ENABLED`, `MCTL_API_BASE_URL`,
`MCTL_SURFACE_TELEGRAM_TOKEN` and `MCTL_WORK_ITEM_TENANT`; the labs values
file maps none of them — its `envFrom` covers only `db-creds`, `tg-api`,
`encryption`, `oauth`, `login` and `demo`. On the other side, mctl-api
authenticates the `surface:telegram` principal from
`MCTL_SURFACE_TELEGRAM_TOKEN` (`internal/auth/oidc.go`, `surfaceTokenEnv`
maps `telegram` -> that variable, `minSurfaceTokenLen = 32`), and nothing
under `platform-gitops/bootstrap/templates/mctl-platform/` provides it. Until
the wiring exists, writing the token to Vault changes nothing and the owner's
enablement step has nothing to flip.

This proposal is gitops-only and lands the wiring **committed but inert**,
following the `usageWriter` precedent in this repo
(`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-usage-writer.yaml`
plus `usageWriter.enabled` in `platform-gitops/bootstrap/values.yaml`) and
the both-states CI precedent already used for it
(`.github/workflows/validate-manifests.yml`, the "Render and validate the
usage-writer overlay" step). With the gates off the rendered manifests of
both applications must be byte-identical to `main`, so merging changes no
cluster state; the four owner steps (Vault write, tenant value, wiring on,
feature flag on) are documented next to the flags and performed by nobody in
this change.

## User stories

- AS the platform owner I WANT the `surface:telegram` token and the
  work-context configuration already wired, gated behind flags that default
  to off, SO THAT enabling the feature is a reviewed values flip rather than
  an unreviewed authoring exercise under time pressure.
- AS the platform owner I WANT mctl-api and mctl-telegram to read the token
  from one single Vault property SO THAT there is one value to rotate and
  nothing to keep in step.
- AS a reviewer of this change I WANT CI to prove that the gate-off render is
  byte-identical to `main` SO THAT merging is provably a no-op on the
  cluster.
- AS an on-call operator I WANT a missing or unwritten Vault property to
  degrade only the work-context wiring SO THAT it cannot take `DB_PASSWORD`,
  `OAUTH_JWT_SECRET`, `ENCRYPTION_KEY` or the Telegram API credentials down
  with it.

## Acceptance criteria (EARS)

Gate-off invariants

- WHILE both gates are off (`surfaceTelegramToken.enabled: false` in
  `platform-gitops/bootstrap/values.yaml` and `workContext.enabled: false`
  in `platform-gitops/services/labs/mctl-telegram/values.yaml`) THE SYSTEM
  SHALL render the `admins-mctl-api` Application and the
  `labs-mctl-telegram` manifests byte-identically to `main`.
- WHILE the `workContext` gate is off THE SYSTEM SHALL render the
  `base-service` chart for a values file containing the `workContext` block
  byte-identically to the same values file with the `workContext` key
  deleted, for every workload kind the chart can emit (`Deployment` and
  `Rollout`).
- WHILE both gates are off THE SYSTEM SHALL render no `ExternalSecret` named
  `mctl-api-surface-telegram` and none named
  `labs-mctl-telegram-work-context`.
- WHEN CI runs on a pull request THE SYSTEM SHALL render both gate states of
  both applications and SHALL fail if a gate-on marker appears in the
  gate-off render, or is missing from the gate-on render.

Gate-on behaviour

- WHEN the mctl-api gate is on THE SYSTEM SHALL render an `ExternalSecret`
  named `mctl-api-surface-telegram` in namespace `mctl-api` whose only
  `data` entry maps `secretKey: MCTL_SURFACE_TELEGRAM_TOKEN` from Vault key
  `platform/mctl-api/surface-tokens`, property `telegram-token`.
- WHEN the mctl-api gate is on THE SYSTEM SHALL pass
  `surfaceTelegramTokenSecret: mctl-api-surface-telegram` in the
  `admins-mctl-api` Application's Helm values, so the mctl-api chart injects
  the variable through an optional `secretKeyRef`, exactly as
  `usageWriterTokenSecret` does today.
- WHEN the mctl-telegram gate is on THE SYSTEM SHALL render an
  `ExternalSecret` named `labs-mctl-telegram-work-context` that reads the
  same Vault path and property as the mctl-api one, in the tenant spelling
  (`remoteKey: secret/data/platform/mctl-api/surface-tokens`, `property:
  telegram-token`), into its own target Secret.
- WHEN the mctl-telegram gate is on THE SYSTEM SHALL add
  `MCTL_SURFACE_TELEGRAM_TOKEN` to the container env from that Secret via
  `secretKeyRef` with `optional: true`, and SHALL add
  `MCTL_WORK_ITEM_TENANT` from the `workContext.tenant` values key and
  `WORK_CONTEXT_ENABLED` from the separate `workContext.featureEnabled`
  values key.
- WHILE `workContext.apiBaseUrl` is empty THE SYSTEM SHALL NOT render
  `MCTL_API_BASE_URL`, leaving mctl-telegram's own default
  (`https://api.mctl.ai`) in force.
- IF a values file sets `MCTL_WORK_ITEM_TENANT`, `WORK_CONTEXT_ENABLED`,
  `MCTL_API_BASE_URL` or `MCTL_SURFACE_TELEGRAM_TOKEN` explicitly under
  `env:` or `envValueFrom:` THEN THE SYSTEM SHALL let the explicit entry win,
  matching the precedence `otel.enabled` already uses in
  `base-service.env`.

Failure isolation and validation

- IF the Vault property does not exist THEN THE SYSTEM SHALL degrade only
  the two new `ExternalSecret` objects, and SHALL leave `mctl-api-secrets`,
  `mctl-api-events`, `labs-mctl-telegram-db-creds`,
  `labs-mctl-telegram-tg-api`, `labs-mctl-telegram-encryption`,
  `labs-mctl-telegram-oauth`, `labs-mctl-telegram-login` and
  `labs-mctl-telegram-demo` unaffected.
- IF `workContext.enabled` is true while `workContext.tokenVaultKey` or
  `workContext.tokenVaultProperty` is empty THEN THE SYSTEM SHALL fail the
  Helm render with a named error rather than emit an `ExternalSecret` with
  an empty `remoteRef`.
- WHEN the gate-on manifests are rendered in CI THE SYSTEM SHALL validate
  them with `kubeconform -strict` against the CRD catalogue, as the existing
  usage-writer step does.
- THE SYSTEM SHALL document the owner steps — Vault write, tenant value,
  wiring gate on, `WORK_CONTEXT_ENABLED` on — as comments immediately above
  each flag, in the order they must be performed, and SHALL perform none of
  them.

## Out of scope

- Writing, rotating or reading any Vault value. No credential is created by
  this change.
- Turning either gate on in production, and turning `WORK_CONTEXT_ENABLED`
  on.
- Any change to mctl-telegram application code, and any change to mctl-api
  application code. The one mctl-api-side prerequisite this proposal depends
  on — an optional `surfaceTelegramTokenSecret` value in that repo's
  `helm/` chart, mirroring the existing `usageWriterTokenSecret` — is named
  as a dependency and is NOT authored here.
- NetworkPolicy changes. The `labs` namespace already reaches external 443
  for Telegram; whether `api.mctl.ai` is reachable from it is an operator
  check on mctl-telegram#443.
- Wiring the second surface mctl-api already knows about
  (`MCTL_SURFACE_PORTAL_TOKEN` in `surfaceTokenEnv`).
- Any live acceptance run of the work-context feature.

## Open questions

- The issue does not name the Vault path. This proposal chooses
  `secret/platform/mctl-api/surface-tokens`, property `telegram-token`,
  because mctl-api is the verifier of every surface principal and a second
  surface then adds a property, not a path. An owner who prefers
  `platform/mctl-telegram/...` changes two lines and one test constant.
- The mctl-api chart has no generic extra-env hook: `envFromSecret` and
  `envFromExtraSecret` are both already taken (`mctl-api-secrets`,
  `mctl-api-events`), and the usage-writer precedent needed a paired chart
  change in mctlhq/mctl-api (`feat(helm): optional usageWriterTokenSecret`).
  So the issue's "no mctl-api code change" non-goal and its "follow the
  usageWriter precedent" instruction cannot both hold for the env injection.
  Resolution taken here: land everything gitops can own, render
  `surfaceTelegramTokenSecret` under the gate, and record the chart value as
  owner step 0. Helm ignores an unknown value, so the line is inert — and
  therefore the mctl-api gate must not be flipped before that value exists.
  The exact key name/shape (`surfaceTelegramTokenSecret` vs a generic
  `surfaceTokenSecrets` map) is for the mctl-api reviewer to settle.
- `MCTL_API_BASE_URL` is left unset so the code default `https://api.mctl.ai`
  applies, which means egress and a public TLS hop for an in-cluster call.
  An in-cluster `http://mctl-api.mctl-api.svc.cluster.local:8080` would avoid
  both but changes the Host/TLS assumptions of the adapter; deferred to the
  operator check on #443.
- Whether the `workContext` block in `base-service` should carry a
  surface-neutral name for reuse by other tenant services. Kept as
  `workContext` here because that is the feature's name in mctl-telegram's
  own config, and the token env var is a values key rather than a literal.
