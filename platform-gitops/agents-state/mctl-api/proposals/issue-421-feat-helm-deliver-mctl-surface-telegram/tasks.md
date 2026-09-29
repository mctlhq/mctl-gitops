# Tasks: issue-421-feat-helm-deliver-mctl-surface-telegram

- [ ] 1. Confirm the Secret key from the gitops ExternalSecret before writing
  any template — read
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-surface-telegram.yaml`
  and use its `data[0].secretKey` verbatim. DoD: the key used in the chart is
  `MCTL_SURFACE_TELEGRAM_TOKEN`, sourced from that file, not inferred from the
  env var name.

- [ ] 2. Add `surfaceTelegramTokenSecret: ""` to `helm/values.yaml` (depends on
  1) — placed immediately after the `usageWriterTokenSecret` block at line 111,
  with a comment in the same voice: what the principal is
  (`surface:telegram`, mctlhq/mctl-telegram#443), where mctl-api reads it
  (`internal/auth/oidc.go`, `surfaceTokenEnv`, `minSurfaceTokenLen = 32`), which
  Secret key is expected, and why the reference is optional. DoD: the value
  exists, defaults to empty, and the comment names the ExternalSecret
  `mctl-api-surface-telegram`. No `surfaceTelegramTokenKey` is added — the
  usage-writer pattern has none.

- [ ] 3. Add the guarded env block to `helm/templates/deployment.yaml` (depends
  on 2) — after the `usageWriterTokenSecret` block (line 66) and before the
  `usagePricingConfigMap` block, at the surrounding env-item indentation:
  `{{- if .Values.surfaceTelegramTokenSecret }}` emitting `MCTL_SURFACE_TELEGRAM_TOKEN`
  via `valueFrom.secretKeyRef` with `name: {{ .Values.surfaceTelegramTokenSecret }}`,
  `key: MCTL_SURFACE_TELEGRAM_TOKEN`, `optional: true`, plus a comment
  explaining the optional semantics and the gitops key coupling. DoD:
  `helm template mctl-api helm/ --show-only templates/deployment.yaml` emits
  nothing new by default and emits the env entry under `--set
  surfaceTelegramTokenSecret=mctl-api-surface-telegram`.

- [ ] 4. Extend `helm/render_test.go`'s struct set (depends on 3) — add
  `secretKeyRef` (`name`, `key`, `optional`) and `envVarSource`
  (`secretKeyRef`) types and a `ValueFrom *envVarSource \`yaml:"valueFrom"\``
  field on `envVar`. DoD: additive only; every existing test still compiles and
  passes unchanged.

- [ ] 5. Write the three required render tests (depends on 4). DoD: see T1-T3
  below; all pass with `helm` on PATH.

- [ ] 6. Add the new branch to the helm-lint case list (depends on 3) — append
  `{"--set", "surfaceTelegramTokenSecret=mctl-api-surface-telegram"}` to the
  `cases` slice in `TestHelmLintCleanWithAndWithoutUsagePricing`, and rename it
  to `TestHelmLintCleanAcrossOptionalValues` since it no longer covers usage
  pricing alone. DoD: lint passes for the default, usage-pricing and
  surface-telegram configurations.

- [ ] 7. (Optional, recommended) Add a both-set test covering
  `usageWriterTokenSecret` and `surfaceTelegramTokenSecret` together (depends on
  5). DoD: both env entries render with their own Secret names and keys; this
  also gives the previously untested usage-writer block its first assertion.

- [ ] 8. Run the repo gates (depends on 5, 6) — `go fmt ./...`, `go vet ./...`,
  `golangci-lint run`, `go test ./...` including `go test ./helm/...`. DoD: all
  clean; no change to `internal/mcp/server.go`, so the MCP tool-count
  expectation in `server_test.go` is untouched.

- [ ] 9. Verify the production no-op by hand (depends on 3) — render the chart
  with the values mctl-gitops passes today (`surfaceTelegramToken.enabled:
  false`, so no `surfaceTelegramTokenSecret` key at all) and diff against the
  pre-change render. DoD: zero-byte diff, recorded in the PR description.

- [ ] 10. Write the PR description (depends on 8, 9) — state that this lands
  owner step 0 from mctl-gitops `bootstrap/values.yaml:210-225`, that the flag
  stays `false` and this repo makes no gitops change, and that the follow-up is
  the owner's Vault write plus `enabled: true` gated on mctlhq/mctl-telegram#443.
  DoD: PR links issue #421 and mctlhq/mctl-telegram#443 and includes the no-op
  diff evidence from task 9.

## Tests

- [ ] T1. `TestDeploymentDefaultRenderHasNoSurfaceTelegramToken` — default
  render; `findEnv(c, "MCTL_SURFACE_TELEGRAM_TOKEN")` returns `ok == false`.
- [ ] T2. `TestDeploymentEmptySurfaceTelegramTokenRendersUnchanged` — raw bytes
  of the default render and of `--set surfaceTelegramTokenSecret=` compare
  equal with `bytes.Equal`, mirroring
  `TestDeploymentEmptyUsagePricingRendersUnchanged`.
- [ ] T3. `TestDeploymentRendersSurfaceTelegramTokenEnv` — with `--set
  surfaceTelegramTokenSecret=mctl-api-surface-telegram`: exactly one env entry
  named `MCTL_SURFACE_TELEGRAM_TOKEN` (count matches across `c.Env`, do not
  take the first and stop), `ValueFrom.SecretKeyRef` non-nil, `.Name ==
  "mctl-api-surface-telegram"`, `.Key == "MCTL_SURFACE_TELEGRAM_TOKEN"`,
  `.Optional == true`, and `env.Value == ""`.
- [ ] T4. Negative control, run manually once and not committed: delete the
  template block from `helm/templates/deployment.yaml` and confirm T3 fails.
  Restore the block. This is the issue's explicit acceptance requirement that
  the set-case test fails if the block is removed.
- [ ] T5. `TestHelmLintCleanAcrossOptionalValues` — `helm lint .` clean for
  default, `usagePricingConfigMap` set, and `surfaceTelegramTokenSecret` set.
- [ ] T6. (Optional, with task 7) both-set test: `usageWriterTokenSecret` and
  `surfaceTelegramTokenSecret` each render their own `secretKeyRef` env entry.
- [ ] T7. Regression: `go test ./internal/auth/...` still passes untouched —
  proof that nothing in `internal/auth` was modified.

## Rollback

The change is additive and inert by default, so the blast radius is limited to
teams that set the new value.

1. **Before the gitops flag flips** (the expected state at merge): nothing to
   roll back. `surfaceTelegramToken.enabled` is `false`, the value is never
   passed, and T2/task 9 prove the rendered manifest is byte-identical. Revert
   the PR if desired; no deploy is needed.
2. **After the flag flips, if the pod misbehaves**: set
   `surfaceTelegramToken.enabled: false` in mctl-gitops
   `platform-gitops/bootstrap/values.yaml`. The ExternalSecret and the
   `surfaceTelegramTokenSecret` reference both disappear, the env var is gone
   on the next roll, and `surfaceTokens()` simply omits telegram — mctl-api
   keeps serving every other principal. This is a gitops-only change and needs
   no mctl-api release.
3. **Chart-level revert**: `git revert` the mctl-api commit and redeploy. Helm
   then ignores the `surfaceTelegramTokenSecret` key mctl-gitops passes, exactly
   as it does today, returning to the pre-change behaviour without a gitops
   edit.

Because the `secretKeyRef` is `optional: true`, the worst failure mode of a
bad Secret is a disabled `surface:telegram` principal (relay calls 401), never
a pod that will not start — so no rollback path requires urgent action to keep
the control plane up.
