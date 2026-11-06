# Design: issue-200-add-the-agent-trailer-check-to-portfolio

## Current state

- `.github/workflows/` holds five workflows: `build.yml`,
  `claude-review.yml`, `journal-closure.yml`, `release-please.yml`,
  `weekly-refresh.yml`. There is no `agent-trailer-check.yml`, and nothing in
  `src/`, `docs/`, `scripts/` or `test/` mentions the Agent trailer.
- `AGENTS.md` ("Bootstrap boundary (ADR-0001)") reserves for humans only
  `README.md`, `AGENTS.md`, `LICENSE`, `.gitignore`, the release-please
  config and manifest, repository settings, secrets and labels, and three
  loop-gating files: `.github/workflows/claude-review.yml`,
  `.github/workflows/release-please.yml`, `.github/dependabot.yml`. It states
  that `build.yml` is not reserved and that every other file is written by
  the implementer. A new `agent-trailer-check.yml` is therefore
  implementer-owned under AGENTS.md as written.
- `src/content/adr/0001-bootstrap-boundary.md` (status `accepted`, date
  `2026-09-11`) still says in its Decision section that humans own
  `.github/**`. That already contradicts AGENTS.md (narrowed after #21) and
  the implementer-written `build.yml`, `journal-closure.yml` and
  `weekly-refresh.yml`; adding a fourth implementer-written workflow would
  widen the contradiction. ADR bodies are validated by `adrBodyProblems` in
  `src/lib/adr.ts` (five sections in order, each with an `.l.en` heading
  span, an `.l.ru` heading span, an English `<div class="l en">` block and a
  Russian `<div class="l ru" lang="ru">` block), tested in
  `test/adr.test.ts`. The ADR schema is in `src/content.config.ts`
  (`status`, `date`, optional `supersedes`).
- Workflow files are pinned by structural text tests without a YAML parser:
  `test/journal-workflow.test.ts` and `test/weekly-refresh-workflow.test.ts`
  read the file with `readFileSync` and assert with regexes. Every test file
  is listed explicitly in the `test` script of `package.json`; a file not
  listed there does not run. `build.yml` runs `npm run build`, whose
  `prebuild` runs `npm test`.
- Journal: `docs/journal.md` requires one entry per cycle, created by the
  cycle with `status: in_progress` and no release evidence. The schema
  (`journalSchema` in `src/content.config.ts`) is strict: `service`,
  `issue`, `proposal_slug`, `status`, `visibility`, `title` (en/ru),
  optional `seoTitle`, `indexing`, `decided` (en/ru), `issue_opened_at`,
  `interventions`. At most one entry may be `in_progress`; none currently is
  (`grep '^status: in_progress' src/content/journal/*` is empty). The latest
  entry is `2026-11-05-q24-home-snippet-in-both-scripts.md` (Q24), so this
  cycle is Q25. Issue #200 was created at `2026-11-06T15:00:45Z`
  (`gh issue view 200 --json createdAt`), later than issue #195's stamp, so
  `checkIssueStampOrder` holds.
- Reference caller: `mctlhq/mctl-web`, `mctlhq/mctl-api` and
  `mctlhq/mctl-agents` `.github/workflows/agent-trailer-check.yml` on `main`
  have identical content (same md5). It differs from the issue's snippet
  only by a two-line comment after `name:`. Per the issue, the existing
  caller wins.
- Reusable workflow at
  `mctlhq/.github/.github/workflows/agent-trailer.yml@afb2328...`: input
  `enforce` (boolean, default `false`); classifies only the final paragraph
  of each commit message, and only when every line of that paragraph is a
  trailer; values `claude|codex|agy|none`; merge commits and bot authors are
  skipped; label is `agent:<value>`, `agent:mixed` or `agent:unknown`;
  labels are created on demand with `gh label create --force`; fork pull
  requests get only the report. With `enforce: false` the Enforce step never
  runs.
- Recent implementer commits (PR #196) end with
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and no `Agent:`
  line, so without an explicit requirement this cycle's PR would be labelled
  `agent:unknown`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/portfolio/values.yaml`: the site is
  tenant `labs`, service `portfolio`, image tag `0.1.54`. This change touches
  no deployed configuration; the file is cited only to confirm nothing here
  depends on it.
- `gh label list -R mctlhq/portfolio --search agent`: no `agent:*` labels
  exist yet (only `agents:intake`, `spike:scout`); the reusable workflow
  creates them on first run.
- mctl MCP tools were not called: nothing in this proposal reads or changes
  runtime state.

## Proposed solution

### 1. The caller workflow

Create `.github/workflows/agent-trailer-check.yml` with exactly this content
(copied from `mctlhq/mctl-web` main; trailing newline after the last line):

```yaml
name: Agent trailers

# Reports which assistant each commit declares through its Agent trailer and
# sets the agent:* label (mctlhq/.github#316). Warning only for now.

on:
  pull_request:
    types: [opened, reopened, synchronize, ready_for_review]

permissions: {}

jobs:
  agent-trailer:
    permissions:
      issues: write
      pull-requests: write
    uses: mctlhq/.github/.github/workflows/agent-trailer.yml@afb232838c79279141d293e6ce311f3ec664bfbc
```

No `with:` block: `enforce` keeps its default `false`, which is the
warn-only mode the issue requires. Byte identity with the other 18 callers
keeps a later org-wide flip a mechanical change.

### 2. Structural test

Add `test/agent-trailer-workflow.test.ts`, in the style of
`test/weekly-refresh-workflow.test.ts` (no YAML parser, `readFileSync` +
regex), and append it to the `test` script in `package.json`. It asserts:

- the file exists and the trigger block equals
  `on:\n  pull_request:\n    types: [opened, reopened, synchronize, ready_for_review]\n`;
- the only top-level permissions line is `permissions: {}`, and the job's
  permissions are exactly `issues: write` and `pull-requests: write`
  (`permissions:` occurs exactly twice in the file);
- exactly one `uses:` line, equal to
  `mctlhq/.github/.github/workflows/agent-trailer.yml@afb232838c79279141d293e6ce311f3ec664bfbc`,
  with a 40-hex ref;
- no `enforce` substring and no `with:` key anywhere (warn-only);
- no `steps:`, `runs-on:` or `secrets:` (the caller stays a thin
  pass-through).

Each assertion is a fixed string or anchored regex, so a weakening edit
(for example `enforce: false` explicitly, or a tag ref) is caught as well.

### 3. Commit trailer

Every commit the implementer makes in this cycle ends with a final trailer
paragraph containing `Agent: claude`, for example:

```
Co-Authored-By: Claude <noreply@anthropic.com>
Agent: claude
```

Any `Proposal:` line stays in its own earlier paragraph as in PR #196, or is
moved into the final paragraph; either way every line of the final
paragraph must be a `Key: value` trailer, otherwise the reusable workflow
ignores the block and reports `unknown`.

### 4. ADR-0001 amendment

In `src/content/adr/0001-bootstrap-boundary.md` replace only the paragraph
inside the Decision section's English block and the paragraph inside its
Russian block. Frontmatter (`id`, `title`, `seoTitle`, `status: accepted`,
`date: '2026-09-11'`), headings and every other section are unchanged.

English, replacing the current Decision paragraph, character for character:

> Humans create and edit only the wiring: the repository itself, README.md, AGENTS.md, LICENSE, .gitignore, the release-please configuration and manifest, repository settings, secrets, labels, the branch ruleset, and the three files that gate the loop itself — .github/workflows/claude-review.yml, .github/workflows/release-please.yml and .github/dependabot.yml. Every other file — the Astro project, Dockerfile, nginx.conf, content, journal, ADRs, scripts and every other workflow under .github/workflows, among them build.yml and agent-trailer-check.yml — arrives through a DevLoop cycle, and every deployment action goes through the mctl MCP tools.

Russian, replacing the current Decision paragraph, character for character:

> Человек создаёт и правит только обвязку: сам репозиторий, README.md, AGENTS.md, LICENSE, .gitignore, конфигурацию и манифест release-please, настройки репозитория, секреты, метки, правила ветвления и три файла, которые охраняют сам цикл, — .github/workflows/claude-review.yml, .github/workflows/release-please.yml и .github/dependabot.yml. Все остальные файлы — проект Astro, Dockerfile, nginx.conf, контент, журнал, ADR, скрипты и все прочие воркфлоу в .github/workflows, в том числе build.yml и agent-trailer-check.yml, — появляются через цикл DevLoop, а любое действие по развёртыванию выполняется инструментами mctl MCP.

(The leading `> ` is quoting in this document only; the ADR paragraphs are
plain text, one line each, as today.)

### 5. Journal entry

Add `src/content/journal/2026-11-06-q25-agent-trailer-check.md`:

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/200
proposal_slug: issue-200-add-the-agent-trailer-check-to-portfolio
status: in_progress
visibility: public
indexing: noindex
title:
  en: "Q25: Commits say which assistant wrote them"
  ru: "Q25: коммиты называют ассистента, который их написал"
seoTitle: "Agent trailer check — Dmitrii Mashkov"
decided:
  en: "A new workflow, .github/workflows/agent-trailer-check.yml, calls the organisation's shared Agent trailer check on every pull request, byte for byte the same caller the other 18 mctlhq repositories already run. It reads the Agent: trailer each commit declares and sets one agent:* label on the pull request. It only warns: a commit without a trailer counts as unknown, never as human, and nothing fails until enforcement is decided organisation-wide. The trailer is self-declared and is not an approval signal. This cycle's own commits carry Agent: claude. ADR-0001 now names the three files a human still reserves, as AGENTS.md already did, instead of all of .github, so the new workflow arriving through the DevLoop is inside the boundary rather than an exception to it."
  ru: "Новый воркфлоу .github/workflows/agent-trailer-check.yml вызывает общую для организации проверку трейлера Agent на каждом pull request — байт в байт тот же вызов, что уже работает в остальных 18 репозиториях mctlhq. Он читает трейлер Agent:, который объявляет каждый коммит, и ставит на pull request одну метку agent:*. Проверка только предупреждает: коммит без трейлера считается unknown, а не человеческим, и ничего не падает, пока включение строгого режима не решено на уровне организации. Трейлер заявляется самим автором и не является сигналом одобрения. Коммиты этого цикла несут Agent: claude. ADR-0001 теперь называет три файла, которые по-прежнему остаются за человеком, как это уже делал AGENTS.md, вместо всего каталога .github, поэтому новый воркфлоу, пришедший через DevLoop, находится внутри границы, а не является исключением из неё."
issue_opened_at: '2026-11-06T15:00:45Z'
interventions: []
---
```

No body, no `pr`, `release`, `merged_at`, `released_at` or `deployed_at`;
the `journal-closure` workflow fills those after release.

## Alternatives

- **Copy the issue's snippet verbatim (without the comment).** Dropped: the
  issue itself says the existing caller wins, and a byte-different caller
  would make the org-wide enforcement flip a non-mechanical diff here.
- **Supersede ADR-0001 with a new ADR-0007 instead of amending it.** Dropped
  for now: the drift already exists since #21, AGENTS.md narrowed the
  reservation in place, and a superseded ADR-0001 would push the site's
  founding decision off the accepted list for a wording fix. Kept as an open
  question for the owner.
- **Leave ADR-0001 untouched and rely on AGENTS.md.** Dropped: the issue
  asks that ADR-0001 stay consistent with the new file, and the published
  ADR would then claim a human owns a file the journal says the DevLoop
  wrote.
- **No structural test.** Dropped: the warn-only requirement must be
  checkable by a committed artefact, and the repository already pins its
  other non-reserved workflows this way.

## Platform impact

- No migration, no deploy, no image or runtime change; the static site
  rebuilds only the ADR-0001 page and the new journal entry.
- CI: one extra job per pull request event, a few seconds, `timeout-minutes:
  5` in the reusable workflow. Permissions are scoped to the job; top-level
  token has none.
- Release-please and journal-closure pull requests are opened by a bot or
  App; bot-authored commits are classified `bot` and produce no label, which
  is expected behaviour, not a failure.
- Risk: the GitHub App token the implementer pushes with may lack the
  `workflows` permission, in which case the push of a file under
  `.github/workflows/` is rejected. Precedent says it has it
  (`journal-closure.yml` and `weekly-refresh.yml` were added by the DevLoop);
  if not, the cycle stops at push and is retried after the permission is
  granted, not worked around by a human commit.
- Risk: a commit without the trailer (for example a shepherd review fix)
  yields `agent:mixed` or `agent:unknown`. Warn-only, so no merge is
  blocked; the reviewer notes it.
- Risk: the reusable workflow pin is a third-party ref inside the org; it is
  pinned by full SHA, same as everywhere else.
