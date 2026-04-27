# Egress NetworkPolicy для ограничения исходящего трафика из openclaw pods

## Контекст

CVE-2026-41297 (SSRF в marketplace plugin download) позволяет перенаправлять HTTP-запросы
openclaw на произвольные внутренние или внешние хосты. Несмотря на то что этот конкретный CVE
закрывается обновлением до 2026.4.25 (см. proposal `upgrade-to-2026-4-25`), сам архитектурный
gap — отсутствие egress NetworkPolicy на namespace openclaw — сохраняется и останется уязвимым
к любым будущим SSRF в openclaw core или его плагинах.

Сейчас pods openclaw в namespaces `ovk`, `labs`, `admins` не имеют ограничений на исходящий
трафик: pod может обратиться к любому IP внутри кластера и вовне. Это нарушает принцип
least-privilege сетевого доступа и создаёт неустранимый риск латерального перемещения при любом
будущем SSRF или RCE в openclaw. Kubernetes NetworkPolicy с явным whitelist egress устраняет
этот класс атак независимо от версии openclaw.

## User stories

- AS a platform security engineer I WANT чтобы egress из openclaw pods был ограничен
  только необходимыми endpoints SO THAT SSRF-уязвимость в любой версии openclaw не позволяет
  достичь внутренних сервисов кластера или нецелевых внешних хостов
- AS a platform operator I WANT NetworkPolicy применялась через gitops (ArgoCD) без изменений
  в коде openclaw SO THAT изменение можно откатить манифестом без деплоя нового образа
- AS a labs tenant operator I WANT NetworkPolicy не увеличивала потребление RAM пода SO THAT
  labs тенант не приближается к OOM

## Acceptance criteria (EARS)

- WHEN pod openclaw в любом из тенантов (`ovk`, `labs`, `admins`) пытается обратиться
  к IP-адресу, не входящему в whitelist egress THE SYSTEM SHALL отклонять соединение на уровне
  iptables (connection timeout или connection refused без прохождения пакета)
- WHEN pod openclaw выполняет запрос к разрешённому S3 endpoint THE SYSTEM SHALL пропускать
  трафик без задержки
- WHEN pod openclaw выполняет запрос к разрешённому upstream marketplace endpoint THE SYSTEM
  SHALL пропускать трафик без задержки
- WHEN pod openclaw выполняет запросы к channel API endpoints (Telegram, Discord, Slack,
  WhatsApp и другие каналы из списка архитектуры) THE SYSTEM SHALL пропускать трафик
- WHILE NetworkPolicy применена THE SYSTEM SHALL не блокировать трафик к DNS (UDP/TCP 53
  в namespace kube-dns)
- WHILE NetworkPolicy применена THE SYSTEM SHALL не блокировать egress трафик к mctl-api
  endpoint (`api.mctl.ai/mcp`) для MCP-интеграции
- IF openclaw pod пытается инициировать соединение к любому адресу в RFC-1918 диапазонах
  (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), не являющемуся явно разрешённым сервисом
  кластера THEN THE SYSTEM SHALL блокировать соединение
- WHEN изменяется состав разрешённых endpoints (новый канал или S3 region) THE SYSTEM SHALL
  применять обновлённую NetworkPolicy через ArgoCD sync без рестарта pods

## Out of scope

- Изменения в исходном коде openclaw или его конфигурации
- Ingress NetworkPolicy (управление входящим трафиком — отдельная задача)
- Изменение resource limits или requests в pods openclaw
- Межтенантная сетевая изоляция (namespace isolation) — уже обеспечена архитектурой трёх
  независимых namespaces согласно ADR 0001
- Внедрение service mesh (Istio, Linkerd) — более тяжёлое решение, отдельное решение
