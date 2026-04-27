# Tasks: mermaid-dep-security

- [ ] 1. Создать `context/decisions/0002-mermaid-dep-security.md` по шаблону ADR (см. `context/decisions/README.md`).
      Вставить контент из `proposed-content.md` (секция ADR). — DoD: файл присутствует, статус "accepted" или "proposed".
- [ ] 2. Добавить секцию "Known dependency advisories" в `docs/reference/troubleshooting.md`.
      Использовать контент из `proposed-content.md` (секция troubleshooting patch). — DoD: секция появляется на странице.
- [ ] 3. Проверить `package.json` mctl-docs на наличие `overrides`/`resolutions` для lodash-es.
      Если нет — добавить `"overrides": { "lodash-es": "^4.18.1" }` как временный mitigation.
      — DoD: `npm audit` не показывает CVE-2026-4800, CVE-2026-2950 как high/critical.
- [ ] 4. Локально проверить `npm run dev` и `vitepress build docs` после overrides — DoD: сборка зелёная, mermaid рендерится.
- [ ] 5. Открыть PR в `mctlhq/mctl-docs`, codex review, мердж. — DoD: задеплоено на docs.mctl.ai.

## Тесты

- [ ] T1. `vitepress build docs` без ошибок и warnings.
- [ ] T2. `npm audit --audit-level=high` не показывает CVE-2026-4800, CVE-2026-2950 (после overrides pin).
- [ ] T3. Страница `docs/reference/troubleshooting` рендерится с новой секцией; ссылка на ADR резолвится корректно.

## Откат

- Удалить ADR-файл и секцию из troubleshooting.md через revert PR.
- Убрать `overrides` из package.json если pin вызывает breaking changes в mermaid.
- Низкий риск — только markdown + package.json patch.
