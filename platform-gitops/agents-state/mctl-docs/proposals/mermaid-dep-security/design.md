# Design: mermaid-dep-security

## Source commits
- n/a — signal from CVE advisories, not a git commit in sibling repos
- CVE-2026-4800: lodash-es vulnerability (version-status: unverified, see advisory published ~2026-04)
- CVE-2026-2950: lodash-es vulnerability (version-status: unverified, see advisory published ~2026-04)
- Reference: https://security.snyk.io/package/npm/mermaid

## Текущее состояние документации
- `docs/security/authentication.md` — покрывает auth/JWT/OAuth платформы; не затрагивает зависимости docs-сайта.
- `docs/security/authorization.md` — RBAC платформы; аналогично не релевантно.
- `docs/reference/troubleshooting.md` — существует, но нет секции о known dependency advisories.
- `context/decisions/` — есть только 0001-vitepress-stack.md; явного ADR о безопасности зависимостей нет.
- **Вывод:** страница отсутствует; решение по CVE не задокументировано нигде.

## Предлагаемое решение

Два артефакта:

### A. Новый ADR: `context/decisions/0002-mermaid-dep-security.md`
Внутренний (read-only) ADR, фиксирующий:
- Описание CVE-2026-4800 и CVE-2026-2950 в lodash-es.
- Оценку attack surface (static site, no user input → low real-world risk).
- Решение: upgrade mermaid до версии ≥ 11.15.0 (или той, что зафиксирует lodash-es ≥ 4.18.1)
  как только выйдет, либо pin lodash-es через `overrides` в package.json.
- Дату решения и ответственного.

### B. Добавить секцию в `docs/reference/troubleshooting.md`
Публичная заметка "Known dependency advisories" для transparency — короткая таблица CVE + status + link to ADR.

### Связанные изменения конфига VitePress
Нет (чисто markdown изменения).

## Альтернативы

1. **Только ADR, без публичной записи** — скрывает информацию от tenant-аудиторов; отклонено: прозрачность важна.
2. **Заменить mermaid на другой рендерер** — нарушает ADR 0001 (высокая стоимость миграции); отклонено.

## Влияние
- VitePress sidebar / nav config: не затрагивает (troubleshooting.md уже в nav).
- Mermaid диаграммы: не нужны.
- Versioning: нет concept of versioning в mctl-docs — ADR + troubleshooting update применяется к текущей ветке.
