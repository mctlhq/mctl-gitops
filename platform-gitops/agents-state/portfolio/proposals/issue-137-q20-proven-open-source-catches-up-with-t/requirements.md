# Q20: Proven open source catches up with the platform

## Context

The first weekly drift report (mctlhq/portfolio#134, produced by `scripts/org-drift.mjs` from Q19) shows the site's two hand-maintained lists behind the platform. Six bootstrap components in `mctl-gitops/platform-gitops/bootstrap/templates` are not on the "Proven open source" list: `valkey`, `minio`, `otel-collector`, `forgejo`, `reflector`, `zitadel`. Eight organisation repositories have no `/work/` card: `mctl-agent`, `mctl-alice`, `mctl-claude-remote`, `mctl-docs`, `mctl-pairdesk`, `mctl-web`, `newton-mcp-gateway`, `projects-mcp`.

This cycle brings the stack list, the evidence manifest and the drift exemption list in line. Valkey, MinIO and the OpenTelemetry Collector join the list by widening two existing lines (the list stays at nine lines on the home page and thirteen on the approach page). Forgejo, Reflector and ZITADEL become ignored components. Seven repositories become drift exemptions, each with its reason. Afterwards `computeDrift` over the live organisation and mctl-gitops reports exactly one entry: `mctl-agent` under "Repositories with no /work/ card". `mctl-agent` stays in the report on purpose; it gets a card after a rename in a later cycle.

## User stories

- AS a visitor reading "What I run" / "Proven open source" I WANT the list to name the data and telemetry components the platform actually runs SO THAT the list is an honest description of the platform.
- AS the site owner I WANT the weekly drift report to list only real gaps SO THAT one remaining entry (`mctl-agent`) is a signal, not noise.
- AS a reviewer I WANT each exemption to carry its reason in the code and a test that fails if any one is removed SO THAT the exemption list cannot silently drift.

## Acceptance criteria (EARS)

Copy (character for character; EN and RU):

| position | EN old | EN new | RU old | RU new |
|---|---|---|---|---|
| 4 | `CloudNativePG` | `CloudNativePG, Valkey and MinIO` | `CloudNativePG` | `CloudNativePG, Valkey и MinIO` |
| 5 | `VictoriaMetrics, Grafana and Loki` | `VictoriaMetrics, Grafana, Loki and OpenTelemetry` | `VictoriaMetrics, Grafana и Loki` | `VictoriaMetrics, Grafana, Loki и OpenTelemetry` |

1. WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose `ui.detailsRunItems.en` and `ui.detailsRunItems.ru` with nine entries each, where position 4 (index 3) and position 5 (index 4) equal the "new" strings in the table above and the other seven entries are unchanged.
2. WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose `ui.detailsStackItems.en` and `.ru` with thirteen entries each, equal to the nine run items followed by the unchanged `STACK_EXTRA` (`Claude Agent SDK`, `release-please`, `Astro`, `nginx`); `test/approach.test.ts` and `test/ui.test.ts` assert this, including the two new strings at indices 3 and 4 in both languages.
3. WHILE this change is applied THE SYSTEM SHALL leave `STACK_EXTRA`, the header comment of `src/i18n/ui.ts`, and the capabilities body text that mentions CloudNativePG (`ui.ts` ~lines 128 and 142, pinned in `test/ui.test.ts`) byte-identical.
4. WHEN `src/data/stack-evidence.json` is read THE SYSTEM SHALL contain:
   - item 4 with `item` `CloudNativePG, Valkey and MinIO`, evidence = the two existing entries followed by `{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/data/valkey.yaml" }` and `{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/data/minio.yaml" }`, `covers` = `["cloudnative-pg", "cnpg-rbac", "shared-pg", "valkey", "minio"]`;
   - item 5 with `item` `VictoriaMetrics, Grafana, Loki and OpenTelemetry`, evidence = the two existing entries followed by `{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/observability/otel-collector.yaml" }`, `covers` = the five existing entries followed by `otel-collector`;
   - no new item (thirteen items total), all other items unchanged;
   - `ignored_components` = the five existing entries followed by `forgejo`, `zitadel`, `reflector`.
5. WHEN `test/org-drift.test.ts` runs THE SYSTEM SHALL assert `stack-evidence.json` deep-equals the updated `EXPECTED` fixture and that `items[].item` equals `ui.detailsStackItems.en`.
6. WHEN `IGNORED_REPOS` in `scripts/org-drift.mjs` is read THE SYSTEM SHALL equal `['.github', 'portfolio', 'mctl-rule', 'mctl-web', 'mctl-docs', 'mctl-claude-remote', 'mctl-alice', 'projects-mcp', 'newton-mcp-gateway', 'mctl-pairdesk']`, each of the seven new entries followed by its one-line reason as a code comment (reasons in design.md, section C).
7. WHEN `computeDrift` runs over a fixture that reproduces the organisation listing of the implementation date (every repository from `gh repo list mctlhq`, archived ones flagged `archived: true`), the cards parsed by `cardsFromMarkdown` from the committed `src/content/projects/*.en.md`, every evidence path `present`, and the current bootstrap file list of the three `BOOTSTRAP_DIRS` THE SYSTEM SHALL return exactly `{ uncardedRepos: [{ name: 'mctl-agent', private: false, fork: false }], staleCards: [], missingEvidence: [], candidateComponents: [], unknown: [] }`.
8. IF any one of the seven section C entries is removed from `IGNORED_REPOS` THEN THE SYSTEM SHALL fail a test in `test/org-drift.test.ts` (the test removes each one in turn and asserts it reappears under `uncardedRepos`).
9. WHEN `npm run build` runs THE SYSTEM SHALL pass, including `check-no-metrics` (the new copy carries no typed number).
10. WHEN the journal collection is loaded THE SYSTEM SHALL contain one new entry `src/content/journal/<implementation date>-q20-proven-open-source-catches-up-with-the-platform.md` with `status: in_progress`, `issue_opened_at: '2026-10-03T16:45:28Z'`, titles `Q20: Proven open source catches up with the platform` (en) and `Q20: Proven open source догоняет платформу` (ru), and the `seoTitle` and `decided` copy given verbatim in design.md section E.

## Out of scope

- Any change to `scripts/snapshot-metrics.mjs`, `.github/workflows/weekly-refresh.yml`, or the drift logic in `scripts/org-drift.mjs` beyond the `IGNORED_REPOS` list.
- `/work/` cards for any repository in section C, and a card for `mctl-agent` (waits for its rename).
- Renumbering existing cards; any change to the capabilities body copy.
- `STACK_EXTRA` and the `ui.ts` header comment.
- The metrics themselves (`src/data/metrics.json`); the weekly snapshot PR updates them.
- Adding Forgejo, Reflector or ZITADEL to the list.

## Open questions

- The issue supplies the journal title but not the required `decided` text or the `seoTitle` (the computed title "Q20: Proven open source catches up with the platform — Dmitrii Mashkov" exceeds 65 characters, so `test/title.test.ts` requires a `seoTitle`). The proposal authors both in design.md section E; the human reviewer should check that copy before approval.
- The org fixture is a snapshot of `gh repo list mctlhq` as observed on 2026-10-03 (listed in design.md). If the organisation changes before implementation, the implementer re-runs the listing and uses the live result; the expected drift stays "only `mctl-agent`" only if no new uncarded repository appeared. If one did, the implementer reports rather than adds an unapproved exemption.
