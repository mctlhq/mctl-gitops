# Design: scaffolder-path-traversal

## Текущее состояние
Согласно `context/architecture.md`, mctl-portal работает на Backstage latest (root
`package.json` фиксирует `1.0.1`). Scaffolder — плагин `plugin-scaffolder-backend`,
который монтирует actions из `@backstage/backend-defaults`. Backend-pod запущен в тенанте
`admins`; секреты Vault смонтированы через ExternalSecret как переменные среды и файлы.
Действующая версия `plugin-scaffolder-backend` ниже 3.1.1 и `@backstage/backend-defaults`
ниже 0.12.2, то есть уязвима к CVE-2026-24046.

Symlink-guard отсутствует: при вызове `fs:delete` или при распаковке архива движок
scaffolder разрешает путь без проверки выхода за границу рабочего каталога задачи
(`/tmp/scaffolder-<uuid>/`).

## Предлагаемое решение
Обновить два пакета до исправленных версий в рамках одного PR:

```
@backstage/backend-defaults  ^0.12.2
plugin-scaffolder-backend    ^3.1.1
```

Апстрим-фикс внедряет `realpath`-проверку после разрешения каждого пути внутри actions:
если результирующий абсолютный путь не начинается с корня workspace — операция прерывается
с ошибкой. Symlink-ы внутри архивов полностью отклоняются.

Шаги обновления:
1. `yarn up @backstage/backend-defaults@^0.12.2 plugin-scaffolder-backend@^3.1.1` в корне
   монорепо.
2. Проверить, что `yarn.lock` не подтянул транзитивные зависимости с несовместимыми
   peer-версиями (backstage-cli и platform версии должны совпадать).
3. Запустить `yarn backstage-cli repo build` и playwright smoke-тест шаблона создания
   сервиса.
4. Обновить Docker-образ; ArgoCD-sync в `admins` применит новый манифест.

Поскольку `plugin-scaffolder-backend` 3.1.1 закрывает также CVE-2026-32237
(scaffolder-secret-leak), оба CVE закрываются одним PR — детальное обоснование
в `proposals/scaffolder-secret-leak/design.md`.

## Альтернативы

**A. WAF/network policy блокировка path-traversal запросов**
Потребует разбора тела HTTP-ответа scaffolder; не применимо к внутренним file-system
вызовам (уязвимость живёт на уровне Node.js fs, а не HTTP). Отклонено.

**B. Запуск каждой scaffolder-задачи в отдельном ephemeral container**
Изолирует файловую систему на уровне ОС. Устраняет уязвимость независимо от версии
пакетов. Однако требует значительной архитектурной переработки (Job/Pod per task,
отдельный SA, передача артефактов), несоразмерной с Effort:2 данного CVE. Отклонено
как over-engineering; может быть рассмотрено в отдельном предложении.

**C. Запретить загрузку шаблонов с внешних URL и проверять все symlink вручную
в custom middleware**
Не закрывает уязвимость в built-in actions (`debug:log`, `fs:delete`). Отклонено.

## Влияние на платформу

### Migration/миграции
Нет миграций схемы или данных. Изменения ограничены `yarn.lock` и `package.json`.

### Backward compatibility
`@backstage/backend-defaults` 0.12.2 и `plugin-scaffolder-backend` 3.1.1 выходят
как patch-релизы; публичный API не меняется. Существующие шаблоны, не использующие
path-traversal, продолжают работать без изменений.

### Resource impact
Патч не вносит новых зависимостей с высоким потреблением памяти. Тенант `labs`
не затронут (Backstage развёрнут только в `admins`).

### Риски и митигации
| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Peer-dependency конфликт с другими backstage-пакетами при `yarn up` | Средняя | Запустить `yarn backstage-cli versions:check` до merge; при конфликте — точечно поднять транзитивные пакеты |
| Регрессия в scaffolder-шаблонах | Низкая | Playwright smoke-тест шаблона onboarding перед merge |
| ArgoCD sync race при одновременном деплое другого изменения | Низкая | Деплоить в maintenance window; ArgoCD sync с `--prune` |
