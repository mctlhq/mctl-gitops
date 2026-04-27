# Политика allowlist для external skills из ClawHub

## Контекст
Активная кампания ClawHavoc разместила 341+ вредоносных skills в официальном ClawHub marketplace (зафиксировано в inbox/2026-04-27.md, источник: armosec.io). CVE пока не назначен, кампания продолжается. Платформа mctl-openclaw использует 3-layer skills архитектуру, где Layer 3 (remote/HTTP-delegated skills) регистрируется через REST API без ограничений на источник. Если хотя бы один тенант (ovk, labs, admins) устанавливал skills с ClawHub без верификации источника, вектор атаки уже открыт.

На данный момент в gitops-конфиге нет механизма, фиксирующего список разрешённых источников skills. Отсутствует и CI-проверка, которая детектировала бы появление новых неодобренных skill-источников при изменениях в манифестах. Это конфигурационное изменение с низким effort: не затрагивает RAM, не требует апстрим-патча, реализуется через Helm values + CI-шаг.

## User stories
- AS a platform operator I WANT фиксированный allowlist разрешённых источников Layer 3 skills в gitops-конфиге каждого тенанта SO THAT вредоносные skills из ClawHub не могут быть зарегистрированы без явного одобрения
- AS a security engineer I WANT CI-проверку, которая блокирует PR при появлении нового неодобренного skill-источника SO THAT случайная или несанкционированная регистрация вредоносных skills выявляется до деплоя
- AS a tenant operator I WANT понятный процесс одобрения нового skill-источника (allowlist update) SO THAT легитимные skills можно добавить без обхода защиты

## Acceptance criteria (EARS)
- WHEN Layer 3 skill регистрируется через REST API с источником (URL/origin), не входящим в allowlist тенанта THEN THE SYSTEM SHALL отклонить регистрацию с кодом 403 и сообщением об ограничении политики
- WHILE allowlist для тенанта задан в Helm values THE SYSTEM SHALL применять его ко всем входящим запросам на регистрацию remote skills, включая restart пода и hot-reload
- IF CI-пайплайн обнаруживает в PR изменение, добавляющее новый skill-источник в манифест без соответствующего обновления allowlist THEN THE SYSTEM SHALL провалить CI-шаг с явным сообщением о необходимости review
- WHEN allowlist задан как пустой список THEN THE SYSTEM SHALL блокировать регистрацию всех Layer 3 skills (fail-closed семантика)
- IF тенант не имеет явно заданного allowlist в Helm values THEN THE SYSTEM SHALL применять deny-all политику по умолчанию для Layer 3 skills
- WHEN allowlist обновляется через gitops-манифест THEN THE SYSTEM SHALL применить новую политику без рестарта пода (hot-reload через YAML skill config)

## Out of scope
- Аудит уже установленных Layer 3 skills (отдельная задача инвентаризации)
- Изменения в Layer 1 (built-in) и Layer 2 (YAML hot-reload) skills — они не регистрируются через REST API из внешних источников
- Блокировка ClawHub на сетевом уровне (NetworkPolicy) — это более широкая мера, отдельное предложение
- Сканирование содержимого skills на вредоносный код — выходит за рамки allowlist-контроля
- Изменения в upstream openclaw API
