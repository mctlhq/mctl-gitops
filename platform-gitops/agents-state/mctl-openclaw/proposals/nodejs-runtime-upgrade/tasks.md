# Tasks: nodejs-runtime-upgrade

- [ ] 1. Определить текущую версию Node.js в базовом образе — проверить Dockerfile(s) в
  mctl-gitops (и upstream fork если есть) — DoD: зафиксирована точная версия `node:XX.YY.Z`
  используемая в текущем production образе; если < v22.22.0 — подтверждено что CVE активны

- [ ] 2. Обновить базовый образ до Node.js v22.22.0 (зависит от 1) — изменить `FROM node:XX`
  на `FROM node:22.22.0-alpine` (или `-slim` если текущий образ slim-based) в Dockerfile —
  DoD: Dockerfile содержит `FROM node:22.22.0-*`; образ успешно собирается локально
  (`docker build` без ошибок); openclaw стартует в контейнере (`node --version` возвращает
  v22.22.0)

- [ ] 3. Добавить CI шаг: npm audit (зависит от 2) — добавить шаг `npm audit --audit-level=high
  --production` в CI pipeline после `npm ci` и до `docker build` — DoD: шаг добавлен в
  pipeline конфигурацию; при отсутствии High/Critical уязвимостей pipeline проходит;
  при введении тестовой уязвимости (npm install тестового пакета с known CVE) — pipeline
  падает с кодом выхода != 0

- [ ] 4. Добавить CI шаг: malicious package grep (зависит от 2) — добавить скрипт-проверку
  lockfile на `lotusbail` и `discord.js-user` (и любые другие пакеты из `.malicious-packages`
  если файл существует); шаг выполняется до `npm ci` — DoD: скрипт добавлен в pipeline;
  при clean lockfile проходит; при добавлении `"lotusbail": "1.0.0"` в lockfile — падает
  с явным сообщением об ошибке

- [ ] 5. Создать файл `.malicious-packages` (зависит от 4) — один пакет на строку, начальный
  список: `lotusbail`, `discord.js-user` — DoD: файл зачекинен в репозиторий; CI шаг
  читает список из файла а не из hardcode в скрипте; добавление нового пакета в файл
  автоматически подхватывается CI без изменения скрипта

- [ ] 6. Задеплоить новый образ в `labs` (зависит от 3, 4, 5) — собрать образ с новым Node.js,
  обновить тег в gitops overlay labs, выполнить ArgoCD sync — DoD: ArgoCD показывает
  Synced+Healthy для labs; `kubectl exec` в pod даёт `node --version` v22.22.0; restore-state
  probe прошёл (ADR 0002); RAM-delta относительно baseline <= 20MB

- [ ] 7. Задеплоить в `admins` (зависит от 6) — наблюдение 24 часа после labs, затем
  аналогичный rollout — DoD: ArgoCD Synced+Healthy; функциональные каналы admins работают;
  s3-sync canary зелёный

- [ ] 8. Задеплоить в `ovk` (зависит от 7) — rollout в production тенант — DoD: ArgoCD
  Synced+Healthy; restore-state probe прошёл; s3-sync canary активен; ни один production
  канал ovk не потерял соединение через 24 часа после деплоя

## Тесты

- [ ] T1. Node.js версия в образе — `docker run --rm <image> node --version` возвращает
  `v22.22.x`; ожидаемый результат: версия >= 22.22.0

- [ ] T2. npm audit чистый lockfile — запустить `npm audit --audit-level=high --production`
  в текущей кодовой базе после обновления lockfile; ожидаемый результат: exit code 0,
  no high/critical vulnerabilities found

- [ ] T3. npm audit триггер — временно добавить known-vulnerable пакет в devDependencies,
  запустить audit; ожидаемый результат: exit code != 0, вывод содержит название CVE

- [ ] T4. Malicious package grep: clean — запустить скрипт на production lockfile;
  ожидаемый результат: "Malicious package check passed.", exit code 0

- [ ] T5. Malicious package grep: detect — вручную добавить строку `"lotusbail": "1.0.0"`
  в package-lock.json (не коммитить), запустить скрипт; ожидаемый результат: сообщение
  "SECURITY: malicious package 'lotusbail' found in lockfile", exit code 1

- [ ] T6. RAM baseline labs — до и после деплоя нового образа сравнить `kubectl top pod`
  для openclaw pod в labs; ожидаемый результат: delta <= 20MB

- [ ] T7. Restore-state probe после деплоя — перезапустить pod labs вручную после деплоя
  нового образа; ожидаемый результат: pod переходит в Ready без превышения probe timeout

- [ ] T8. S3-sync canary после деплоя в labs — дождаться следующего цикла canary workflow
  после завершения rollout labs; ожидаемый результат: canary зелёный, timestamp в S3 свежий

## Откат

Откат выполняется через gitops без изменений в коде:

1. В overlay тенанта вернуть предыдущий тег Docker образа (с предыдущей версией Node.js).
2. Выполнить ArgoCD sync — ArgoCD задеплоит предыдущий образ.
3. Restore-state probe гарантирует (ADR 0002) что pod не станет Ready до восстановления
   S3 state — даже при откате.

Порядок отката при инциденте: ovk → admins → labs (обратно ADR 0001).

CI шаги (`npm audit`, malicious package grep) можно временно перевести в warn-only mode
(убрать `-e` флаг или добавить `|| true`) если они дают false positives блокирующие hotfix —
но это требует явного решения и фиксации в issue-трекере.
