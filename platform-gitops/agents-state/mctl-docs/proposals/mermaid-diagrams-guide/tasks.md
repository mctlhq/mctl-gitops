# Tasks: mermaid-diagrams-guide

- [ ] 1. Создать `docs/reference/diagrams.md` с содержимым из `proposed-content.md`. —
      DoD: файл присутствует, `vitepress build docs` зелёный.
- [ ] 2. Обновить `.vitepress/config.{js,ts,mts}` — добавить sidebar entry под "Reference":
      `{ text: 'Diagram Types', link: '/reference/diagrams' }`. —
      DoD: страница `/reference/diagrams` появляется в левом nav под "Reference".
- [ ] 3. Локально проверить `npm run dev` → открыть `/reference/diagrams` —
      DoD: все mermaid-блоки рендерятся (flowchart, sequence, Wardley Map, etc.),
      beta callouts видны, страница читаема.
- [ ] 4. Cross-link: добавить ссылку на `/reference/diagrams` со страницы `docs/reference/faq.md`
      в секцию о documentation site (или contributing). —
      DoD: ссылка добавлена, резолвится.
- [ ] 5. Аудит существующих `.md` в `docs/` на наличие `htmlLabels` — если найдены, создать
      отдельный fix-PR для их удаления. —
      DoD: либо `htmlLabels` не найдено (OK), либо создан tracking issue/PR.
- [ ] 6. Открыть PR в `mctlhq/mctl-docs`, codex review, мердж. —
      DoD: задеплоено на docs.mctl.ai, `/reference/diagrams` доступна.

## Тесты

- [ ] T1. `vitepress build docs` без ошибок и warnings.
- [ ] T2. Все ссылки в `docs/reference/diagrams.md` резолвятся (нет 404).
- [ ] T3. Каждый mermaid-блок на странице корректно рендерится в браузере (flowchart, sequence,
      architecture; beta-типы — визуально проверить, они могут иметь rendering quirks).
- [ ] T4. `grep -r "htmlLabels" docs/` не возвращает результатов в production-ветке.

## Откат

- Удалить `docs/reference/diagrams.md` и убрать sidebar entry через revert PR.
- Убрать cross-link из FAQ.
- Низкий риск — только markdown + конфиг строка.
