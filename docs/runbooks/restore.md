# Runbook: восстановление из бэкапов

Инвентарь stateful-состояния и проверенные процедуры восстановления.
Правило: **непроверенный бэкап считается отсутствующим** — каждая процедура
ниже имеет drill-вариант, который не трогает прод. Дату последнего drill
фиксировать в таблице внизу.

## Инвентарь

| Состояние | Где живёт | Бэкап | Куда | Retention | Переживает потерю кластера? |
|---|---|---|---|---|---|
| Postgres (9 tenant DB + backstage, argo, temporal, mctl-api audit) | CNPG `shared-pg` | barman + daily ScheduledBackup 02:00 | R2 `s3://vault-backup/postgres-backups/shared-pg` | 14d | да |
| Vault (все секреты платформы) | vault ns, raft | CronJob 03:00 | R2 `s3://<bucket>/vault-backups/` | 30 копий | да |
| Кластерное состояние k8s (etcd) | single CP node | k3s snapshot каждые 6h | R2 `mctl-etcd-snapshots/k3s-preview` | 56 копий (14d) | да |
| Метрики | VMSingle (3d retention) | vmbackup daily | R2 `s3://vault-backup/victoria-metrics` | — | да |
| Логи | Loki | хранение сразу в R2 | R2 | 7d | да |
| Terraform state | R2 `mctl-terraform-state` | версионирование R2 | — | — | да |
| mctl-agent tickets/webhooks/metrics | Postgres `mctl-agent` DB в shared-pg (`DATABASE_URL`) | через CNPG | — | 14d | как Postgres |

### Закрытый gap: бэкапы Postgres переведены с in-cluster MinIO на R2

До 2026-07 `barmanObjectStore` писал в MinIO на PVC этого же кластера — при
потере кластера пропадали и база, и её бэкапы. Теперь destination — R2
(креды: ExternalSecret `cnpg-backup-r2` ← Vault `platform/vault/r2-backup`).
Старые бэкапы в MinIO (`s3://postgres-backups/shared-pg`) остаются читаемыми
для PITR на даты до переключения, пока MinIO жив. Первый базовый бэкап в R2
делает одноразовый `Backup` CR `shared-pg-r2-initial` — до его завершения
восстановление возможно только из MinIO.

## 1. CNPG / Postgres

### Drill (безопасно, не трогает прод)

Восстановить копию `shared-pg` в отдельный namespace из barman-архива:

```yaml
# scratch: restore-drill.yaml — namespace pg-restore-drill
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: shared-pg-drill
  namespace: pg-restore-drill
spec:
  instances: 1
  imageName: ghcr.io/cloudnative-pg/postgresql:17.2   # тот же major!
  storage:
    storageClass: hcloud-volumes
    size: 40Gi
  bootstrap:
    recovery:
      source: shared-pg
  externalClusters:
    - name: shared-pg
      barmanObjectStore:
        destinationPath: s3://vault-backup/postgres-backups/shared-pg
        endpointURL: https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com
        s3Credentials:
          accessKeyId:
            name: cnpg-backup-r2   # скопировать Secret в drill-namespace
            key: ACCESS_KEY_ID
          secretAccessKey:
            name: cnpg-backup-r2
            key: SECRET_ACCESS_KEY
        wal:
          compression: gzip
```

Проверка:
```bash
kubectl create ns pg-restore-drill
kubectl get secret cnpg-backup-r2 -n platform-db -o yaml | \
  sed 's/namespace: .*/namespace: pg-restore-drill/' | kubectl apply -f -
kubectl apply -f restore-drill.yaml
kubectl -n pg-restore-drill wait cluster/shared-pg-drill --for=condition=Ready --timeout=15m
# сверить данные: список БД + счётчики строк в паре ключевых таблиц
kubectl -n pg-restore-drill exec shared-pg-drill-1 -- psql -c '\l'
kubectl -n pg-restore-drill exec shared-pg-drill-1 -- \
  psql -d backstage -c 'select count(*) from final_entities;'
# убрать за собой
kubectl delete ns pg-restore-drill
```

PITR: добавить в `recovery` блок `recoveryTarget: { targetTime: "2026-07-18 03:00:00+00" }`.

### Реальное восстановление

То же самое, но в namespace `platform-db` с именем нового кластера, затем
переключить приложения (Secret'ы `*-db-creds` пересоздаст CNPG managed roles,
rw-service имя поменяется — обновить values затронутых сервисов) — либо
восстановить под старым именем после удаления погибшего Cluster CR.

## 2. Vault

### Drill (локально, ничего не трогает)

```bash
aws s3 ls s3://<bucket>/vault-backups/ --endpoint-url <r2-endpoint> --region auto | sort | tail -1
aws s3 cp s3://<bucket>/vault-backups/<latest>.snap ./vault.snap \
  --endpoint-url <r2-endpoint> --region auto

# локальный vault в docker
docker run -d --name vault-drill --cap-add=IPC_LOCK -p 8200:8200 hashicorp/vault:1.18 \
  server -dev -dev-root-token-id=drill
export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=drill
vault operator raft snapshot restore -force vault.snap   # см. примечание ниже
# проверить, что секреты читаются:
vault kv list secret/platform/
vault kv get secret/platform/mctl-agents
docker rm -f vault-drill
```

Примечание: `-dev` использует inmem storage — для честного drill поднять vault
с raft-конфигом (single node) вместо dev-режима, иначе restore снапшота raft
не сработает. Минимальный конфиг: `storage "raft" { path = "/vault/data" }`,
`vault operator init -key-shares=1`, unseal, затем restore с `-force`.

Успех drill = снапшот скачивается, восстанавливается, KV-секреты читаются.

### Реальное восстановление

1. Новый Vault (helm-чарт из bootstrap), `vault operator init`, unseal.
2. `vault operator raft snapshot restore -force vault.snap` на активной ноде.
3. Unseal-ключи от **старого** Vault (снапшот несёт старые seal-ключи) — они
   обязаны храниться вне кластера. Убедиться, что это так, ДО того как
   понадобится.
4. Проверить: ESO ClusterSecretStore `vault-backend` снова Ready, ExternalSecrets синкаются.

## 3. etcd / k3s (single control-plane)

Снапшоты пишутся каждые 6h в R2 `mctl-etcd-snapshots/k3s-preview`
(настроено в `infrastructure/k3s-preview/kube.tf`, `etcd_s3_backup`).

### Проверка, что снапшоты вообще идут (после первого apply)

```bash
ssh <cp-node> sudo k3s etcd-snapshot ls --etcd-s3 \
  --etcd-s3-endpoint=<r2-endpoint> --etcd-s3-bucket=mctl-etcd-snapshots \
  --etcd-s3-folder=k3s-preview --etcd-s3-access-key=... --etcd-s3-secret-key=...
```

### Реальное восстановление (CP-нода погибла)

По k3s docs (datastore/backup-restore): на новой/пересозданной CP-ноде:

```bash
sudo k3s server --cluster-reset \
  --cluster-reset-restore-path=<snapshot-name> \
  --etcd-s3 --etcd-s3-endpoint=<r2-endpoint> \
  --etcd-s3-bucket=mctl-etcd-snapshots --etcd-s3-folder=k3s-preview \
  --etcd-s3-access-key=... --etcd-s3-secret-key=...
# после завершения — перезапустить k3s без флагов reset
sudo systemctl start k3s
```

Затем: воркеры переподключатся; PVC (hcloud-volumes) переподцепятся, если
ноды живы. При полной потере всех нод — сначала `terraform apply` заново
(см. `infrastructure/k3s-preview/README.md`, "Disaster recovery"), затем
restore Vault (§2) и Postgres (§1) — в этом порядке, т.к. ESO зависит от Vault.

## 4. VictoriaMetrics (опционально)

Метрики — потеря терпима (retention всё равно 3d). Restore: `vmrestore
-src=s3://vault-backup/victoria-metrics/<snapshot> -storageDataPath=...`.

## Порядок полного DR (кластер потерян целиком)

1. `terraform apply` (+ `bootstrap_argocd=true`) — голый кластер + ArgoCD.
2. Vault restore (§2) + unseal → ESO оживает.
3. ArgoCD синкает платформу из этого репо.
4. Postgres restore (§1) из R2.
5. Прогнать smoke: mctl-api `/healthz`, деплой тестового сервиса.

## Журнал drill'ов

| Дата | Что проверяли | Результат | Заметки |
|---|---|---|---|
| — | CNPG restore | не проводился | |
| — | Vault restore | не проводился | |
| — | etcd snapshot ls | не проводился | ждёт первого apply с etcd_s3_backup |
