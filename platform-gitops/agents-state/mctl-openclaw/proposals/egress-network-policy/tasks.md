# Tasks: egress-network-policy

- [ ] 1. Инвентаризация egress endpoints — составить полный список хостов/CIDR, к которым
  реально обращаются openclaw pods в трёх тенантах — DoD: таблица endpoints (hostname,
  port, протокол, тенант) зафиксирована в PR-описании; покрывает S3, все активные каналы
  из `context/architecture.md`, upstream marketplace, `api.mctl.ai`

- [ ] 2. Базовый манифест NetworkPolicy (зависит от 1) — создать `egress-network-policy.yaml`
  в `gitops/base/network-policy/` с правилами: default-deny egress, allow DNS, allow S3
  (placeholder CIDR), allow channel APIs, allow marketplace, allow mctl-api — DoD: манифест
  валиден (`kubectl apply --dry-run=client`), содержит все endpoints из задачи 1, прошёл
  review

- [ ] 3. Tenant overlays (зависит от 2) — создать Kustomize patches в
  `gitops/overlays/{labs,admins,ovk}/network-policy/` с tenant-specific S3 CIDR/FQDN —
  DoD: три overlay файла, каждый проходит `kustomize build` без ошибок

- [ ] 4. Применить NetworkPolicy в `labs` (зависит от 3) — добавить overlay labs в ArgoCD
  Application, выполнить sync, наблюдать 48 часов — DoD: ArgoCD показывает Synced+Healthy
  для namespace labs; в логах openclaw нет connection errors на разрешённые endpoints;
  s3-sync canary не сигнализирует ошибок; restore-state probe проходит

- [ ] 5. Применить NetworkPolicy в `admins` (зависит от 4) — аналогично задаче 4 для
  namespace admins, наблюдать 24 часа — DoD: ArgoCD Synced+Healthy; нет connection errors;
  функциональные каналы admins работают

- [ ] 6. Применить NetworkPolicy в `ovk` (зависит от 5) — аналогично для namespace ovk —
  DoD: ArgoCD Synced+Healthy; restore-state probe прошёл; s3-sync canary активен и зелёный;
  ни один production канал ovk не потерял соединение через 24 часа после применения

## Тесты

- [ ] T1. Dry-run validation — `kubectl apply --dry-run=server -f egress-network-policy.yaml`
  для каждого тенанта; ожидаемый результат: no errors, no warnings

- [ ] T2. Позитивный тест: разрешённый egress — после применения в labs выполнить `kubectl exec`
  в pod openclaw/labs и проверить curl к каждому endpoint из whitelist (S3, Telegram API,
  Discord API, `api.mctl.ai`); ожидаемый результат: HTTP 200/ответ без connection refused

- [ ] T3. Негативный тест: блокировка нецелевого egress — из pod openclaw/labs попытаться
  достичь внутреннего кластерного IP (например, kube-apiserver, другой namespace service),
  не входящего в whitelist; ожидаемый результат: connection timeout или ICMP reject в
  течение < 5 секунд

- [ ] T4. DNS доступность — в pod openclaw/labs выполнить `nslookup api.telegram.org`
  и `nslookup s3.<region>.amazonaws.com`; ожидаемый результат: успешная резолюция

- [ ] T5. S3-sync canary — после применения в labs убедиться что s3-sync canary workflow
  завершается успешно в следующем цикле; ожидаемый результат: canary зелёный, timestamp
  в S3 свежий

- [ ] T6. Restore-state probe — после применения в labs перезапустить pod openclaw/labs
  вручную (`kubectl rollout restart`) и проверить что readiness probe проходит за штатный
  timeout; ожидаемый результат: pod переходит в Ready без ArgoCD rollback

## Откат

NetworkPolicy является отдельным Kubernetes объектом, не связанным с Deployment openclaw.
Откат выполняется без рестарта pods и без изменения версии openclaw:

1. `kubectl delete networkpolicy egress-openclaw -n <namespace>` — немедленно восстанавливает
   unrestricted egress для указанного тенанта.
2. Или: удалить overlay из gitops и выполнить ArgoCD sync с prune — политика удалится через ArgoCD.

Откат не затрагивает S3 state, s3-sync canary и restore-state probe. Rollback безопасен
в любой момент без координации с командой openclaw.

Рекомендуемый порядок отката при инциденте: сначала откатить `ovk`, затем `admins`, затем `labs`
(обратно ADR 0001).
