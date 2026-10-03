# Design: issue-421-feat-helm-deliver-mctl-surface-telegram

## Current state

### How the token is consumed

`internal/auth/oidc.go:278-285` declares the surface token registry:

```go
var surfaceTokenEnv = map[string]string{
	"telegram": "MCTL_SURFACE_TELEGRAM_TOKEN",
	"portal":   "MCTL_SURFACE_PORTAL_TOKEN",
}
const minSurfaceTokenLen = 32
```

`surfaceTokens()` (`internal/auth/oidc.go:420`) reads each variable once, at
`Middleware()` construction (`oidc.go:500`), and drops any token that is empty,
under 32 bytes, equal to `MCTL_AGENT_SERVICE_TOKEN`, or shared with another
surface. An absent variable is therefore not an error: the surface simply has
no principal, and every bearer presented as that surface falls through to a
401. `usageWriterToken()` (`oidc.go:387`) applies the same shape to
`MCTL_USAGE_WRITER_TOKEN`. Nothing in `internal/auth` needs to change.

### How the chart delivers secrets today

`helm/templates/deployment.yaml` has four distinct delivery shapes:

- `envFromSecret` / `envFromExtraSecret` (lines 30-38) — bulk `secretRef`
  envFrom, used for the big `mctl-api-env` Secret.
- `gitopsSSHSecret`, `githubAppTokenSecret`, `postgresCA.secretName` (lines
  126-201) — file mounts, chosen deliberately where the value rotates in place.
- `usagePricingConfigMap` (lines 67-74, 202-223) — optional ConfigMap volume.
- `usageWriterTokenSecret` (lines 56-66) — the pattern this issue mirrors:

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

`helm/values.yaml:107-111` documents it and defaults it to `""`. There is no
key-name value: the Secret key is hardcoded and equals the env var name.

### What gitops already ships

`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-surface-telegram.yaml`
renders, only when `surfaceTelegramToken.enabled` is true, an ExternalSecret
whose target Secret is `mctl-api-surface-telegram` with exactly one entry:

```yaml
data:
  - secretKey: MCTL_SURFACE_TELEGRAM_TOKEN
    remoteRef:
      key: platform/mctl-api/surface-tokens
      property: telegram-token
```

So **the Secret key is `MCTL_SURFACE_TELEGRAM_TOKEN`**, read from the template,
not guessed. `mctl-api.yaml:236-246` passes `surfaceTelegramTokenSecret:
mctl-api-surface-telegram` behind the same flag, with an inline comment saying
the chart must grow the value. `bootstrap/values.yaml:210-225` keeps
`surfaceTelegramToken.enabled: false` and names this work as owner step 0.

### Test harness

`helm/render_test.go` shells out to the real `helm` binary
(`renderDeployment()`, line 86), unmarshals the deployment with `gopkg.in/yaml.v3`
into local structs, and asserts structurally. Its `envVar` struct (lines 18-21)
carries only `name` and `value`, so a `valueFrom` env currently round-trips with
an empty `Value` and no way to see the `secretKeyRef`. `requireHelm()` skips
locally when `helm` is absent and fails in CI.

## Proposed solution

Three files change, all under `helm/`. No Go source outside the test file, no
gitops change.

### 1. `helm/values.yaml`

Add, immediately after the `usageWriterTokenSecret` block (so the two optional
token Secrets read as a pair):

```yaml
# Optional: Secret holding MCTL_SURFACE_TELEGRAM_TOKEN, the bearer token of
# the surface:telegram principal (mctlhq/mctl-telegram#443). mctl-api
# authenticates it in internal/auth/oidc.go (surfaceTokenEnv,
# minSurfaceTokenLen = 32); it may only speak for the telegram surface. The
# key inside the Secret is MCTL_SURFACE_TELEGRAM_TOKEN, which is what the
# mctl-gitops ExternalSecret mctl-api-surface-telegram produces. The
# reference is optional, so an absent Secret leaves the principal disabled
# rather than failing the pod.
surfaceTelegramTokenSecret: ""
```

No `surfaceTelegramTokenKey`. The usage-writer pattern has none, the issue says
to mirror it exactly, and the ExternalSecret's `secretKey` is fixed in gitops —
a second knob would be an unexercised branch whose only effect is a way to get
it wrong.

### 2. `helm/templates/deployment.yaml`

Insert directly after the `usageWriterTokenSecret` block (after line 66), before
the `usagePricingConfigMap` block:

```yaml
{{- if .Values.surfaceTelegramTokenSecret }}
# Optional on purpose, same as the usage writer above: the chart ships
# before mctl-gitops flips surfaceTelegramToken.enabled, so the Secret may
# not exist yet. A missing Secret leaves the surface:telegram principal
# disabled (relay calls 401) instead of holding the pod in
# CreateContainerConfigError. The key matches the ExternalSecret
# mctl-api-surface-telegram's secretKey.
- name: MCTL_SURFACE_TELEGRAM_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.surfaceTelegramTokenSecret }}
      key: MCTL_SURFACE_TELEGRAM_TOKEN
      optional: true
{{- end }}
```

(Indented to the surrounding 12-space env-item level in the real file.)

Placement matters for the byte-identity requirement only in that the block must
be wholly inside an `{{- if }}` guard whose default is falsy — which it is,
since `values.yaml` defaults the key to `""`. Helm's `{{- if }}` with a leading
chomp emits nothing at all when false, so the default and empty renders stay
byte-identical to today's.

`optional: true` is the load-bearing detail. Without it, kubelet fails the
container with `CreateContainerConfigError` when the Secret is absent — the
control plane down over a principal that is meant to degrade. With it, the
variable is simply unset, `surfaceTokens()` skips the telegram entry, and the
rest of mctl-api is unaffected. This is the same reasoning already written into
the usage-writer and usage-pricing comments.

### 3. `helm/render_test.go`

The struct set needs one addition so `valueFrom` is visible:

```go
type secretKeyRef struct {
	Name     string `yaml:"name"`
	Key      string `yaml:"key"`
	Optional bool   `yaml:"optional"`
}

type envVarSource struct {
	SecretKeyRef *secretKeyRef `yaml:"secretKeyRef"`
}
```

and `envVar` gains `ValueFrom *envVarSource \`yaml:"valueFrom"\``. That is
additive: existing assertions read `Name`/`Value` and are unaffected, because
plain value envs unmarshal `ValueFrom` as nil.

Then three tests, named for the value not the pattern:

- `TestDeploymentDefaultRenderHasNoSurfaceTelegramToken` — default render,
  `findEnv(c, "MCTL_SURFACE_TELEGRAM_TOKEN")` must return false.
- `TestDeploymentEmptySurfaceTelegramTokenRendersUnchanged` — mirrors
  `TestDeploymentEmptyUsagePricingRendersUnchanged` (line 216): compare the raw
  bytes of the default render against `--set surfaceTelegramTokenSecret=` and
  require `bytes.Equal`. This is the acceptance criterion "with the gitops flag
  still false, the rendered production manifest is unchanged", expressed as a
  test rather than a claim.
- `TestDeploymentRendersSurfaceTelegramTokenEnv` — `--set
  surfaceTelegramTokenSecret=mctl-api-surface-telegram`, then assert: exactly
  one env entry with that name (count the matches in `c.Env`, do not just take
  the first), `ValueFrom.SecretKeyRef` non-nil, `.Name ==
  "mctl-api-surface-telegram"`, `.Key == "MCTL_SURFACE_TELEGRAM_TOKEN"`,
  `.Optional == true`, and `env.Value == ""` (no literal leaked into the
  manifest). Deleting the template block fails the `!ok` fatal; changing the
  key fails the key assertion.

Additionally extend `TestHelmLintCleanWithAndWithoutUsagePricing`'s `cases`
slice with `{"--set", "surfaceTelegramTokenSecret=mctl-api-surface-telegram"}`
so lint covers the new branch too. The test name stays as-is to keep the diff
minimal, or is renamed to `TestHelmLintCleanAcrossOptionalValues` — either is
acceptable; prefer the rename since the case list is no longer about usage
pricing alone.

A fourth, optional test asserts that setting both `usageWriterTokenSecret` and
`surfaceTelegramTokenSecret` renders both env entries — cheap coverage of the
"neither suppresses the other" criterion and of the usage-writer block, which
has no render test today.

## Alternatives

**Deliver the token through `envFromSecret`.** Add
`MCTL_SURFACE_TELEGRAM_TOKEN` to the big `mctl-api-env` Secret and let the
existing `secretRef` envFrom carry it. Dropped: gitops deliberately gave this
token its own ExternalSecret so a missing Vault property degrades one principal
instead of taking `DB_PASSWORD` down with it (stated verbatim in
`mctl-api-surface-telegram.yaml`'s header). Folding it into the bulk Secret
throws away exactly the isolation that was designed for, and would require a
gitops change this proposal is out of scope for.

**Add a third `envFromExtraSecret`-style bulk reference pointing at
`mctl-api-surface-telegram`.** Dropped: `envFrom` `secretRef` has no
`optional` in the same ergonomic sense used here (it does support `optional`,
but it imports every key, so the Secret's shape silently becomes part of the
pod's env contract), and it does not satisfy the issue's "exactly one env entry
with the right secret name and key" test requirement. `secretKeyRef` names the
one variable it delivers, which is auditable in the rendered manifest.

**Generic `surfaceTokenSecrets` map keyed by surface name.** A
`range $surface, $secret := .Values.surfaceTokenSecrets` block would cover
telegram and portal in one shape. Dropped for now: only one surface has a
gitops ExternalSecret, the env-var name would have to be reconstructed by
`upper`-casing the key (`printf "MCTL_SURFACE_%s_TOKEN"`), which is a template
computing an identifier that `internal/auth` holds as a literal map — a drift
risk with no current payoff. Revisit if/when `MCTL_SURFACE_PORTAL_TOKEN` gets
its own Secret; the two explicit blocks refactor into a map trivially at that
point.

**File mount, like `githubAppTokenSecret`.** Dropped: that mount exists because
GitHub installation tokens are re-minted every 30 minutes and an env var would
pin an expired value (comment at `deployment.yaml:169-175`). The surface token
is a long-lived Vault-held secret whose rotation already implies a pod roll, and
`internal/auth` reads it with `os.Getenv`, not from a file — a file mount would
require the `internal/auth` change this issue explicitly excludes.

## Platform impact

**Migrations.** None. No database, no API surface, no MCP tool count change
(`internal/mcp/server.go` untouched, so `server_test.go`'s tool-count
expectation is unaffected).

**Backward compatibility.** Strictly additive. The new value defaults to `""`,
the template block is fully guarded, and
`TestDeploymentEmptySurfaceTelegramTokenRendersUnchanged` pins byte-identity of
the default render. Existing deployments — including production, where
`surfaceTelegramToken.enabled` is still `false` — render exactly the manifest
they render today, so no pod restarts and no ArgoCD diff result from merging
this.

**Resource impact.** One additional env var on the container when enabled.
Nil.

**Risks and mitigations.**

- *Wrong Secret key.* If the chart hardcoded a key the ExternalSecret does not
  produce, the pod would start cleanly with the variable unset and the only
  symptom would be 401s at relay time — a silent failure. Mitigated by reading
  the key from `mctl-api-surface-telegram.yaml` (`secretKey:
  MCTL_SURFACE_TELEGRAM_TOKEN`) rather than guessing, and by asserting the
  literal in `render_test.go`. If gitops ever changes that `secretKey`, the
  chart test will not catch it — the two repos are only coupled by this
  constant; noted in the task list as a comment to leave in both places.
- *Non-optional reference.* Omitting `optional: true` would turn a not-yet-synced
  Secret into a pod that cannot start. Mitigated by the explicit assertion on
  `Optional == true` in the set-case test.
- *Token leaking into a rendered manifest.* `secretKeyRef` never inlines the
  value; the test additionally asserts `env.Value == ""`. The rendered
  deployment in gitops contains only the Secret's name.
- *CI without `helm`.* `requireHelm()` skips locally but `t.Fatalf`s when `CI`
  is set, so the new assertions cannot silently no-op in the pipeline.
- *Ordering with mctl-gitops.* This change is inert until owner steps 1 (Vault
  write) and 2 (`enabled: true`) happen in mctl-gitops, which the owner gates on
  mctlhq/mctl-telegram#443. After merge, `bootstrap/values.yaml`'s "Not done
  yet: step 0 has not landed" note becomes stale — a follow-up gitops comment
  update is the owner's, not this proposal's.
