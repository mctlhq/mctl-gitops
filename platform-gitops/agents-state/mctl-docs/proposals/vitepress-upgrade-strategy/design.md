# Design: vitepress-upgrade-strategy

## Source commits
- n/a — signal from GitHub releases (no sibling-repo git SHA)
- vuejs/vitepress@v2.0.0-alpha.17 (2025-03-19) — latest alpha release
- vuejs/vitepress@v2.0.0-alpha.16 (2025-01-31) — previous alpha

## Текущее состояние документации
- Existing ADR: `context/decisions/0001-vitepress-stack.md` — принял VitePress 1.6, перечислил
  плюсы/минусы, добавил ограничения (нет i18n, нет замены VitePress). **Не содержит** плана
  перехода на VitePress 2.
- `docs/reference/faq.md` — существует, но нет вопроса о версии VitePress.
- **Вывод:** нужен новый ADR и минорное дополнение FAQ.

## Предлагаемое решение

### A. Новый ADR: `context/decisions/0003-vitepress-2-upgrade-strategy.md`
Документирует:
- Текущий statус VitePress 2 (alpha → ожидаем stable).
- Критерии для начала миграции: VitePress 2 выпускает stable release + нет blocker issues.
- Known breaking changes от 1.6 к 2.x: новый sidebar-конфиг, изменения в теме, возможные
  конфиг-файл breaking changes (`config.ts` API).
- Checklist предварительных шагов (создать ветку, сравнить CHANGELOG, обновить config.ts).
- Дата ревью (предлагается: ревьюить при каждом новом alpha/rc release, или через 6 мес).

### B. Добавить Q&A в `docs/reference/faq.md`
Один вопрос: "Which VitePress version does mctl docs use?" с коротким ответом
(версия 1.6, upgrade planned when v2 stable, ссылка на ADR).

### Связанные изменения конфига VitePress
Нет — proposal только документирует план, не выполняет его.

## Альтернативы
1. **Не документировать upgrade strategy, ждать stable** — риск: когда stable придёт, контекст
   принятия решений будет потерян; отклонено.
2. **Перейти на VitePress 2-alpha сейчас** — нарушает принцип stability-first из ADR 0001;
   отклонено.

## Влияние
- VitePress sidebar / nav: не затрагивает (FAQ существует).
- Mermaid диаграммы: не нужны.
- Versioning: нет concept of versioning — применяется к текущей ветке.
