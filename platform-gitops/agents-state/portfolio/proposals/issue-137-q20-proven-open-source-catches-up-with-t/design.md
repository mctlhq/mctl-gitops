# Design: issue-137-q20-proven-open-source-catches-up-with-t

## Current state

- `src/i18n/ui.ts` lines 1-28: module-level `RUN_ITEMS_EN` / `RUN_ITEMS_RU` (nine entries each) and `STACK_EXTRA` (`Claude Agent SDK`, `release-please`, `Astro`, `nginx`). `ui.detailsRunItems` (line ~186) spreads the run items; `ui.detailsStackItems` (line ~286) is `[...RUN_ITEMS_*, ...STACK_EXTRA]`. Rendered by `src/pages/index.astro` (lines 67/70, "What I run") and `src/pages/approach.astro` (lines 52/55, "Proven open source"). Index 3 is `CloudNativePG` in both languages; index 4 is `VictoriaMetrics, Grafana and Loki` / `VictoriaMetrics, Grafana и Loki`.
- `test/approach.test.ts` line 110: asserts `detailsStackItems` = `detailsRunItems` + the four extras, length 13. It does not pin the individual run-item strings. `test/ui.test.ts` pins the capabilities body copy (lines ~206/220), which mentions CloudNativePG and is not touched.
- `src/data/stack-evidence.json`: thirteen items `{ item, evidence[{repo,path}], covers[] }` plus `ignored_components` (`image-prune`, `local-path-provisioner`, `academy-postgres-datasource`, `eval-candidates`, `eval-namespace`). `test/org-drift.test.ts` lines 25-50 hold an `EXPECTED` deep-equal fixture and assert `items[].item` equals `ui.detailsStackItems.en`.
- `scripts/org-drift.mjs`: `IGNORED_REPOS = ['.github', 'portfolio', 'mctl-rule']`; `BOOTSTRAP_DIRS` = `core-infra`, `data`, `observability`. `computeDrift` reads `IGNORED_REPOS` from module scope; a bootstrap file is a candidate unless it is in some item's `covers` or in `ignored_components`. The test file's `converged()` fixture already spreads `IGNORED_REPOS` into the org listing, so it keeps working after the list grows.
- Live state observed on 2026-10-03 (via `gh`):
  - `core-infra`: argo-rollouts, argo-workflows-config, argo-workflows, cnpg-rbac, external-secrets, image-prune, local-path-provisioner, reflector, traefik-origin-cert, traefik-origin-pull, vault-auto-unseal, vault-backup, vault-netpol, vault, zitadel
  - `data`: cloudnative-pg, forgejo, minio, shared-pg, temporal-web, temporal, valkey
  - `observability`: academy-postgres-datasource, eval-candidates, eval-namespace, loki-datasource, loki, monitoring-externalsecret, monitoring, otel-collector, promtail-podscrape
  - Org repositories (name, private, fork, archived): portfolio; mctl-gitops; mctl-claude-remote; .github; mctl-telegram; projects-mcp (private); mctl-agents; mctl-academy; mctl-agent; newton-mcp-gateway; mctl-api; mctl-web; mctl-design; mctl-portal; mctl-docs; seerrsense; mctl-alice; mctl-pairdesk; mctl-loyalty; mctl-openclaw (fork, archived); pfeifenpatenschaft-backend (private, archived); mctl-mcp (archived); mctl-rule (private); mctl-trading-data (archived).
  - Cards (`src/content/projects/*.en.md` `repo:`): mctl-academy, mctl-agents, mctl-api, mctl-design, mctl-gitops, mctl-loyalty, mctl-portal, mctl-telegram, seerrsense.
  - The three new evidence paths (`data/valkey.yaml`, `data/minio.yaml`, `observability/otel-collector.yaml`) exist.
- Report #134 matches this: eight uncarded repositories and six candidate components.
- Journal: `src/content.config.ts` `journalSchema` requires `title`, `decided` (bilingual), `issue_opened_at`, `status`, `visibility`; at most one `in_progress` entry (Q19 is `complete`). `test/title.test.ts` requires a `seoTitle` when `title.en + " — Dmitrii Mashkov"` exceeds 65 characters.

## Proposed solution

### A. `src/i18n/ui.ts`

Replace in place, nothing else in the file:

- `RUN_ITEMS_EN[3]`: `'CloudNativePG'` -> `'CloudNativePG, Valkey and MinIO'`
- `RUN_ITEMS_EN[4]`: `'VictoriaMetrics, Grafana and Loki'` -> `'VictoriaMetrics, Grafana, Loki and OpenTelemetry'`
- `RUN_ITEMS_RU[3]`: `'CloudNativePG'` -> `'CloudNativePG, Valkey и MinIO'`
- `RUN_ITEMS_RU[4]`: `'VictoriaMetrics, Grafana и Loki'` -> `'VictoriaMetrics, Grafana, Loki и OpenTelemetry'`

`STACK_EXTRA`, the header comment and the capabilities bodies stay byte-identical. Because `detailsStackItems` spreads the same arrays, the approach page picks up the change automatically.

### B. `src/data/stack-evidence.json`

Item 4 becomes:
```json
{ "item": "CloudNativePG, Valkey and MinIO", "evidence": [{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/data/cloudnative-pg.yaml" }, { "repo": "mctl-gitops", "path": "platform-gitops/infra-components/data/cnpg" }, { "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/data/valkey.yaml" }, { "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/data/minio.yaml" }], "covers": ["cloudnative-pg", "cnpg-rbac", "shared-pg", "valkey", "minio"] }
```
Item 5 becomes:
```json
{ "item": "VictoriaMetrics, Grafana, Loki and OpenTelemetry", "evidence": [{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/observability/monitoring.yaml" }, { "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/observability/loki.yaml" }, { "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/observability/otel-collector.yaml" }], "covers": ["monitoring", "monitoring-externalsecret", "loki", "loki-datasource", "promtail-podscrape", "otel-collector"] }
```
`ignored_components` becomes `["image-prune", "local-path-provisioner", "academy-postgres-datasource", "eval-candidates", "eval-namespace", "forgejo", "zitadel", "reflector"]`. Keep the file's one-item-per-line formatting. The JSON format has no comments; the reasons for `forgejo` (owner chose to keep it off the list), `zitadel` (deployed 2026-10-03; revisit once it is the primary sign-in path) and `reflector` (copies Secrets and ConfigMaps between namespaces; platform glue, not a showcase item) are recorded in the journal `decided` text and in a comment next to the `ignored_components` line of the `EXPECTED` fixture in `test/org-drift.test.ts`.

### C. `IGNORED_REPOS` in `scripts/org-drift.mjs`

Turn the one-line array into a multi-line array; the three existing entries keep their order, then:

```js
export const IGNORED_REPOS = [
  '.github',
  'portfolio',
  'mctl-rule',
  'mctl-web', // the mctl.ai landing page; the site already links mctl.ai
  'mctl-docs', // the docs.mctl.ai sources; already linked from the mctl-api card
  'mctl-claude-remote', // internal operator tooling, not a product
  'mctl-alice', // personal smart-home integration, not built through DevLoop
  'projects-mcp', // private customer-facing service
  'newton-mcp-gateway', // client work
  'mctl-pairdesk', // P2P exchange board; kept off the public portfolio by owner decision
];
```
No other line of `org-drift.mjs` changes.

### D. Tests

- `test/org-drift.test.ts`:
  - Update `EXPECTED` items 4 and 5 and `ignored_components` to match section B.
  - New test `IGNORED_REPOS is the specified list` deep-equals the list above.
  - New fixture `LIVE_ORG_2026_10_03`: the 24 repositories listed in "Current state" with their `private` / `fork` / `archived` flags (re-captured with `gh repo list mctlhq --limit 200 --json name,isArchived,isPrivate,isFork` on the implementation date). `LIVE_BOOTSTRAP`: the 31 file stems listed in "Current state". Cards: `cardsFromMarkdown` over the committed `src/content/projects/*.en.md` (read with `readdirSync`/`readFileSync`, same filter as `main()`), so the test tracks the real cards. Evidence results: every evidence path of the real `stack-evidence.json` as `present`.
  - New test: `computeDrift` over that fixture deep-equals `{ ...EMPTY, uncardedRepos: [{ name: 'mctl-agent', private: false, fork: false }] }`.
  - New test: for each of the seven section C names, remove it from `IGNORED_REPOS` (`splice` on the exported array inside `try`, restore in `finally`), run `computeDrift` on the same fixture, and assert its `uncardedRepos` names include the removed name. This test, together with the deep-equal list test, fails if any one exemption is removed from the source.
  - New test: removing `valkey`, `minio` or `otel-collector` from a copy of the evidence `covers`, or `forgejo` / `zitadel` / `reflector` from a copy of `ignored_components`, makes that name appear in `candidateComponents` (guards section B the same way).
- `test/ui.test.ts`: new test pinning `ui.detailsRunItems.en/ru` length 9, indices 3 and 4 equal to the new strings, and `ui.detailsStackItems.en/ru` length 13 with the same strings at indices 3 and 4.
- `test/approach.test.ts`: the existing prefix/length test stays as is (still valid); add assertions there that `detailsStackItems.en[3]`/`[4]` and `.ru[3]`/`[4]` equal the new strings.

### E. Journal entry

File `src/content/journal/<implementation date YYYY-MM-DD>-q20-proven-open-source-catches-up-with-the-platform.md`, verbatim:

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/137
proposal_slug: issue-137-q20-proven-open-source-catches-up-with-t
status: in_progress
visibility: public
indexing: noindex
title:
  en: "Q20: Proven open source catches up with the platform"
  ru: "Q20: Proven open source догоняет платформу"
seoTitle: "Proven open source catches up with the platform — Dmitrii Mashkov"
decided:
  en: "The first weekly drift report showed the site's two hand-maintained lists behind the platform. On the Proven open source list, the CloudNativePG line now also names Valkey and MinIO, and the observability line now names OpenTelemetry, each backed by a committed evidence path in the platform's GitOps repository; the home page list keeps its nine lines. Forgejo is left off by the owner's choice, Reflector is platform glue rather than a showcase item, and ZITADEL waits until it is the primary sign-in path. Seven repositories that are not portfolio material, from the mctl.ai landing page and the docs sources to client and private work, are now exempt from the report, each with its reason in the code. The one entry the report keeps is mctl-agent, which gets a card after it is renamed."
  ru: "Первый еженедельный отчёт о расхождениях показал, что два списка на сайте, которые ведутся руками, отстают от платформы. В списке Proven open source строка CloudNativePG теперь называет также Valkey и MinIO, а строка наблюдаемости — OpenTelemetry, и у каждого добавления есть закоммиченный путь-подтверждение в GitOps-репозитории платформы; на главной в списке по-прежнему девять строк. Forgejo не включён по решению владельца, Reflector — служебная связка платформы, а не витрина, а ZITADEL подождёт, пока не станет основным способом входа. Семь репозиториев, которые не относятся к портфолио, — от лендинга mctl.ai и исходников документации до клиентской и закрытой работы, — теперь исключены из отчёта, и у каждого исключения причина записана в коде. В отчёте остаётся одна запись — mctl-agent: карточку он получит после переименования."
interventions: []
issue_opened_at: '2026-10-03T16:45:28Z'
---
```

`issue_opened_at` is the `createdAt` of mctlhq/portfolio#137; it is later than Q19's `2026-10-03T13:26:15Z`, so `checkIssueStampOrder` holds. `pr`, `merged_at` and release fields are left to journal-closure. The seoTitle is 65 characters, within the limit.

## Alternatives

1. **Add Valkey, MinIO and OpenTelemetry as new list lines.** Would push "What I run" past nine lines and the approach list past thirteen, breaking the issue's explicit constraint and `test/approach.test.ts`. Dropped.
2. **Add an `ignoredRepos` parameter to `computeDrift` so the removal test need not mutate the exported array.** Cleaner to test, but it changes the drift logic signature, which the issue puts out of scope ("nothing beyond the exemption list"). Dropped in favour of a `splice`/`finally` in the test plus a deep-equal on the list.
3. **Pin the fixture's cards as a literal list instead of parsing the committed project files.** Simpler, but would keep passing if a card were deleted; parsing the real files ties the "only mctl-agent" assertion to the site as built. Dropped.

## Platform impact

- No migrations, no runtime behaviour change. The site gets two longer list lines in both languages; static output only. Page weight change is negligible.
- The weekly workflow's next run reads the new `stack-evidence.json` and `IGNORED_REPOS`; the three new evidence paths exist today, so no "Stack evidence missing" entry is introduced. Expected next report: only `mctl-agent`.
- Risk: a long list line wrapping on narrow screens. The longest new line (`VictoriaMetrics, Grafana, Loki and OpenTelemetry`) is plain text in a `<li>`; wrapping is acceptable. Reviewer step (human): glance at the home and approach pages at a phone width.
- Risk: the org fixture goes stale as the organisation changes. It is a dated snapshot by design (named `..._2026_10_03`); the live report, not this test, tracks future drift.
- Risk: `check-no-metrics` — the new copy contains no digits.
