# scripts/

One-shot recovery helpers used during platform incidents. Idempotent by
design — re-running on a healthy cluster is a no-op.

| Script | Purpose |
|---|---|
| `heal-eso-lac.sh` | Strip stale `kubectl.kubernetes.io/last-applied-configuration` annotations from ExternalSecret objects after an ESO chart version roundtrip leaves them with `apiVersion=external-secrets.io/v1` + embedded `resourceVersion`. Used 2026-05-07 during recovery from the 0.10.x → 2.x → 0.10.x roundtrip. Default is `--dry-run`; pass `--apply` to mutate. |
| `validate-gha-expression-injection.py` | CI detector (run by validate-manifests, not a recovery helper): fails when a `.github` workflow `run:` or github-script step interpolates `${{ inputs.* }}`, `github.event.*` or `github.head_ref` instead of binding it via `env:` (gitops#1809). `--selftest` proves it detects. |
| `validate-generated-app-scope.py` | CI detector (validate-manifests): expands the `apps` and `tenants` ApplicationSets over the real directories, renders base-service per service and checks each object against the resolved AppProject; also checks directory/reserved-name consistency and the inventory in `app-project-consumers.json` of files that spell the project name `apps`. Regenerate the inventory with `--print-consumers` (needs no `--bootstrap`) after an intended change; per-tenant RBAC fragments are matched by a pattern with a fixed per-file count, so tenant create and delete need no inventory change. Tests: `tests/test_generated_app_scope.py`. |

Always set `KUBECONFIG` to the target cluster before running.

