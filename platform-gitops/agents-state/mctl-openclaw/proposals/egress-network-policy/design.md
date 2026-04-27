# Design: egress-network-policy

## Текущее состояние

Согласно `context/architecture.md`, openclaw деплоится в три Kubernetes namespaces: `ovk`, `labs`,
`admins`. Каждый namespace содержит независимый deployment openclaw с отдельным S3 bucket для
state (ADR 0002). Деплой управляется через mctl-gitops → ArgoCD.

В настоящее время ни один из трёх namespaces не имеет Kubernetes NetworkPolicy. Это означает
что pods openclaw имеют unrestricted egress: они могут инициировать TCP/UDP соединения к любому
IP-адресу — как внутри кластера (другие namespace, control plane), так и вовне (произвольные
внешние хосты). CVE-2026-41297 (SSRF в marketplace) наглядно показал как этот gap позволяет
злоумышленнику управлять исходящими запросами pod'а.

## Предлагаемое решение

Создать по одному манифесту `NetworkPolicy` для каждого из трёх namespaces. Манифесты
добавляются в mctl-gitops репозиторий и применяются через ArgoCD sync — без изменений в коде
openclaw, без изменения Docker образов, без влияния на RAM.

### Структура манифеста

Каждый NetworkPolicy манифест содержит:

1. **Default deny egress** — базовое правило: весь egress заблокирован, если явно не разрешён.
2. **Allow DNS** — UDP/TCP port 53 к kube-dns (namespace `kube-system`, label
   `k8s-app: kube-dns`). Без DNS pod не может резолвить ни один hostname.
3. **Allow S3** — HTTPS (TCP 443) к S3 endpoint тенанта. Конкретные CIDR или FQDN
   зависят от провайдера (AWS S3, Minio и т.п.) — указываются в overlay тенанта.
4. **Allow channel APIs** — HTTPS (TCP 443) к API endpoints каналов:
   - Telegram: `api.telegram.org`
   - Discord: `discord.com`, `gateway.discord.gg`
   - Slack: `slack.com`, `wss-primary.slack.com`
   - WhatsApp (Baileys): `web.whatsapp.com`, `*.whatsapp.net`
   - Остальные каналы по аналогии (полный список в манифесте по архитектуре)
5. **Allow upstream marketplace** — HTTPS к `api.clawhub.io` (или актуальному marketplace
   endpoint upstream openclaw).
6. **Allow mctl-api MCP** — HTTPS к `api.mctl.ai` для MCP-интеграции.

### Раздельные overlays на тенант

Поскольку тенанты могут использовать разные S3 регионы или иметь специфические каналы,
NetworkPolicy оформляются как Kustomize overlays в mctl-gitops:

```
gitops/
  base/
    network-policy/
      egress-network-policy.yaml   # базовый шаблон с общими правилами
  overlays/
    labs/
      network-policy/
        patch-s3-cidr.yaml         # labs-specific S3 endpoint
    admins/
      network-policy/
        patch-s3-cidr.yaml
    ovk/
      network-policy/
        patch-s3-cidr.yaml
```

### Порядок применения

Rollout следует ADR 0001: labs → admins → ovk. NetworkPolicy применяются последовательно с
периодом наблюдения:
1. Применить в `labs`, наблюдать N дней — убедиться что ни один нужный запрос не заблокирован
   (смотреть в логи openclaw на connection errors).
2. Применить в `admins`.
3. Применить в `ovk`.

NetworkPolicy не требует остановки s3-sync canary и не влияет на restore-state probe (ADR 0002),
поскольку S3 endpoint явно разрешён в whitelist.

### Важно: labs RAM

Kubernetes NetworkPolicy реализована на уровне kube-proxy/iptables (или CNI plugin). Она
не добавляет sidecar-контейнер и не увеличивает RAM openclaw pod. Для `labs` тенанта (близкого
к лимиту памяти) это ключевое свойство решения.

## Альтернативы

### 1. Service mesh (Istio / Linkerd)

Обеспечивает L7-контроль egress, mTLS, детальный audit log. Однако:
- Требует внедрения sidecar (Envoy proxy) в каждый pod → существенный рост RAM, критично для `labs`.
- Значительная операционная сложность (CRD, certificates rotation, control plane).
- Избыточно для текущей задачи — нам нужна L4 whitelist, не L7 inspection.

Отброшено как несоразмерное по complexity/RAM impact.

### 2. Внешний egress gateway (Squid, Envoy как отдельный pod)

Весь трафик openclaw pods направляется через egress proxy, который фильтрует по FQDN.
- Даёт FQDN-level filtering вместо IP/CIDR (полезно для cloud-hosted channel APIs с динамическими IP).
- Добавляет отдельный pod → дополнительный RAM на уровне кластера, latency, SPOF.
- Сложнее в конфигурировании и rollback.

Отброшено: выгода (FQDN resolution) не перевешивает сложность для текущего threat model.
Может быть рассмотрено в будущем как отдельный proposal если IP ranges channel APIs окажутся нестабильными.

### 3. Ничего не делать (закрыть SSRF только через обновление openclaw)

CVE-2026-41297 закрыт в 2026.3.31+. Однако:
- Будущие SSRF в openclaw или его плагинах останутся незакрытыми на уровне сети.
- Defense-in-depth требует сетевой изоляции независимо от версии приложения.
- Effort крайне низкий (манифест без кодовых изменений).

Отброшено как недостаточное.

## Влияние на платформу

### Migration / миграции

Нет миграции данных. Изменение — только добавление NetworkPolicy манифестов в gitops.

### Backward compatibility

Kubernetes NetworkPolicy является аддитивной операцией: пока правила egress не применены,
поведение не меняется. После применения блокируются только соединения вне whitelist.
Риск ложной блокировки легитимного трафика — основной операционный риск; митигируется
поэтапным rollout через labs.

### Resource impact

- RAM openclaw pods: **без изменений** (NetworkPolicy — iptables rules, не sidecar).
- CPU: минимальный overhead iptables на пакет, незначимый для текущей нагрузки.
- `labs` тенант: **не затронут с точки зрения памяти** — не risky.

### Риски и митигации

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Блокировка нужного channel API (неполный whitelist) | Средняя | Rollout через labs с наблюдением; логи openclaw; easy rollback удалением манифеста |
| S3 endpoint CIDR меняется (cloud провайдер) | Низкая | Использовать FQDN-based egress rules если CNI поддерживает (Calico NetworkPolicy), или мониторинг S3 connectivity |
| CNI плагин кластера не поддерживает NetworkPolicy | Низкая | Проверить на labs до rollout в production namespaces |
| Блокировка mctl MCP интеграции | Низкая | `api.mctl.ai` явно включён в whitelist; проверяется в T3 |
