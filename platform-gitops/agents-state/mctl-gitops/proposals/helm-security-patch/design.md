# Design: helm-security-patch

## Текущее состояние
Согласно `context/architecture.md`, платформа использует Helm charts (base-service, openclaw,
custom), ArgoCD ApplicationSet для генерации Apps и `helm-charts/base-service` как generic chart.
Helm бинарный файл присутствует в нескольких местах:
1. Внутри образа ArgoCD (используется для рендеринга Helm-based Applications).
2. В CI/CD пайплайнах (Argo Workflow steps, Backstage scaffolder).
3. Локально у platform engineers (вне scope этого предложения — мануальное обновление).

Текущие версии v4.0.0–v4.1.3 подвержены GHSA-vmx8-mqv2-9gmg, GHSA-hr2v-4r36-88hr,
GHSA-q5jf-9vfq-h4h7.

## Предлагаемое решение
Обновление Helm до v4.1.4 во всех платформенных точках использования.

**Шаг 1: ArgoCD**
ArgoCD включает Helm как часть своего официального образа. Необходимо проверить, какая версия
ArgoCD содержит Helm v4.1.4, и обновить тег образа ArgoCD в `platform-gitops/apps/`. Если
текущая версия ArgoCD уже выпустила patch с Helm v4.1.4 — достаточно обновить тег. Если нет —
ждать upstream ArgoCD patch или использовать custom init-container с патченым Helm (нежелательно).

**Шаг 2: Argo Workflow steps**
Workflow steps, которые вызывают `helm` CLI (например build/package steps), должны использовать
образ с Helm v4.1.4. Обновить image reference в соответствующих ClusterWorkflowTemplate в
`platform-gitops/argo-workflows/cluster-templates/`.

**Шаг 3: Backstage scaffolder templates**
Если scaffolder использует helm CLI в skeleton actions — обновить образ или pinned version в
`platform-gitops/backstage-templates/`.

Все изменения оформляются как git commit в mctl-gitops; ArgoCD применяет через App-of-Apps.
ADR-0001 (App-of-Apps pattern) не нарушается.

## Альтернативы

### 1. Блокировать chart extraction через OPA/Gatekeeper admission webhook
Ввести политику, которая проверяет имена chart'ов перед применением. Не закрывает уязвимость
в самом Helm (extraction происходит до admission), не закрывает plugin уязвимости.
Отброшено: неполное покрытие.

### 2. Отключить плагины Helm на уровне конфигурации
Отключить возможность установки Helm плагинов в CI и ArgoCD окружении. Частично снижает риск
GHSA-vmx8-mqv2-9gmg и GHSA-q5jf-9vfq-h4h7, но не закрывает path traversal при chart extraction.
Отброшено: не является полным исправлением, плагины могут понадобиться.

### 3. Обновить только ArgoCD, пропустить CI образы
Минимизировать scope — обновить Helm только в ArgoCD. Path traversal при chart extraction
остаётся возможным в CI workflow steps. Отброшено: неполное покрытие attack surface.

## Влияние на платформу

### Migration
Нет миграции данных. Patch release (v4.1.4) декларирован без breaking changes. Существующие
`values.yaml` и chart структуры остаются неизменными.

### Backward compatibility
v4.1.4 полностью обратно совместим с v4.1.x. Все существующие Helm charts (`base-service` и
кастомные) продолжат рендериться без изменений.

### Resource impact
Обновление бинарного файла Helm не влияет на потребление CPU/памяти в runtime. Образы ArgoCD
и workflow steps могут незначительно изменить размер. Тенант `labs` не затронут напрямую:
ArgoCD и Argo Workflows работают в тенанте `admins`. Деплои в тенант `labs` через ArgoCD
продолжатся штатно.

### Риски и митигации
- **Риск:** Версия ArgoCD, задеплоенная на платформе, ещё не выпустила patch с Helm v4.1.4.
  **Митигация:** Проверить матрицу совместимости ArgoCD ↔ Helm; при необходимости дождаться
  ближайшего ArgoCD patch release или использовать временный workaround с кастомным образом.
- **Риск:** Workflow steps используют pinned образы, не управляемые через central values.
  **Митигация:** Провести grep по `cluster-templates/` на предмет всех image references с Helm.
- **Риск:** Регрессия в рендеринге Helm chart'ов после обновления.
  **Митигация:** ArgoCD dry-run sync перед применением; наличие отката через git revert.
