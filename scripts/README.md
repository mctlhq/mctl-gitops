# scripts/

One-shot recovery helpers used during platform incidents. Idempotent by
design — re-running on a healthy cluster is a no-op.

| Script | Purpose |
|---|---|
| `heal-eso-lac.sh` | Strip stale `kubectl.kubernetes.io/last-applied-configuration` annotations from ExternalSecret objects after an ESO chart version roundtrip leaves them with `apiVersion=external-secrets.io/v1` + embedded `resourceVersion`. Used 2026-05-07 during recovery from the 0.10.x → 2.x → 0.10.x roundtrip. Default is `--dry-run`; pass `--apply` to mutate. |
| `validate-gha-expression-injection.py` | CI detector (run by validate-manifests, not a recovery helper): fails when a `.github` workflow `run:` or github-script step interpolates `${{ inputs.* }}`, `github.event.*` or `github.head_ref` instead of binding it via `env:` (gitops#1809). `--selftest` proves it detects. |
| `validate-generated-app-scope.py` | CI detector (validate-manifests): expands the `apps` and `tenants` ApplicationSets over the real directories, renders base-service per service and checks each object against the resolved AppProject; also checks directory/reserved-name consistency and the inventory in `app-project-consumers.json` of files that spell the project name `apps`. Regenerate the inventory with `--print-consumers` (needs no `--bootstrap`) after an intended change; per-tenant RBAC fragments are matched by a pattern with a fixed per-file count, so tenant create and delete need no inventory change. Tests: `tests/test_generated_app_scope.py`. |
| `check-mctl-api-oidc-config.py` | CI detector (validate-manifests, zitadel-iac job): runs the image pinned in `mctl-api.yaml` with `--check-config` on the values zitadel-iac renders (`iac/tests/fixtures/mctl-api-config-check.json`, kept equal to the rendering by `tofu test`), so mctl-api's own validator judges them (gitops#2737 lesson). Fail closed; the only skip is a pin older than `MIN_CHECKER_VERSION`, with a warning. `--selftest` proves each failure path. |
| `release-config-preflight.py` | Release-path twin of the above (`bump` job of release-deploy.yaml and gitops-bump.yaml, before the tag edit): runs the NEW mctl-api image's `--check-config` on the configuration main renders today, so a rule that is stricter in the new image is refused before the bump, not after Argo rolls it (4.166.0). Not applicable to other images. Proven by `tests/test_release_config_preflight.py` (stub docker, mutants). |

Always set `KUBECONFIG` to the target cluster before running.

