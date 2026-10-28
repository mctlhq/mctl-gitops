# Preprod control plane — accepted residuals

The platform runs on a single k3s cluster (`mctl-preprod`): 1 control-plane
node + 3 workers. There is no separate production cluster. This runbook
records the availability and encryption residuals that SOC review left
accepted, and the controls that *are* in git.

## F11 — single control plane (accepted)

A second control-plane node is deferred until the first paying customer
(ROADMAP Horizon 2). Losing the CP node takes down the API server until
Terraform rebuild + restore (`docs/runbooks/restore.md`).
Failure-path checklist and monitoring status:
`docs/runbooks/control-plane-failure-paths.md`.

Compensating controls in place:

- OS auto-upgrade is **off** (`automatically_upgrade_os = false` in
  `infrastructure/k3s-preview/kube.tf`) so kured cannot drain the only CP.
- PodDisruptionBudgets `minAvailable: 1` on **mctl-api**, **Argo CD server**,
  and **Argo CD repo-server**. Traefik already runs 3 replicas with
  `maxUnavailable: 33%` (desiredHealthy 2); that budget is pinned in
  `extra-manifests/traefik-helmchartconfig.yaml.tpl` and must not be
  weakened to `minAvailable: 1`.
- Replica counts are not raised by this control. A 1-replica PDB with
  `minAvailable: 1` allows 0 voluntary evictions (drain/kured). Rolling
  updates still work: Deployments delete pods directly; PDBs only gate the
  Eviction API.

### If the control-plane node dies

1. Rebuild the cluster from `infrastructure/k3s-preview/`
   (`README.md` "Disaster recovery").
2. Restore Vault, then Postgres, in that order — ESO depends on Vault
   (`docs/runbooks/restore.md`).
3. Restore etcd from R2 (`s3://mctl-etcd-snapshots/k3s-preview`). Off-cluster
   snapshots have been live since 2026-08-15 (gitops#841; ROADMAP 2.1).
   Procedure: `docs/runbooks/restore.md` §3. A full restore *drill* has not
   been run — presence in S3 is confirmed, not a throwaway-cluster restore.

Do not add a second CP node from this runbook.

## F15 — Vault east-west TLS (accepted residual)

Vault's Raft listener is `tls_disable = 1`. Edge TLS already terminates at
Traefik (`https://secrets.mctl.ai`, cert-manager). In-cluster clients
(ESO, workflows, backups) speak `http://vault.vault.svc:8200`.

Enabling a TLS listener is **not** a contained gitops change: it requires
internal certs for `vault-0/1/2`, flipping `retry_join` to `https`, and
updating every in-cluster `VAULT_ADDR`. A botched rollout splits Raft
quorum. Deferred until a customer asks, with the existing ingress TLS as
the compensating control.

`AUDIT_DB_URL sslmode=require` to CNPG is live in `mctl-api.yaml` (F15
partial). Vault east-west TLS is the remaining hole, not Postgres.

## F20 — Kubernetes API audit

Policy file: `infrastructure/k3s-preview/audit-policy.yaml`.

- Secrets: Metadata only (no bodies).
- TokenReview/TokenRequest: Metadata only (bodies carry bearer tokens).
- SubjectAccessReviews: RequestResponse.
- Catch-all: Metadata.
- Logs stay on the CP node at `/var/lib/rancher/k3s/server/logs/audit.log`
  (30-day rotation via `audit-log-maxage=30`, 100MiB files, 10 backups).
  Shipping those files to Loki is not part of this control.

From-zero rebuilds write the file in `preinstall_exec` and pass
`kube-apiserver-arg` via `control_planes_custom_config`. On the live
cluster the file must exist **before** a terraform apply that adds those
args, or the apiserver will refuse to start.

### All apiserver args live in config.yaml, never in config.yaml.d

`control_planes_custom_config` is the only place for `kube-apiserver-arg`
(audit and the ZITADEL OIDC flags of #1881). Do not add a drop-in under
`/etc/rancher/k3s/config.yaml.d/` with the same key: k3s lets a drop-in's
list **replace** the list from `config.yaml` (only a key spelled
`kube-apiserver-arg+` appends), so every arg Terraform writes silently stops
applying while the plan and apply look clean.

That happened once. The audit args were first rolled out by hand on
2026-08-15 as `config.yaml.d/audit.yaml`. When the OIDC flags were applied on
2026-10-14 the apiserver came up with the drop-in's five audit args and none
of the OIDC ones. The drop-in was moved to
`/root/k3s-audit-dropin-2026-08-15.yaml.bak` and k3s restarted.

Check what the apiserver actually runs with, not what the file says
(`k3s.io/node-args` on the Node does not show it reliably either):

```bash
ssh root@<cp> "journalctl -u k3s --since -10min --no-pager \
  | grep 'Running kube-apiserver' | tail -1 \
  | grep -o -E -- '--(oidc|audit)-[a-z-]+=[^ ]+'"
```

## F9 — Vault JWT for GitHub Actions (live)

`auth/jwt` is mounted. Role `github-actions` is live. GHA `build-image.yaml`
logs in with OIDC (`permissions.id-token: write`). Confirmed end to end on
2026-08-15 (`infrastructure/k3s-preview/cluster-bootstrap/vault-config/README.md`).
Do **not** `vault auth enable jwt` again and do not widen the provisioner.

## F18 — PSS restricted / cosign (Horizon 3)

Out of scope. PSS stays `enforce=baseline`. Cosign/admission is ROADMAP
Horizon 3.
