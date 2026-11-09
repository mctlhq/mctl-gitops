# scripts/

One-shot recovery helpers used during platform incidents. Idempotent by
design — re-running on a healthy cluster is a no-op.

| Script | Purpose |
|---|---|
| `heal-eso-lac.sh` | Strip stale `kubectl.kubernetes.io/last-applied-configuration` annotations from ExternalSecret objects after an ESO chart version roundtrip leaves them with `apiVersion=external-secrets.io/v1` + embedded `resourceVersion`. Used 2026-05-07 during recovery from the 0.10.x → 2.x → 0.10.x roundtrip. Default is `--dry-run`; pass `--apply` to mutate. |
| `validate-gha-expression-injection.py` | CI detector (run by validate-manifests, not a recovery helper): fails when a `.github` workflow `run:` or github-script step interpolates `${{ inputs.* }}`, `github.event.*` or `github.head_ref` instead of binding it via `env:` (gitops#1809). `--selftest` proves it detects. |
| `validate-generated-app-scope.py` | CI detector (validate-manifests): expands the `apps` and `tenants` ApplicationSets over the real directories, renders base-service per service and checks each object against the resolved AppProject; also checks directory/reserved-name consistency and the inventory in `app-project-consumers.json` of files that spell the project name `apps`. Regenerate the inventory with `--print-consumers` (needs no `--bootstrap`) after an intended change; per-tenant RBAC fragments are matched by a pattern with a fixed per-file count, so tenant create and delete need no inventory change. Tests: `tests/test_generated_app_scope.py`. |
| `validate-reflector-sources.py` | CI detector (validate-manifests): offline guard that no Reflector enabler or mirror marker is committed anywhere in the tree (S-A, mctl-agents#1007). Exit 0 GREEN, 1 RED, 2 UNKNOWN; reads resolved YAML/JSON keys (aliases, merge and explicit keys, multi-line scalars, JSON-patch ops) as well as lines, runs under `timeout 120` in CI, and prints a COVERAGE block of what it does not see. Tests: `tests/test_validate_reflector_sources.py`. |
| `check-live-reflector-drift.py` + `collect-reflector-metadata.sh` | MANUAL, not run in CI: the collector lists Secret annotation metadata with a read-only kubectl (only metadata is written out; kubectl still fetches the full objects into memory) and stamps the cluster identity, which the checker must be told to expect (`--expect-context`/`--expect-server`); the checker flags sources that are not provably off, mirror markers and name-based copies, rc 2 when the listing is partial. Tests on synthetic fixtures: `tests/test_live_reflector_drift.py`. |

Always set `KUBECONFIG` to the target cluster before running.

