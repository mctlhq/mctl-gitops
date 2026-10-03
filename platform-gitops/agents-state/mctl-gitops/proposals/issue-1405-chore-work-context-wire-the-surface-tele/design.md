# Design: issue-1405-chore-work-context-wire-the-surface-tele

## Current state

**Two different delivery paths, one repo.**

mctl-api is a platform application declared by the bootstrap chart.
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` is an
ArgoCD `Application` whose Helm values are written inline; the
`ExternalSecret` objects that feed it live beside it in
`mctl-api-secrets.yaml` (four of them: `mctl-api-secrets`, `mctl-api-ghcr`,
`mctl-api-github-app`, `mctl-api-events`) and in the flag-gated
`mctl-api-usage-writer.yaml`. Because these are Helm templates of the
bootstrap chart, a flag in `platform-gitops/bootstrap/values.yaml` can gate
them: `mctl-api-usage-writer.yaml` is one file whose entire body sits inside
`{{- if .Values.usageWriter.enabled }}`, and `mctl-api.yaml` adds
`usageWriterTokenSecret: mctl-api-usage-writer` inside the same gate. That
file also explains why it is a separate `ExternalSecret` and a separate file:
ESO fails the whole `ExternalSecret` when a single `remoteRef` does not
resolve, so a key with a shaky Vault property must not sit next to
`DB_PASSWORD`.

The mctl-api chart itself lives in `mctlhq/mctl-api` under `helm/`. Read at
`main`, its `envFrom` offers exactly two hooks — `envFromSecret` and
`envFromExtraSecret` — and both are already spoken for in `mctl-api.yaml`
(`mctl-api-secrets` and `mctl-api-events`). Its `env:` map renders literal
values only (`value: {{ $value | quote }}`); there is no `valueFrom`
mechanism, no `extraEnv`, and no generic extra-`envFrom` list. The one
credential injected outside those two secrets is the usage-writer token,
which got its own chart value:

```yaml
{{- if .Values.usageWriterTokenSecret }}
- name: MCTL_USAGE_WRITER_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.usageWriterTokenSecret }}
      key: MCTL_USAGE_WRITER_TOKEN
      optional: true
{{- end }}
```

added by the mctl-api commit `feat(helm): optional usageWriterTokenSecret for
MCTL_USAGE_WRITER_TOKEN`. So the usageWriter precedent is a **pair**: a chart
value in mctl-api plus the gitops gate here.

mctl-api's consumer of the token is `internal/auth/oidc.go`: `surfaceTokenEnv`
maps `telegram` -> `MCTL_SURFACE_TELEGRAM_TOKEN` and `portal` ->
`MCTL_SURFACE_PORTAL_TOKEN`, `minSurfaceTokenLen` is 32, and the principal is
`surface:telegram` — no tenant, no admin, no relay authority beyond its own
surface.

mctl-telegram is a tenant service. The `apps` ApplicationSet
(`platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml`)
walks `platform-gitops/services/*/*` and renders each directory as
`helm template <team>-<service> platform-gitops/helm-charts/base-service -f
$values/<dir>/values.yaml`. The values file is a **plain values file**, not a
template, so a gate for a tenant service can only be a values key that the
`base-service` chart itself interprets. The chart already does exactly this
once: `otel.enabled` in `platform-gitops/helm-charts/base-service/values.yaml`
makes `base-service.env` (in `templates/_helpers.tpl`) emit four OTEL
variables, skipping any key the service set explicitly under `env:` or
`envValueFrom:`; both `templates/deployment.yaml:121` and
`templates/rollout.yaml:107` carry their own copy of the guard
`{{- if or .Values.env .Values.envValueFrom .Values.otel.enabled }}`, which
is precisely the two-copies trap `tests/test_base_service_otel_env.py` exists
to catch. A second generic gate exists for whole manifests:
`templates/extra-objects.yaml` honours a per-object `renderIf` template
string and renders the object only when it evaluates to exactly `"true"` —
the labs values file already uses it twice for the demo-reviewer CronJobs.
There is no `values.schema.json`, so an unknown top-level values key is
simply ignored by Helm.

`platform-gitops/services/labs/mctl-telegram/values.yaml` today: `image.tag
"0.69.0"`, `strategy.type: Recreate` (MTProto auth keys must never be opened
by overlapping pods), a large literal `env:` map, `envValueFrom.POD_NAME`, an
`envFrom` list of six `secretRef`s, `dbSecret`, and `extraExternalSecrets`
for `tg-api` / `encryption` / `oauth` / `login` / `demo`, each with
`store: vault-backend`, `storeKind: ClusterSecretStore` and a `remoteKey`
in the `secret/data/platform/...` spelling. Bootstrap's ExternalSecrets use
the same `vault-backend` ClusterSecretStore but the bare
`platform/...` spelling (`key: platform/mctl-agents`). Both forms are live
against the same store, so the same physical Vault path is addressed two
ways depending on which file it is written in — a detail this change has to
get right, because the whole point is one property.

CI, all in `.github/workflows/validate-manifests.yml` (no path filter; helm
v3.16.4, kubeconform 0.8.0): every tenant values file is rendered and
kubeconform'd in a loop; the usage-writer step renders bootstrap twice with
`--set usageWriter.enabled=false|true` and asserts each marker is present in
the on-render and absent from the off-render; a dozen `python3 tests/*.py`
steps run plain scripts (no pytest anywhere in this repo — the convention is
a module-level `failures` list, a `check(cond, msg)` helper and
`sys.exit(1)`), with `pyyaml` pip-installed inline. `.github/workflows/yamllint.yml`
lints `platform-gitops/**` and names, one by one, the files whose first line
is a Go-template directive — `mctl-api-usage-writer.yaml` is on that list
because its whole body sits inside its gate.

## Proposed solution

Two gates, one Vault property, four new/edited files per side, plus CI.

### 1. mctl-api side (bootstrap chart)

**New file** `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-surface-telegram.yaml`,
a direct sibling of `mctl-api-usage-writer.yaml`: entire body inside
`{{- if (default dict .Values.surfaceTelegramToken).enabled }}`, rendering
one `ExternalSecret` named `mctl-api-surface-telegram` in namespace
`mctl-api`, `refreshInterval: 1h`, `ClusterSecretStore vault-backend`,
`target.name: mctl-api-surface-telegram`, `creationPolicy: Owner`, and a
single `data` entry: `secretKey: MCTL_SURFACE_TELEGRAM_TOKEN`, `remoteRef.key:
platform/mctl-api/surface-tokens`, `remoteRef.property: telegram-token`. Its
own ExternalSecret and its own file for the reason `mctl-api-usage-writer.yaml`
states: an unresolved property must disable the surface principal, not take
`DB_PASSWORD` with it.

The `(default dict ...)` idiom rather than a bare `.Values.surfaceTelegramToken.enabled`
is deliberate: it keeps the template renderable when the key is absent
entirely, which is what lets CI compare the gate-off render against a render
whose values file never mentioned the key (test T1 below).

**Edited** `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`:
inside the same gate, next to the existing `usageWriterTokenSecret` block,
add `surfaceTelegramTokenSecret: mctl-api-surface-telegram` with a comment
naming the mctl-api chart prerequisite. Adding an env entry changes the
Deployment spec, so the rollout happens by itself — no `ROLLOUT_MARKER` bump
is needed for the flip (a later token *rotation* is different: the value
arrives through `secretKeyRef`, captured at container start, so rotating it
needs a restart of both pods).

**Edited** `platform-gitops/bootstrap/values.yaml`: a new top-level
`surfaceTelegramToken: { enabled: false }` with the owner steps written above
it in the exact shape `usageWriter` uses — Vault write first (`vault kv patch
-method=rw`, never `put`, at least 32 bytes per `minSurfaceTokenLen`, no
trailing newline, distinct from `MCTL_AGENT_SERVICE_TOKEN` and the other
surface tokens), then the mctl-api chart value, then this flag.

**Edited** `.github/workflows/yamllint.yml`: add the new template to the
`ignore:` list, for the same reason `mctl-api-usage-writer.yaml` is there.

The Vault key/property are literals in the template, exactly as the
usage-writer's `platform/mctl-agents` / `usage-writer-token` are, rather than
values keys: fewer moving parts, and the "same property" claim then lives in
two files whose agreement a test can assert.

### 2. mctl-telegram side (base-service chart + labs values)

The gate must be a values key the chart interprets, so `base-service` gains a
`workContext` block modelled on `otel`:

```yaml
# platform-gitops/helm-charts/base-service/values.yaml
workContext:
  enabled: false            # wiring gate; off = render unchanged
  featureEnabled: false     # -> WORK_CONTEXT_ENABLED, the separate flag
  tenant: ""                # -> MCTL_WORK_ITEM_TENANT
  apiBaseUrl: ""            # -> MCTL_API_BASE_URL, omitted while empty
  tokenEnvName: MCTL_SURFACE_TELEGRAM_TOKEN
  tokenVaultKey: ""         # e.g. secret/data/platform/mctl-api/surface-tokens
  tokenVaultProperty: ""    # e.g. telegram-token
  tokenSecretName: ""       # target Secret; defaults to <fullname>-work-context
  store: vault-backend
  storeKind: ClusterSecretStore
  refreshInterval: 1h
```

**New template** `templates/externalsecret-work-context.yaml`: whole body
gated on `workContext.enabled`, `fail`ing with a named message if
`tokenVaultKey` or `tokenVaultProperty` is empty (the chart already uses
`fail` this way in `externalsecret-extra.yaml` and `extra-objects.yaml`),
otherwise one `ExternalSecret` named `<fullname>-work-context` with its own
target Secret, its `store`/`storeKind` resolved through the existing
`base-service.secretStoreRef` helper, and `conversionStrategy` /
`decodingStrategy` / `metadataPolicy` spelled out — the chart's standing
convention, so git matches live under `ServerSideApply` +
`RespectIgnoreDifferences` (#789).

**Edited** `templates/_helpers.tpl`, `base-service.env`: after the `otel`
block and under `workContext.enabled`, emit — each skipped if the service
already set that name under `env:` or `envValueFrom:`, the same precedence
rule `otel` uses —

- `WORK_CONTEXT_ENABLED`, from `workContext.featureEnabled` (quoted
  `"true"` / `"false"`);
- `MCTL_WORK_ITEM_TENANT`, from `workContext.tenant` (may be empty);
- `MCTL_API_BASE_URL`, only when `workContext.apiBaseUrl` is non-empty;
- `<tokenEnvName>` as a `valueFrom.secretKeyRef` on the target Secret, key
  `<tokenEnvName>`, `optional: true`.

`optional: true` is the same choice mctl-api's chart made for the
usage-writer, and here it separates two failure modes cleanly: a Secret that
has not synced yet leaves the variable absent, and mctl-telegram only
*refuses to start* on an absent token when `WORK_CONTEXT_ENABLED` is already
true. That is exactly why the two flags are separate and why the owner flips
the wiring first, confirms the Secret, and flips the feature second — on a
service whose `strategy.type` is `Recreate`, a crash-looping pod is downtime,
not a degraded replica.

**Edited** `templates/deployment.yaml` and `templates/rollout.yaml`: extend
both copies of the env guard to
`{{- if or .Values.env .Values.envValueFrom .Values.otel.enabled (default dict .Values.workContext).enabled }}`,
so a service with no `env:` map still gets the block. Two files, one change —
the miss `tests/test_base_service_otel_env.py` was written for.

**Edited** `platform-gitops/services/labs/mctl-telegram/values.yaml`: add the
`workContext` block with `enabled: false`, `featureEnabled: false`,
`tenant: ""`, `tokenVaultKey: secret/data/platform/mctl-api/surface-tokens`,
`tokenVaultProperty: telegram-token`, and the owner steps as comments
directly above it. Nothing else in that file moves: no `envFrom` entry and no
`extraExternalSecrets` entry is added, because the token arrives through the
chart's `secretKeyRef` and an `envFrom: secretRef` without `optional` would
block startup on a Secret that has not synced.

### 3. The single property, asserted

Written twice in two spellings that address one Vault path:

| file | spelling | property |
| --- | --- | --- |
| `bootstrap/.../mctl-api-surface-telegram.yaml` | `platform/mctl-api/surface-tokens` | `telegram-token` |
| `services/labs/mctl-telegram/values.yaml` | `secret/data/platform/mctl-api/surface-tokens` | `telegram-token` |

A test normalises the `secret/data/` prefix and asserts the two are equal, so
the "one value, nothing to keep in step" guarantee is a CI property rather
than a comment.

### 4. CI

Following the usage-writer step at `.github/workflows/validate-manifests.yml`
and the golden-render precedent in `tests/test_otel_collector_backends_render.py`:

- a bootstrap both-states shell step (`--set
  surfaceTelegramToken.enabled=false|true`), `kubeconform -strict` on the
  on-render, and present-on/absent-off assertions for the markers `name:
  mctl-api-surface-telegram`, `surfaceTelegramTokenSecret:
  mctl-api-surface-telegram`, `property: telegram-token`;
- a new plain-script test `tests/test_base_service_work_context_env.py` in the
  repo's existing style (`ROOT = pathlib.Path(__file__).resolve().parents[1]`,
  `failures` + `check` + `sys.exit(1)`, `helm template ... -f <values>` via
  `subprocess.run`, `pyyaml` installed inline by the step).

The gate-off baseline is obtained without any git plumbing: render the real
`labs/mctl-telegram/values.yaml` as committed, render a copy with the
`workContext` key deleted, and compare. Byte-equality then *means* "the gate
off is indistinguishable from a values file that never mentioned the
feature", which is the acceptance criterion, and it cannot rot the way a
committed golden file can.

## Alternatives

1. **Add `MCTL_SURFACE_TELEGRAM_TOKEN` to an existing ExternalSecret**
   (`mctl-api-events` for mctl-api, `labs-mctl-telegram-oauth` for
   mctl-telegram). One-line change, no new files, no chart work. Dropped: ESO
   0.10.7 fails the entire `ExternalSecret` when one `remoteRef` does not
   resolve, so an unwritten property would take `GITHUB_WEBHOOK_SECRET` and
   `EVENTS_VALKEY_PASSWORD` — or `TELEGRAM_OIDC_CLIENT_SECRET` — down with
   it. That is the failure mode `mctl-api-secrets.yaml` documents at length
   and the issue's third acceptance criterion forbids.

2. **A second ExternalSecret with `target.creationPolicy: Merge` into
   `mctl-api-secrets`**, which would inject the variable through the existing
   `envFromSecret` with no chart change at all. There is a precedent for
   `Merge` in this repo (`platform-gitops/argocd/templates/argocd-github-oauth.yaml`).
   Dropped: that precedent merges into a Secret owned by the ArgoCD Helm
   release, whereas `mctl-api-secrets` is owned by another ExternalSecret with
   `creationPolicy: Owner`, which rewrites the Secret's data from its own
   spec on every refresh. Two ESO controllers contending for one Secret is a
   key that disappears roughly hourly — a failure that looks like an
   intermittent 401 from one surface and is very expensive to diagnose. Not
   worth avoiding a ten-line chart value.

3. **Ship the mctl-telegram wiring as `extraObjects` + `renderIf` and leave
   the env out**, using only mechanisms `base-service` has today and touching
   no chart file. Dropped: `renderIf` can gate the `ExternalSecret`, but
   `env:` is a flat literal map with no gate, so `WORK_CONTEXT_ENABLED` and
   `MCTL_WORK_ITEM_TENANT` would either always render (breaking the
   byte-identical requirement) or have to be authored at flip time (defeating
   "committed but inert", which is the point of the issue). A generic
   per-entry `enabled` on `envFrom`/`extraExternalSecrets` was also
   considered and dropped: it widens a chart every tenant service renders
   from, to gate one feature.

4. **Point mctl-api's `MCTL_API_BASE_URL` consumer at the in-cluster Service**
   (`http://mctl-api.mctl-api.svc.cluster.local:8080`) instead of
   `https://api.mctl.ai`, avoiding egress entirely. Not dropped so much as
   deferred: it changes the Host header and drops TLS for a bearer-token call,
   and reachability is explicitly an operator check on mctl-telegram#443. The
   values key exists (`workContext.apiBaseUrl`) and is empty, so this is a
   one-line follow-up if the operator check says egress is the problem.

## Platform impact

**Migrations / backward compatibility.** None. With both gates off the
rendered output of every application in the repo is unchanged, which is
asserted rather than asserted-by-eye: the bootstrap both-states step covers
`admins-mctl-api`, and the new test covers `base-service` for
`labs/mctl-telegram` on both workload kinds. The `base-service` chart change
touches a chart every tenant service renders from, so CI's existing
render-every-service loop is the second net; the `workContext` defaults are
off/empty so the new helper branch is dead code for every other service.
`argocd.argoproj.io/manifest-generate-paths` on the apps ApplicationSet
already includes `/platform-gitops/helm-charts/base-service`, so the chart
edit does refresh the generated apps — expected and harmless while the gate
is off.

**Resource impact.** Two `ExternalSecret` objects and two Secrets when both
gates are on; no pods, no CPU or memory request changes. `refreshInterval:
1h` on both, matching every neighbouring ExternalSecret.

**Risks and mitigations.**

- *The mctl-api chart value does not exist yet.* Helm silently ignores an
  unknown value, so flipping `surfaceTelegramToken.enabled` before
  mctlhq/mctl-api ships `surfaceTelegramTokenSecret` would render the
  ExternalSecret and sync the Secret while mctl-api never reads it — a
  `surface:telegram` 401 with everything looking green. Mitigation: it is
  owner step 0, written above the flag, and the CI marker check proves only
  that gitops passes the value. The gate-off default means the window is
  harmless until someone flips it.
- *Unwritten Vault property.* The gated ExternalSecret goes Degraded and
  `ArgoCDApplicationDegraded` fires after 30m — which is exactly why the
  wiring is flag-gated rather than "optional", the reasoning
  `bootstrap/values.yaml` already records for `usageWriter`. Mitigation:
  Vault write is owner step 1.
- *Trailing newline / too-short token.* `mctl-api-secrets.yaml` documents a
  real incident where `security find-generic-password -w` added a byte and
  ESO then served `Bearer <token>\n`. `minSurfaceTokenLen` is 32 and mctl-api
  refuses a surface token equal to `MCTL_AGENT_SERVICE_TOKEN`. Mitigation:
  the owner step spells out `printf '%s' ... | vault kv patch -method=rw` and
  a `t == t.strip()` check.
- *Ordering on a `Recreate` service.* mctl-telegram refuses to start with
  `WORK_CONTEXT_ENABLED=true` and no token or tenant, and `strategy.type:
  Recreate` means the old pod is gone before the new one starts. Mitigation:
  the documented flip order is wiring on -> confirm the Secret synced ->
  `featureEnabled: true`, and `optional: true` keeps step 3 non-fatal on its
  own.
- *Rotation.* Both injections are `secretKeyRef` env, captured at container
  start, so rotating the property in Vault requires restarting mctl-api and
  mctl-telegram. Recorded next to the flags; a file mount (the
  `mctl-api-github-app` pattern) would be the fix if the token ever gets a
  short lifetime, which it does not.
- *yamllint.* A new bootstrap template whose first line is `{{- if ... }}`
  fails the relaxed yamllint job unless it is named in that workflow's
  `ignore:` list. Mitigation: it is a task, not a footnote.
