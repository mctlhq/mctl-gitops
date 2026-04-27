# Helm Security Patch: обновление до v4.1.4

## Контекст
В Helm выявлено три уязвимости в версиях v4.0.0–v4.1.3. GHSA-vmx8-mqv2-9gmg допускает запись
произвольных файлов за пределами директории плагина при установке плагина. GHSA-hr2v-4r36-88hr
позволяет выполнить path traversal при распаковке chart'а через специально подготовленное поле
`name` в `Chart.yaml` с dot-segment (например `../`). GHSA-q5jf-9vfq-h4h7 позволяет обойти
проверку подписи плагина — плагины устанавливаются без `.prov` файла даже при включённой
верификации.

Платформа использует Helm для `base-service` chart и ApplicationSet-based деплоев. Helm CLI также
задействован в ArgoCD и в процессах scaffolding. Уязвимость path traversal при chart extraction
особенно критична в контексте GitOps: вредоносный chart в репозитории может привести к записи
файлов на узел. Исправление выпущено в v4.1.4 (patch release, no breaking changes).

## User stories
- AS a platform engineer I WANT Helm upgraded to v4.1.4 SO THAT chart extraction cannot be exploited for path traversal attacks against cluster nodes or the ArgoCD server filesystem.
- AS a security officer I WANT plugin signature verification to actually enforce .prov file checks SO THAT unsigned plugins cannot be installed silently.
- AS a platform engineer I WANT plugin installation to be safe SO THAT malicious plugins cannot write files outside the designated plugin directory.

## Acceptance criteria (EARS)
- WHEN Helm is used in any platform component (ArgoCD, CI, CLI) THE SYSTEM SHALL run version v4.1.4 or newer.
- WHEN a chart archive is extracted and `Chart.yaml` contains a name with dot-segment path characters THE SYSTEM SHALL reject extraction and return an error (GHSA-hr2v-4r36-88hr).
- WHEN a Helm plugin is installed with signature verification enabled THE SYSTEM SHALL require a valid `.prov` file and refuse installation if it is absent or invalid (GHSA-q5jf-9vfq-h4h7).
- WHEN a Helm plugin archive is extracted THE SYSTEM SHALL restrict all extracted files to the designated plugin directory and not write to any path outside it (GHSA-vmx8-mqv2-9gmg).
- WHILE ArgoCD is reconciling Applications that use Helm THE SYSTEM SHALL use only the patched Helm binary bundled with the updated ArgoCD image (or a patched sidecar).
- IF the Helm binary version in the ArgoCD image is older than v4.1.4 THEN THE SYSTEM SHALL not be used for chart rendering until the image is updated.

## Out of scope
- Обновление Helm мажорной версии (v4.x → v5.x).
- Изменение структуры `base-service` chart или values.yaml тенантов.
- Аудит существующих chart'ов на предмет подозрительных имён в Chart.yaml (отдельная задача).
- Обновление ArgoCD до новой мажорной версии ради получения нового Helm (Helm обновляется в рамках существующей ArgoCD версии или патч-версии ArgoCD с новым Helm).
