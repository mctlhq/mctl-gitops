# Tasks: vitepress-upgrade-strategy

- [ ] 1. Создать `context/decisions/0003-vitepress-2-upgrade-strategy.md` по шаблону ADR.
      Контент — из `proposed-content.md` (секция ADR). — DoD: файл присутствует, содержит
      критерии перехода и checklist.
- [ ] 2. Обновить `docs/reference/faq.md` — добавить Q&A секцию о версии VitePress.
      Контент — из `proposed-content.md` (секция FAQ patch). — DoD: вопрос и ответ присутствуют,
      ссылка на ADR резолвится.
- [ ] 3. Локально проверить `npm run dev` → открыть `/reference/faq` — DoD: рендерится, новый
      блок Q&A виден, mermaid-блоки (если есть) рендерятся корректно.
- [ ] 4. Cross-link: убедиться, что `context/decisions/0001-vitepress-stack.md` ссылается на
      новый ADR 0003 как "See also". — DoD: cross-reference добавлен.
- [ ] 5. Открыть PR в `mctlhq/mctl-docs`, codex review, мердж. — DoD: задеплоено на docs.mctl.ai.

## Тесты

- [ ] T1. `vitepress build docs` без ошибок и warnings.
- [ ] T2. Ссылка `/reference/faq#vitepress-version` резолвится (якорь существует).
- [ ] T3. Ссылка из FAQ на ADR `context/decisions/0003-…` корректна (или даёт понятную ошибку
      если ADR не публикуется в публичном docs).

## Откат

- Удалить `context/decisions/0003-...md` и reverт FAQ изменений через revert PR.
- Убрать cross-link из ADR 0001.
- Нулевой риск — только markdown.
