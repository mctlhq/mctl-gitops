# Tasks: helm-security-patch

- [ ] 1. Инвентаризация всех точек использования Helm в платформе — DoD: составлен список (ArgoCD image, ClusterWorkflowTemplate image refs, Backstage scaffolder actions) с текущими версиями Helm в каждой.
- [ ] 2. Определить версию ArgoCD, содержащую Helm v4.1.4 (проверить официальный changelog ArgoCD) — DoD: зафиксирован минимальный тег образа ArgoCD с Helm >= v4.1.4.
- [ ] 3. Обновить тег образа ArgoCD в `platform-gitops/apps/` (зависит от 2) — DoD: image tag обновлён, PR содержит только изменение версии.
- [ ] 4. Обновить image references в ClusterWorkflowTemplate файлах в `platform-gitops/argo-workflows/cluster-templates/` для всех steps, использующих helm CLI (зависит от 1) — DoD: все helm-использующие steps указывают на образ с Helm v4.1.4.
- [ ] 5. Проверить и обновить Backstage scaffolder templates если helm используется в actions (зависит от 1) — DoD: либо подтверждено отсутствие helm в scaffolder, либо обновлён соответствующий image/version.
- [ ] 6. Создать единый PR с изменениями из шагов 3–5 — DoD: PR создан, diff содержит только обновления версий, CI зелёный.
- [ ] 7. После merge выполнить ArgoCD sync и проверить состояние Applications (зависит от 6) — DoD: все затронутые ArgoCD Applications в состоянии `Synced` + `Healthy`.
- [ ] 8. Верифицировать версию Helm в задеплоенных компонентах (зависит от 7) — DoD: `helm version` в ArgoCD pod и в workflow executor pod возвращает v4.1.4 или новее.

## Тесты
- [ ] T1. Проверить версию Helm в ArgoCD: `kubectl exec -n argocd <argocd-server-pod> -- helm version` — ожидается v4.1.4+.
- [ ] T2. Выполнить ArgoCD dry-run sync для нескольких ключевых Applications (включая `base-service` для тенанта `admins`) — ожидается успешный рендеринг без ошибок.
- [ ] T3. Запустить тестовый Workflow, использующий helm CLI step (если такой есть в `cluster-templates/`) — ожидается статус `Succeeded`.
- [ ] T4. Убедиться, что все ArgoCD Applications остаются `Synced` + `Healthy` через 15 минут после обновления ArgoCD.
- [ ] T5. Проверить отсутствие ошибок в логах ArgoCD repo-server, связанных с Helm rendering: `kubectl logs -n argocd -l app.kubernetes.io/component=repo-server --since=15m | grep -i "helm\|error"`.

## Откат
1. Выполнить `git revert <commit-sha>` коммита с обновлением image tags в mctl-gitops.
2. Смержить revert-коммит.
3. ArgoCD автоматически откатит образы к предыдущим версиям через App-of-Apps sync.
4. Если ArgoCD сам обновился — проверить, что после revert его образ также вернулся к предыдущему тегу.
5. Верифицировать откат: повторить T1 с ожидаемой старой версией Helm.
