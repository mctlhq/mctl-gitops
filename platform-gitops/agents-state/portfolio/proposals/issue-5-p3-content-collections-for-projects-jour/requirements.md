# P3: Typed content collections for projects, journal and ADRs, seeded with the cycles that already happened

## Context

`portfolio` today has no content layer at all: `src/` holds four components,
one layout, two pages, `src/i18n/ui.ts` and `src/styles/site.css`, and there is
no `src/content/` directory and no `src/content.config.ts`. Everything the site
renders is hard-coded in `.astro` files. The repository's whole claim — stated
in `README.md` and fixed by the bootstrap boundary in `AGENTS.md` — is that the
site is *evidence* of the mctl DevLoop rather than a description of it. That
evidence is the work journal and the architecture decision records, and they
cannot be evidence while they are untyped prose that no build step checks.

This proposal defines three Astro content collections (`projects`, `journal`,
`adr`) with zod schemas strict enough that the build refuses malformed or
hand-computed records, adds two dependency-free helper modules
(`src/lib/journal.ts`, `src/lib/adr.ts`), and seeds the collections with the
four DevLoop cycles that have already completed (mctl-agents#330,
mctl-api#281, portfolio#3 and portfolio#4), three accepted ADRs, and one
bilingual project pair that proves the `projects` schema. Nothing is rendered:
pages for journal, ADRs and project cards are P7 and P5. The point of this
cycle is that the content model and its machine checks exist before any page
depends on them, and that the manual interventions of the first four cycles are
recorded while they are still verifiable.

## User stories

- AS the site's author I WANT the journal and the ADRs to be typed content with
  a build-time schema SO THAT a malformed or back-dated record fails CI instead
  of shipping as plausible-looking prose.
- AS the site's author I WANT lead time and intervention counts computed from
  timestamps at build time SO THAT no number on the site can be typed by hand,
  as `AGENTS.md` requires.
- AS a reviewer of a `feat/agents-*` pull request I WANT the ADR structure
  (five sections, both languages) enforced by `astro build` SO THAT I review
  the content of a decision record rather than its shape.
- AS a reader of the site (in a later cycle) I WANT every project, journal
  entry and ADR to exist in both English and Russian SO THAT the bilingual
  promise in `AGENTS.md` holds for content as well as for `src/i18n/ui.ts`.
- AS the implementer of a later cycle I WANT `getCollection('journal')` to
  return fully typed entries SO THAT P7 renders pages without re-deriving the
  shape of the data.

## Acceptance criteria (EARS)

### Collections and schemas

- WHEN `astro sync`, `astro check`, `astro dev` or `astro build` runs THE
  SYSTEM SHALL load three collections declared in `src/content.config.ts` —
  `projects` from `src/content/projects/**`, `journal` from
  `src/content/journal/**`, `adr` from `src/content/adr/**` — each through the
  `glob` loader of Astro's content layer.
- WHILE a `projects` entry is being validated THE SYSTEM SHALL require
  `slug`, `lang` (`'en' | 'ru'`), `name`, `group` (`'platform' | 'product'`),
  `order` (integer), `repo` (a `https://github.com/...` URL), `stack`
  (non-empty array of strings) and `summary` (single-line string), SHALL allow
  an optional `links` array of `{ label, url }`, and SHALL reject any other
  frontmatter key.
- WHILE a `journal` entry is being validated THE SYSTEM SHALL require
  `service` (`'portfolio' | 'mctl-agents' | 'mctl-api'`), `issue` (GitHub URL),
  `proposal_slug`, `visibility` (`'public' | 'private'`), `title` (`{ en, ru }`),
  `decided` (`{ en, ru }`) and `issue_opened_at`, SHALL allow optional `pr`
  (GitHub URL), `release` (bare semver, no `v` prefix, per `AGENTS.md`),
  `proposal_approved_at`, `merged_at`, `released_at`, `deployed_at`, SHALL
  default `interventions` to `[]`, and SHALL require every element of
  `interventions` to carry `what`, `why` and `at`.
- WHILE a `journal` entry is being validated THE SYSTEM SHALL reject any
  unknown frontmatter key, so that a field named `lead_time`, `lead_time_hours`
  or `manual_interventions` fails the build because those values are computed
  at build time and never written by hand.
- WHILE a `journal` or `adr` timestamp is being validated THE SYSTEM SHALL
  accept only a quoted ISO 8601 string that carries a timezone (`Z` or
  `±HH:MM`), and SHALL reject an unquoted YAML timestamp with a message that
  names quoting as the fix, because YAML parses an unquoted timestamp into a
  `Date` and silently discards the offset.
- WHILE an `adr` entry is being validated THE SYSTEM SHALL require `id`
  (positive integer), `title` (`{ en, ru }`), `status` (`'proposed' |
  'accepted' | 'superseded' | 'deprecated'`), `date` (quoted `YYYY-MM-DD`) and
  `visibility`, SHALL allow an optional `supersedes` (integer), and SHALL
  reject any unknown key.
- IF an `adr` entry's `id` does not match the four-digit prefix of its filename
  THEN THE SYSTEM SHALL fail the build naming both values.

### Build-time body validation

- WHEN the `adr` collection loads THE SYSTEM SHALL check every entry body for
  the five sections `Context`, `Decision`, `Consequences`, `Drivers`,
  `Revisit criteria`, as `##` headings in that order, and SHALL check that each
  section contains at least one `.l.en` block and at least one `.l.ru` block.
- IF any ADR body is missing a section, carries the five sections out of order,
  or lacks an English or Russian block inside a section THEN THE SYSTEM SHALL
  fail `astro build`, `astro sync` and `astro check` with one error that lists
  every offending file and every offending section, not just the first.
- WHEN `npm run check` runs THE SYSTEM SHALL run `astro sync` (which executes
  the collection loaders and therefore every schema and body validation) and
  then `astro check`, and SHALL exit non-zero if either step fails.

### Helpers

- WHEN `leadTimeHours(entry)` is called with an entry whose `issue_opened_at`
  and `deployed_at` are both set THE SYSTEM SHALL return the difference in
  hours as an unrounded `number`.
- IF `deployed_at` is absent, `null` or empty THEN `leadTimeHours` SHALL return
  `null`.
- IF `deployed_at` precedes `issue_opened_at` THEN `leadTimeHours` SHALL throw,
  because that ordering is a data error rather than a renderable value.
- WHEN `interventionCount(entry)` is called THE SYSTEM SHALL return the length
  of `interventions`, and `0` when the field is absent.
- WHILE `src/lib/journal.ts` and `src/lib/adr.ts` are being imported THE SYSTEM
  SHALL require no Astro runtime: neither module imports `astro:content`,
  `astro/loaders` or `zod`, so both are importable by plain `node --test`.

### Seeds

- WHEN the collections load THE SYSTEM SHALL find exactly three ADRs
  (`0001-bootstrap-boundary.md`, `0002-static-astro-no-client-bundles.md`,
  `0005-self-contained-runtime-assets.md`), each `status: accepted`,
  `date: '2026-09-11'`, `visibility: public`, with numbers 0003 and 0004 left
  unused and reserved for the custom-domain and no-analytics decisions.
- WHEN the collections load THE SYSTEM SHALL find exactly four `journal`
  entries, all `visibility: public`, one per completed cycle
  (mctl-agents#330, mctl-api#281, portfolio#3, portfolio#4), each file named
  `YYYY-MM-DD-<slug>.md` where the date is the UTC date of its
  `issue_opened_at`.
- WHILE the four seeded journal entries are being written THE SYSTEM SHALL take
  every timestamp, PR and release value from the verified table in `design.md`
  (sourced from the GitHub issue, pull request and release APIs and from the
  proposals' `.status.yaml` in `mctl-gitops`) and SHALL NOT invent a value for
  any field it cannot source.
- WHILE the seeded journal entries are being written THE SYSTEM SHALL record
  every manual intervention listed in `design.md` — two on each of the
  mctl-agents#330 and mctl-api#281 entries, three on the portfolio#3 entry,
  four on the portfolio#4 entry — each with `what`, `why` and an `at`
  timestamp anchored to a verifiable artifact.
- WHILE the portfolio#3 and portfolio#4 entries are being written THE SYSTEM
  SHALL leave `deployed_at` unset, because `MCTL_ONBOARDED` is not yet set and
  the site has never been deployed; consequently `leadTimeHours` returns `null`
  for those two entries and a number for the other two.
- WHEN the collections load THE SYSTEM SHALL find one project pair,
  `src/content/projects/mctl-api.en.md` and `mctl-api.ru.md`, sharing
  `slug: mctl-api` and differing only in `lang` and in the language of `name`,
  `summary`, `links[].label` and the body.
- WHILE any seeded content is being written THE SYSTEM SHALL keep it free of
  credentials, of internal hostnames beyond the platform's public ones, and of
  numeric metrics in frontmatter, since metrics come from the snapshot by
  `repo` in P8b.

### Development affordance and output shape

- WHILE `astro dev` is running THE SYSTEM SHALL serve one throwaway page that
  loads all three collections and lists their entry counts.
- WHEN `astro build` runs THE SYSTEM SHALL emit no page for that throwaway
  route.
- WHEN `astro build` completes THE SYSTEM SHALL leave `dist/` with zero `.js`
  files and exactly one distinct inline `<script>` body of at most 400 bytes,
  so `scripts/csp-hash.mjs` still succeeds unchanged.
- WHEN `npm test` runs THE SYSTEM SHALL execute `node --test` over
  `test/journal.test.ts` and `test/adr.test.ts` and exit non-zero on failure.

## Out of scope

- Rendering journal pages, ADR pages or an index of either (P7).
- Rendering project cards and the `<details>` expansion of project bodies (P5).
- `src/data/metrics.json` and the metrics snapshot joined to projects by `repo`
  (P8b). No numeric metric enters project frontmatter here.
- ADR-0003 (custom domain) and ADR-0004 (no analytics): written when those
  decisions are executed. The numbers stay unused.
- Any `src/i18n/ui.ts` string, navigation entry or layout change. `Base.astro`,
  `Nav.astro`, `Footer.astro` and `site.css` are untouched.
- Deployment, onboarding, `MCTL_ONBOARDED`, custom domains and anything behind
  an mctl MCP tool.
- Backfilling `deployed_at` for the two portfolio cycles (there has been no
  deployment) and any journal entry for this P3 cycle itself (it belongs to the
  next cycle's entry, by definition).
- An RSS or JSON feed of the journal.

## Open questions

- The issue lists the two R-round interventions under "On the R1/R2 entries",
  one of which names `mctl-api#282` specifically. Taken literally, that
  mctl-api-specific review re-request is also recorded on the mctl-agents#330
  entry. This proposal follows the issue literally, because the two cycles
  shared one merge window and the ledger's value is fidelity; a reviewer who
  prefers it recorded only on the mctl-api entry should say so at approval.
- The issue gives no `at` timestamp for individual interventions, only an
  "as of" time for the first block. `design.md` fixes one value per
  intervention, each anchored to a verifiable artifact (a commit, a submitted
  review, a merged PR). Two of them — "rewrote the pull request description"
  and the two review re-requests — have no artifact of their own in the GitHub
  API, so they are anchored to the artifact they produced, and the anchor is
  documented per row. A reviewer should check those three rows specifically.
- `deployed_at` for the two platform cycles is taken from the `mctl-gitops`
  commit that set the running image tag (`chore: bump admins/mctl-agents to
  1.41.0` and `... mctl-api to 4.41.0`), which is the platform's earliest
  verifiable deploy event. The ArgoCD sync completion time would be strictly
  more accurate but is not recoverable from the repositories. The definition is
  written into `AGENTS.md`-adjacent documentation in `src/content/adr` prose,
  not into the schema.
- The issue asks for "EN and RU variants inside `.l.en` / `.l.ru` blocks" but
  does not say whether the five ADR *headings* are bilingual too. Leaving them
  English-only would trip the `claude-review.yml` convention "any user-facing
  string present in only one of EN/RU". This proposal makes each heading carry
  both spans (`## <span class="l en">Context</span><span class="l ru">Контекст</span>`)
  and keys the build-time check on the English token.
- The issue does not supply the Russian copy that `AGENTS.md`'s issue contract
  asks for. `design.md` supplies the full EN and RU copy for all three ADRs,
  the four journal entries and the project pair, so the implementer translates
  nothing. A Russian-reading reviewer should check that copy rather than
  assume it.
- `release` for the portfolio cycles is inferred by time ordering: PR #12
  merged 00:11:53Z and release `0.1.0` published 00:17:50Z; PR #16 merged
  01:39:35Z and `0.1.1` published 01:42:36Z. No other commits fall between, so
  the mapping is unambiguous, but it is an inference, not an API field.
