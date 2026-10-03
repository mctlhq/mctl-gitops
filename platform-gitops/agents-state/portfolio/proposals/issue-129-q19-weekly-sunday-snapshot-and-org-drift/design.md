# Design: issue-129-q19-weekly-sunday-snapshot-and-org-drift

## Current state

- `scripts/snapshot-metrics.mjs` (505 lines) writes `src/data/metrics.json`.
  It has a pure `buildMetrics()` and an impure `main()` that reads `GH_TOKEN`,
  fetches via `ghFetch()` (bounded retries on network error / 5xx, throws
  `GhFetchError` otherwise) and `ghFetchAllPages()` (follows `Link: rel="next"`),
  validates with `metricProblems` from `src/lib/metrics.ts`, and refuses to
  write a partial file. It ends with the hybrid `isEntryPoint()` guard
  (`import.meta.main`, falling back to `realpathSync(process.argv[1])`).
  `package.json` exposes it as `npm run metrics`; nothing schedules it. The
  committed `generated_at` is `2026-09-26T12:39:12.541Z`.
- `.github/workflows/` has `build.yml` (on `pull_request` to `main`; jobs
  `test` and `build`; `actions/checkout@v7`, `actions/setup-node@v4` with
  `node-version: 24`, `npm ci --no-audit --no-fund`), `journal-closure.yml`
  (top-level `permissions: contents: read`, a `concurrency` group,
  `actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0`
  with `owner: mctlhq`, `repositories: portfolio`, contents and pull-requests
  write; PR opened with the App token so it raises `pull_request` events),
  `release-please.yml` and `claude-review.yml` (both human-reserved).
- `test/journal-workflow.test.ts` asserts workflow structure with regexes over
  the file text, no YAML parser. No YAML library is a dependency
  (`package.json`: `astro`, `@astrojs/check`, `@astrojs/sitemap`,
  `@resvg/resvg-wasm`, `typescript`).
- `/work/` cards: `src/content/projects/<slug>.{en,ru}.md`; frontmatter has
  `slug:` and optional `repo:` (`githubUrl.optional()` in
  `src/content.config.ts`). The nine `.en.md` files all carry
  `repo: https://github.com/mctlhq/<name>`.
- "Proven open source": `ui.detailsStackItems.en` in `src/i18n/ui.ts` is
  `[...RUN_ITEMS_EN, ...STACK_EXTRA]` — 9 + 4 = 13 strings, which match the 13
  `items[].item` of the issue's `stack-evidence.json` in order.
- `test/entry-point.test.ts` scans `scripts/*.mjs` for an
  `if (isEntryPoint()) { await main(); }` block and checks the hybrid form, so
  a new script in that shape is covered automatically.
- `package.json` `test` is `node scripts/check-no-metrics.mjs && node scripts/check-contrast.mjs && node --test <explicit list of test files>`;
  test files are `.ts` run by Node 24 type stripping and import `.mjs`
  scripts and `src/i18n/ui.ts` directly (`test/ui.test.ts`).
- Journal: `src/lib/journal.ts` `checkJournalCollection` rejects two
  `in_progress` entries. Today
  `2026-09-14-q17-issue-opened-at-from-a-recorded-source.md` is still
  `in_progress` (closure PR #116 open). See Open questions in requirements.md.

## Proposed solution

### 1. `.github/workflows/weekly-refresh.yml` (new)

Header comment linking `docs/weekly-refresh.md`. Shape:

```yaml
name: weekly-refresh

on:
  schedule:
    - cron: '0 5 * * 0'
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: weekly-refresh-${{ github.repository }}
  cancel-in-progress: false

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          ref: main
          persist-credentials: false

      - uses: actions/setup-node@v4
        with:
          node-version: 24

      - run: npm ci --no-audit --no-fund

      - name: Generate read token
        id: read-token
        uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0
        with:
          app-id: ${{ secrets.AGENTS_APP_ID }}
          private-key: ${{ secrets.AGENTS_APP_PRIVATE_KEY }}
          owner: mctlhq
          permission-contents: read

      - name: Generate write token
        id: write-token
        uses: actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0
        with:
          app-id: ${{ secrets.AGENTS_APP_ID }}
          private-key: ${{ secrets.AGENTS_APP_PRIVATE_KEY }}
          owner: mctlhq
          repositories: portfolio
          permission-contents: write
          permission-pull-requests: write
          permission-issues: write

      - name: Snapshot metrics
        id: snapshot
        env:
          GH_TOKEN: ${{ steps.read-token.outputs.token }}
        run: npm run metrics

      - name: Changed-files guard
        id: guard
        run: |
          status="$(git status --porcelain)"
          if [ -z "$status" ]; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
            echo "::notice::src/data/metrics.json unchanged; no snapshot pull request this week."
          elif [ "$status" = " M src/data/metrics.json" ]; then
            echo "changed=true" >> "$GITHUB_OUTPUT"
          else
            echo "::error::unexpected working-tree changes after the snapshot:"
            printf '%s\n' "$status"
            exit 1
          fi

      - name: Commit and push snapshot branch
        id: push
        if: ${{ steps.guard.outputs.changed == 'true' }}
        env:
          GH_TOKEN: ${{ steps.write-token.outputs.token }}
          APP_SLUG: ${{ steps.write-token.outputs.app-slug }}
        run: |
          set -euo pipefail
          date="$(date -u +%F)"
          title="fix(metrics): weekly snapshot ${date}"
          user_id="$(gh api "/users/${APP_SLUG}%5Bbot%5D" --jq .id)"
          git config user.name "${APP_SLUG}[bot]"
          git config user.email "${user_id}+${APP_SLUG}[bot]@users.noreply.github.com"
          git switch -C fix/weekly-snapshot
          git add src/data/metrics.json
          git commit -m "${title}"
          git push --force "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:refs/heads/fix/weekly-snapshot
          echo "title=${title}" >> "$GITHUB_OUTPUT"

      - name: Open or reuse snapshot pull request and enable auto-merge
        if: ${{ steps.guard.outputs.changed == 'true' }}
        env:
          GH_TOKEN: ${{ steps.write-token.outputs.token }}
          TITLE: ${{ steps.push.outputs.title }}
        run: |
          # builds the body (see "PR body") from src/data/metrics.json with node -e / jq,
          # looks up an open PR: gh pr list -R "$GITHUB_REPOSITORY" --head fix/weekly-snapshot --state open --json number --jq '.[0].number // empty'
          # if empty: gh pr create -R "$GITHUB_REPOSITORY" --base main --head fix/weekly-snapshot --title "$TITLE" --body-file body.md
          # then: gh pr merge "$number" -R "$GITHUB_REPOSITORY" --auto --merge

      - name: Org drift report
        if: ${{ !cancelled() && steps.snapshot.outcome == 'success' }}
        env:
          GH_TOKEN: ${{ steps.read-token.outputs.token }}
          GH_WRITE_TOKEN: ${{ steps.write-token.outputs.token }}
        run: node scripts/org-drift.mjs
```

Notes:
- `persist-credentials: false` keeps any token out of `.git/config` while
  `npm ci` and `npm run metrics` run; the write token reaches git only in the
  push command line.
- The guard is a separate step placed before the push step (AC4). The
  `body.md` scratch file is written after the guard, under `$RUNNER_TEMP`,
  never in the work tree.
- `if: !cancelled() && steps.snapshot.outcome == 'success'` makes the drift
  step run when the PR steps were skipped (or failed after the snapshot), and
  never when the snapshot failed. The job still fails if any earlier step
  failed.
- The existing PR is not edited when reused; its title keeps the date it was
  opened with. The commit message on the branch carries this run's date.

PR body, verbatim (placeholders filled from the new `src/data/metrics.json`;
`<generated_at>` is the ISO string, the others the integer values; a `null`
`services` renders as `null`):

```
Weekly snapshot of src/data/metrics.json, generated by the weekly-refresh workflow.

- generated_at: <generated_at>
- repos: <sources.github.repos>
- commits: <sources.github.commits>
- releases: <sources.github.releases>
- services: <sources.mctl.services>
- devloop_proposals: <sources.mctl.devloop_proposals>

This pull request changes only src/data/metrics.json and is not a DevLoop cycle, so it adds no journal entry.
```

### 2. `scripts/org-drift.mjs` (new)

Header comment in the style of `snapshot-metrics.mjs` explaining the
pure/impure split and the "could not observe is never observed absent" rule.

Constants: `ORG = 'mctlhq'`, `SITE_REPO = 'mctlhq/portfolio'`,
`IGNORED_REPOS = ['.github', 'portfolio', 'mctl-rule']`,
`BOOTSTRAP_DIRS = ['platform-gitops/bootstrap/templates/core-infra', 'platform-gitops/bootstrap/templates/data', 'platform-gitops/bootstrap/templates/observability']`,
`DRIFT_LABEL = 'weekly-drift'`, `ISSUE_TITLE = 'Weekly drift report'`.

Input shapes (a failed read is a value, not an absent list):
- `orgRepos`: `Array<{ name, archived, private, fork }>` or
  `{ unknown: string }` (error message).
- `cards`: `Array<{ slug, repo }>` (cards without `repo` are not included).
- `evidence`: parsed `stack-evidence.json`.
- `evidenceResults`: `Array<{ repo, path, result: 'present'|'absent'|'unknown', error? }>`
  in evidence-file order.
- `bootstrapFiles`: `string[]` or `{ unknown: string }`.

Exports:
- `computeDrift(inputs)` -> `{ uncardedRepos: [{name, private, fork}],
  staleCards: [{slug, name, reason: 'archived'|'not found'}],
  missingEvidence: [{item, repo, path}], candidateComponents: string[],
  unknown: [{what, error}] }`. Deterministic: repos sorted by name, cards by
  slug, evidence in file order, components sorted. When `orgRepos` is
  unknown, `uncardedRepos` and `staleCards` are `[]` and `unknown` gets
  `{ what: 'org repository listing for mctlhq', error }`; likewise for
  `bootstrapFiles` (`what: 'mctlhq/mctl-gitops bootstrap listing'`) and each
  unknown evidence result (`what: 'mctlhq/<repo>/<path>'`). Card matching
  strips a trailing `/` and compares to `https://github.com/mctlhq/<name>`.
- `isNoDrift(drift)` -> true only when all five arrays are empty.
- `renderIssueBody(drift, date)` (`date` = `YYYY-MM-DD`). Throws if
  `isNoDrift(drift)` (an all-empty report is never rendered).
- `cardsFromMarkdown(files: Array<{ text }>)` -> parses `slug:` and `repo:`
  from the frontmatter block (between the first two `---` lines) with
  line regexes.
- `ghRequest(url, { token, fetchImpl = fetch, method, body, retries = 3, backoffMs = 300 })`
  -> `{ status, json, headers }`; retries network errors and 5xx, never
  throws on a status (callers classify).
- `listOrgRepos({ token, fetchImpl, retries, backoffMs })` -> follows
  `rel="next"` from `/orgs/mctlhq/repos?per_page=100&type=all`; any non-200
  page, network failure or non-array body throws, naming the page URL. No
  partial result is ever returned (AC9).
- `classifyEvidence(response)` -> `present` for 200 with an object or array
  body, `absent` for 404, `unknown` otherwise.
- `listBootstrapFiles({ token, fetchImpl, ... })` -> for each
  `BOOTSTRAP_DIRS` entry, `GET /repos/mctlhq/mctl-gitops/contents/<dir>`;
  requires 200 and an array; keeps `type === 'file'` names ending `.yaml`,
  strips the extension; any failure throws.
- `syncDriftIssue({ drift, date, token, fetchImpl })` -> lists
  `GET /repos/mctlhq/portfolio/issues?state=open&labels=weekly-drift&per_page=100`,
  drops entries with `pull_request`, picks the lowest number (warns about
  others). Drift/unknown: `PATCH` body of that issue or `POST` a new issue
  `{ title: 'Weekly drift report', body, labels: ['weekly-drift'] }`. No
  drift: if one exists, `POST .../comments` `{ body: 'No drift as of <date>.' }`
  then `PATCH { state: 'closed', state_reason: 'completed' }`. Any non-2xx
  throws. Returns an action string (`created|updated|closed|none`) for tests.

`main()`: reads `GH_TOKEN`, `GH_WRITE_TOKEN` (missing either -> exit 1),
collects the inputs (each listing wrapped in try/catch into
`{ unknown: err.message }`), reads cards from `src/content/projects/*.en.md`
and `src/data/stack-evidence.json` locally, calls `computeDrift`, logs a
summary, calls `syncDriftIssue` with today's UTC date, and sets
`process.exitCode = 1` when `drift.unknown.length > 0` or the issue sync
threw. Ends with the hybrid `isEntryPoint()` and
`if (isEntryPoint()) { await main(); }`.

Issue body, verbatim structure (sections without entries omitted):

```
Weekly drift report generated by the weekly-refresh workflow on <YYYY-MM-DD>. Acting on it is a separate DevLoop cycle; this issue changes nothing by itself.

## Repositories with no /work/ card
- mctlhq/<name> (private, fork)

## /work/ cards pointing at a repository that is archived or gone
- <slug>: mctlhq/<name> (archived | not found)

## Stack evidence missing
- <item>: mctlhq/<repo>/<path>

## Platform components not on the "Proven open source" list
- <basename>

## Unknown
- <what could not be read>: <error>
```

Rendering details: sections joined by one blank line; the annotation on a
repository line is ` (private, fork)`, ` (private)`, ` (fork)` or nothing;
the card line uses exactly one of `(archived)` or `(not found)`; the body ends
with a single newline.

### 3. `src/data/stack-evidence.json` (new)

Exactly this content, copied character for character (with a trailing
newline); the test compares parsed values:

```json
{
  "items": [
    { "item": "k3s on Hetzner, provisioned with OpenTofu", "evidence": [{ "repo": "mctl-gitops", "path": "infrastructure/k3s-preview" }, { "repo": "mctl-gitops", "path": "infrastructure/k3s-prod" }], "covers": [] },
    { "item": "ArgoCD, Argo Workflows and Argo Rollouts", "evidence": [{ "repo": "mctl-gitops", "path": "platform-gitops/argocd" }, { "repo": "mctl-gitops", "path": "platform-gitops/argo-workflows" }, { "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/core-infra/argo-rollouts.yaml" }], "covers": ["argo-workflows", "argo-workflows-config", "argo-rollouts"] },
    { "item": "HashiCorp Vault with External Secrets", "evidence": [{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/core-infra/vault.yaml" }, { "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/core-infra/external-secrets.yaml" }], "covers": ["vault", "vault-auto-unseal", "vault-backup", "vault-netpol", "external-secrets"] },
    { "item": "CloudNativePG", "evidence": [{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/data/cloudnative-pg.yaml" }, { "repo": "mctl-gitops", "path": "platform-gitops/infra-components/data/cnpg" }], "covers": ["cloudnative-pg", "cnpg-rbac", "shared-pg"] },
    { "item": "VictoriaMetrics, Grafana and Loki", "evidence": [{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/observability/monitoring.yaml" }, { "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/observability/loki.yaml" }], "covers": ["monitoring", "monitoring-externalsecret", "loki", "loki-datasource", "promtail-podscrape"] },
    { "item": "Traefik and cert-manager", "evidence": [{ "repo": "mctl-gitops", "path": "infrastructure/k3s-preview/extra-manifests/traefik-helmchartconfig.yaml.tpl" }, { "repo": "mctl-gitops", "path": "infrastructure/k3s-preview/extra-manifests/cert-manager-helmchartconfig.yaml.tpl" }], "covers": ["traefik-origin-cert", "traefik-origin-pull"] },
    { "item": "Temporal", "evidence": [{ "repo": "mctl-gitops", "path": "platform-gitops/bootstrap/templates/data/temporal.yaml" }], "covers": ["temporal", "temporal-web"] },
    { "item": "Backstage", "evidence": [{ "repo": "mctl-gitops", "path": "platform-gitops/backstage" }], "covers": [] },
    { "item": "Cloudflare", "evidence": [{ "repo": "mctl-gitops", "path": "infrastructure/cloudflare" }], "covers": [] },
    { "item": "Claude Agent SDK", "evidence": [{ "repo": "mctl-agents", "path": "pyproject.toml" }], "covers": [] },
    { "item": "release-please", "evidence": [{ "repo": "portfolio", "path": "release-please-config.json" }], "covers": [] },
    { "item": "Astro", "evidence": [{ "repo": "portfolio", "path": "astro.config.mjs" }], "covers": [] },
    { "item": "nginx", "evidence": [{ "repo": "portfolio", "path": "nginx.conf" }], "covers": [] }
  ],
  "ignored_components": ["image-prune", "local-path-provisioner", "academy-postgres-datasource", "eval-candidates", "eval-namespace"]
}
```

### 4. Tests

`test/weekly-refresh-workflow.test.ts` — reads the workflow text; regexes in
the style of `test/journal-workflow.test.ts`, plus a helper that splits the
`steps:` block into step chunks on `^      - ` so per-step assertions are
scoped to one step:
- cron `'0 5 * * 0'` and `workflow_dispatch:` (AC1);
- exactly one `permissions:` occurrence, followed only by `contents: read`
  (AC2); every `create-github-app-token` `uses:` line carries
  `@bcd2ba49218906704ab6c1aa796996da409d3eb1`, and there are exactly two
  (AC2);
- read-token chunk: `owner: mctlhq`, `permission-contents: read`, no
  `repositories:`, and its only `permission-` key; write-token chunk:
  `repositories: portfolio` plus the three write permissions (AC3);
- index of the guard chunk (contains `git status --porcelain`) is less than
  the index of the chunk containing `git push`, and no earlier chunk contains
  `git push` (AC4);
- `fix(metrics): weekly snapshot ` with `date -u +%F`, `fix/weekly-snapshot`,
  `--auto --merge`, and no `--squash` / `--rebase` (AC5);
- concurrency group and `cancel-in-progress: false`; snapshot step uses
  `npm run metrics` with the read token; drift step uses
  `node scripts/org-drift.mjs` with both tokens and
  `steps.snapshot.outcome == 'success'`.

`test/org-drift.test.ts` — imports from `../scripts/org-drift.mjs` and
`ui` from `../src/i18n/ui.ts`:
- evidence file deep-equals the expected object inlined in the test, and
  `items.map(i => i.item)` deep-equals `ui.detailsStackItems.en` (AC6);
- converged fixture built from the real evidence file: all evidence present,
  bootstrap files = union of all `covers` plus `ignored_components`, org
  repos = card repos plus `IGNORED_REPOS` plus one archived uncarded repo ->
  `isNoDrift` true (AC7);
- three mutations, each asserting `deepEqual` of the whole drift object with
  exactly that one entry (AC7) — removing the corresponding branch makes the
  entry vanish and the test fail;
- one `unknown` evidence result only -> `unknown.length === 1`,
  `isNoDrift` false (AC8); `orgRepos: { unknown }` and
  `bootstrapFiles: { unknown }` each produce an `Unknown` entry (AC8);
- `listOrgRepos` with an injected `fetchImpl` returning page 1 (200 + `Link`
  rel="next") then page 2 (500 or network error), `backoffMs: 0` ->
  rejects, never resolves to page 1's repos (AC9); a two-page success
  concatenates both;
- `classifyEvidence` for 200 / 404 / 500 / malformed;
- `renderIssueBody` full-string equality for a drift with all five sections,
  and for one with only `Unknown` (empty sections omitted); throws on no
  drift (AC10);
- `syncDriftIssue` with an injected fetch recording calls: create when none
  open, update when one open, comment+close on no drift, no call beyond the
  list when no drift and none open; PR entries in the issue list ignored.

### 5. `docs/weekly-refresh.md` (new)

Sections: Schedule (Sunday 05:00 UTC plus manual dispatch); Tokens (read:
org-wide, contents read only, because the snapshot counts private
repositories and the drift report reads mctl-gitops; write: portfolio only,
contents/pull-requests/issues write, minted from the mctl-agents App so the PR
raises `pull_request` events and gets `build` and Claude review; never
`GITHUB_TOKEN`); Snapshot pull request (branch `fix/weekly-snapshot` owned and
force-updated by the workflow, title `fix(metrics): weekly snapshot YYYY-MM-DD`,
auto-merge with merge commit completes only after the required `build` check
and approving review, a requested-changes review holds it; release-please
then opens a patch release PR that a human still merges, so the deploy
decision stays manual; no journal entry); Drift issue (one open issue
labelled `weekly-drift`, body replaced each run, closed with a comment when
there is no drift; Unknown section and job failure on any failed read);
Keeping `src/data/stack-evidence.json` in sync (every change to
`RUN_ITEMS_EN` / `STACK_EXTRA` in `src/i18n/ui.ts` needs the matching
`items[]` edit in the same PR, enforced by `test/org-drift.test.ts`; how
`covers` and `ignored_components` work); Manual run
(`gh workflow run weekly-refresh.yml -R mctlhq/portfolio`); Operator setup
(allow auto-merge in repository settings, create the `weekly-drift` label,
App installation must cover all org repositories).

### 6. Journal entry

File `src/content/journal/<implementation date YYYY-MM-DD>-q19-weekly-sunday-snapshot-and-org-drift-report.md`:

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/129
proposal_slug: issue-129-q19-weekly-sunday-snapshot-and-org-drift
status: in_progress
visibility: public
indexing: noindex
title:
  en: "Q19: weekly Sunday snapshot and org drift report"
  ru: "Q19: еженедельный воскресный снимок и отчёт о расхождениях с организацией"
seoTitle: "Weekly snapshot and org drift report — Dmitrii Mashkov"
decided:
  en: "The home page Snapshot was refreshed only when someone remembered to run the metrics script by hand, and the two hand-maintained lists on the site, the Work cards and the Proven open source list, had no check against the organisation at all. This cycle adds a workflow that runs every Sunday morning and on demand. It regenerates the snapshot with a read-only token that can see the whole organisation, and when the file changed it opens one pull request containing only that file, with auto-merge on, so the snapshot lands through the same build check, review and release path as any other change while the release itself is still merged by a person. The same run compares the organisation and the platform's GitOps repository against the Work cards and a new committed evidence manifest for the Proven open source list, and keeps exactly one open issue describing the differences, closing it when there are none. A source that cannot be read fails the run and is listed as unknown, never as no drift. No visible copy changed: acting on the report is a later cycle."
  ru: "Блок Snapshot на главной обновлялся только тогда, когда кто-то вспоминал запустить скрипт метрик вручную, а два списка на сайте, которые ведутся руками, — карточки Work и список Proven open source, — вообще никак не сверялись с организацией. Этот цикл добавляет workflow, который запускается каждое воскресенье утром и по запросу. Он пересобирает снимок токеном только на чтение, которому видна вся организация, и если файл изменился, открывает один pull request только с этим файлом и включённым auto-merge, так что снимок проходит ту же проверку сборки, ревью и путь релиза, что и любое другое изменение, а сам релиз по-прежнему мержит человек. Тот же запуск сравнивает организацию и GitOps-репозиторий платформы с карточками Work и новым закоммиченным манифестом подтверждений для списка Proven open source и держит ровно один открытый issue с описанием расхождений, закрывая его, когда расхождений нет. Источник, который не удалось прочитать, валит запуск и помечается как неизвестный, а не как отсутствие расхождений. Видимые тексты не менялись: действовать по отчёту будет следующий цикл."
interventions: []
issue_opened_at: '2026-10-03T13:26:15Z'
---
```

`issue_opened_at` is the `created_at` of mctlhq/portfolio#129, copied to the
second (it is later than Q18's `2026-09-13T22:48:25Z`, so
`checkIssueStampOrder` holds). `pr`, `merged_at` and the release fields are
left to journal-closure.

## Alternatives

1. **Commit the snapshot through the contents API from a Node script** (as
   `scripts/close-journal.mjs` does) instead of `git commit` / `git push`.
   Avoids git identity setup, but the issue's AC4 is phrased around a
   `git push` step guarded by `git status --porcelain`, and the porcelain
   guard is the simplest proof that nothing besides `metrics.json` ships.
   Dropped.
2. **Use a YAML parser (`yaml` package) in the workflow test.** More robust
   key lookups, but adds a dependency and a lockfile regeneration (AGENTS.md's
   `--package-lock-only` rule) for one test, and the existing
   `test/journal-workflow.test.ts` sets the text-check precedent. Dropped; the
   step-chunk splitter gives per-step scoping without it.
3. **Two workflows (snapshot, drift) or two jobs.** Separate jobs would need
   to mint tokens twice and pass "snapshot succeeded" across jobs; one job
   with step outcomes expresses "drift runs unless the snapshot failed"
   directly. Dropped.
4. **Reuse `ghFetch` by importing from `snapshot-metrics.mjs`.** Out of
   scope (no changes to that script, and it is not exported); `org-drift.mjs`
   carries its own small `ghRequest` with an injectable `fetchImpl`, which
   the pagination test needs anyway.

## Platform impact

- No runtime or image change; the Docker build and nginx are untouched. The
  new JSON file is not imported by any page.
- GitHub API cost: roughly one org listing, ~20 evidence reads and 3 directory
  listings per week on top of the existing snapshot cost; well inside App
  rate limits.
- Operator preconditions (not commits): App installation granted read access
  to all org repositories; repository "Allow auto-merge" enabled;
  `weekly-drift` label created; Q17 closure PR #116 merged before the
  implementation PR (two `in_progress` journal entries fail the build).
- Risks and mitigations:
  - Write token exposure: checkout uses `persist-credentials: false`; the
    token is used only in the push command and `gh`/script env.
  - Unexpected files committed: porcelain guard fails the job before push,
    and only `src/data/metrics.json` is `git add`ed.
  - Silent "no drift" on outage: every failed read becomes an `Unknown` entry
    and exit 1, covered by tests.
  - Weekly PR noise: the branch is fixed and force-updated, so there is at
    most one open snapshot PR; auto-merge only completes after `build` and an
    approving review.
  - Missing `weekly-drift` label: the operator creates it before the first
    run; if issue creation is rejected, `syncDriftIssue` throws and the job
    fails visibly rather than reporting success.
