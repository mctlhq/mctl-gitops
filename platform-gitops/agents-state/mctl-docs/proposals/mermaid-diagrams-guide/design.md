# Design: mermaid-diagrams-guide

## Source commits
- n/a — signal from GitHub releases (no sibling-repo git SHA)
- mermaid-js/mermaid@11.14.0 (2025-04-01) — Wardley Maps beta, TreeView, Neo look, SVG ID fixes
- mermaid-js/mermaid@11.13.0 (2025-03-09) — Venn beta, Ishikawa beta, htmlLabels deprecated

## Текущее состояние документации
- `docs/reference/faq.md` — FAQ общего назначения; нет ничего о mermaid.
- `docs/reference/troubleshooting.md` — существует; нет секции о диаграммах.
- `docs/mcp/examples.md` — примеры MCP, может содержать диаграммы но это не diagram guide.
- **Страница отсутствует** — нужно новое местоположение `docs/reference/diagrams.md`.
- Также нужна запись в `.vitepress/config.ts` (или `config.mts`) — sidebar "Reference" section.

## Предлагаемое решение

### Новая страница: `docs/reference/diagrams.md`

Содержимое (детали в `proposed-content.md`):
1. **Вводный параграф** — mermaid в mctl-docs, текущая версия, ссылка на upstream.
2. **Таблица типов диаграмм** — название, стабильность (stable/beta), краткое описание, пример кода.
3. **Примеры кода** — flowchart (basic), sequence diagram (платформенный flow), architecture diagram
   (с mctl компонентами), Wardley Map (beta example), Venn (beta), Ishikawa (beta).
4. **htmlLabels deprecation notice** — что deprecated, как мигрировать.
5. **Neo look / стиль** — описание нового стиля по умолчанию.
6. **Best practices** — когда использовать mermaid vs когда достаточно bullet list.

### Обновление `.vitepress/config.ts`
Добавить entry в sidebar "Reference":
```ts
{ text: 'Diagram Types', link: '/reference/diagrams' }
```

## Альтернативы
1. **Добавить в FAQ отдельные Q&A о диаграммах** — не масштабируется при наличии >5 типов;
   отклонено.
2. **Ссылаться только на mermaid upstream docs** — contrib останется без примеров в контексте
   mctl платформы; отклонено.

## Влияние
- VitePress sidebar: да — добавить строку в "Reference" section в `.vitepress/config.ts`.
- Mermaid диаграммы: да — страница сама содержит mermaid-блоки (проверить рендеринг).
- Versioning: нет — применяется к текущей ветке, будет обновляться с bumps mermaid.
