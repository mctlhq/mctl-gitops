# scripts/

One-shot recovery helpers used during platform incidents. Idempotent by
design — re-running on a healthy cluster is a no-op.

| Script | Purpose |
|---|---|
| `heal-eso-lac.sh` | Strip stale `kubectl.kubernetes.io/last-applied-configuration` annotations from ExternalSecret objects after an ESO chart version roundtrip leaves them with `apiVersion=external-secrets.io/v1` + embedded `resourceVersion`. Used 2026-05-07 during recovery from the 0.10.x → 2.x → 0.10.x roundtrip. Default is `--dry-run`; pass `--apply` to mutate. |

Always set `KUBECONFIG` to the target cluster before running.
