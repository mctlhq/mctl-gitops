# Q2: content links fail contrast; footer and colophon link fixes

## Context

Every `<a>` inside `<main>` that carries no class of its own is unstyled. The
vendored design system ships no anchor rule (`public/assets/mctl/global.css` is
28 lines and styles only `box-sizing`, `body` and `::selection`), and
`src/styles/site.css` colours anchors only inside `.site-nav`, `.site-footer`,
`.cta` and `.project-links`. Content links therefore render in the user-agent
default `#0000EE` (visited `#551A8B`). Measured against the dark surface
(`--mctl-surface-dark-bg: #0a0b0d`) that is 2.10:1 unvisited and 1.79:1
visited, below the 4.5:1 that WCAG 2.2 AA 1.4.3 requires; a Lighthouse mobile
run scores `/colophon/` at Accessibility 96 with axe reporting `color-contrast`
2.09 on the table links. The affected links are the Contact block on `/`, both
tables on `/colophon/`, the meta block and "Back to the colophon" link on
`/colophon/journal/*` and `/colophon/adr/*`, and "Back to home" on `/404`.

The same cycle closes three small content defects in the same files: the footer
renders the release label and version with no separating space, the footer's
"Source on GitHub" link points at the organisation rather than this site's
repository, and the two repository/image identifiers in the colophon's "Build
and deploy chain" list are plain text where a reader expects links. The site
exists to be an auditable artifact of the DevLoop, so a colophon that names its
own source and image without linking them is a gap in exactly the page that
claims provenance.

## User stories

- AS a reader on the dark theme I WANT links inside page content to be legible
  against the page background SO THAT I can find and follow them without
  straining, whether or not I have visited them before.
- AS a reader on the light theme I WANT the same links to stay legible SO THAT
  the theme toggle never trades one accessibility defect for another.
- AS a maintainer I WANT the build to fail when the content-link colour is
  removed or reverted to a browser default SO THAT this regression cannot
  return silently.
- AS a reader of the colophon I WANT `github.com/mctlhq/portfolio` and
  `ghcr.io/mctlhq/portfolio` to be links SO THAT I can verify the provenance
  claims the page makes.
- AS a reader of any page I WANT the footer to read `Release 0.1.11` with the
  version linking to that release SO THAT I can see exactly which build I am
  looking at and read its notes.
- AS a reviewer I WANT link health proven by a committed script and a committed
  record SO THAT I do not have to take a broken-link claim on trust.

## Acceptance criteria (EARS)

Colour and contrast

- WHEN a page renders an `<a>` inside `<main>` that carries no class of its own
  THE SYSTEM SHALL colour it with the design system's `--accent` token
  (`#e25a3c` on dark, `#b83d28` on light) rather than leaving it at the
  user-agent default.
- WHILE the document is in either `data-theme` state THE SYSTEM SHALL keep the
  content-link colour at or above 4.5:1 against both `--surface-bg` and
  `--surface-elevated` (measured: dark 5.40:1 and 5.19:1; light 4.81:1 and
  5.11:1).
- WHEN a content link has been visited THE SYSTEM SHALL render it in the same
  `--accent` colour as an unvisited one, so that `#551A8B` (1.79:1 on dark) is
  never used.
- WHEN a content link is hovered THE SYSTEM SHALL render it in
  `--accent-highlight` (`#ff8a6a` on dark, `#9a3220` on light), which measures
  8.53:1 / 8.19:1 on dark and 6.30:1 / 6.70:1 on light against the two
  surfaces.
- WHILE the page is being printed THE SYSTEM SHALL resolve `--accent` to the
  light-theme primary `#b83d28` so printed links measure 5.62:1 against the
  forced white print background instead of 3.64:1.
- WHILE the new rules are in force THE SYSTEM SHALL leave the navigation links
  (`.site-nav a`), the two home-page call-to-action links (`.cta`), the footer
  links (`.site-footer a`) and the work-page project links (`.project-links a`)
  visually unchanged in every state, including `:visited`.

Contrast script

- WHEN `npm test` runs `scripts/check-contrast.mjs` THE SYSTEM SHALL resolve
  the content-link colour declared in `src/styles/site.css` for the normal,
  `:visited` and `:hover` states and check each against `--surface-bg` and
  `--surface-elevated` in both the dark and the light theme.
- IF the content-link colour resolves to a value under 4.5:1 against either
  surface in either theme THEN THE SYSTEM SHALL print the offending pair with
  its measured ratio and exit non-zero.
- IF `src/styles/site.css` declares no colour for the content-link selector, or
  declares one of the browser defaults `#0000EE` or `#551A8B`, THEN THE SYSTEM
  SHALL exit non-zero naming the reverted or missing state.
- WHEN `npm test` runs the unit tests THE SYSTEM SHALL execute a test that
  proves both directions of the assertion: green on the committed stylesheet,
  and red on each of three mutations (link colour set to `#0000EE`, visited
  colour set to `#551A8B`, and the content-link rule deleted outright).

Footer

- WHEN the footer renders THE SYSTEM SHALL emit the English label `Release`
  and the Russian label `Релиз`, then a single space, then the version.
- WHEN the footer renders the version THE SYSTEM SHALL wrap it in a link to
  `https://github.com/mctlhq/portfolio/releases/tag/<version>` where `<version>`
  is the same build-time `package.json` value that already feeds the
  `data-release` hook.
- WHILE the footer template is in the repository THE SYSTEM SHALL contain no
  literal semver string (the existing assertion in `test/colophon.test.ts`
  stays green).
- WHEN the footer renders the source link THE SYSTEM SHALL point it at
  `https://github.com/mctlhq/portfolio` with its label text unchanged
  (`Source on GitHub` / `Исходный код на GitHub`).

Colophon

- WHEN `/colophon/` renders the "Build and deploy chain" list THE SYSTEM SHALL
  render the substring `github.com/mctlhq/portfolio` as a link to
  `https://github.com/mctlhq/portfolio` and the substring
  `ghcr.io/mctlhq/portfolio` as a link to
  `https://github.com/mctlhq/portfolio/packages`, in both the English and the
  Russian list, leaving every other character of those items unchanged.

Link health and parity

- WHEN `scripts/check-links.mjs` runs against a built `dist/` tree THE SYSTEM
  SHALL resolve every internal `href` to a file that exists in the tree and
  request every external `http(s)` URL, failing on any status other than 200.
- IF the release-tag URL returns 404 THEN THE SYSTEM SHALL print a warning and
  continue, because release-please bumps `package.json` in the release pull
  request before the matching tag exists.
- IF the network step itself cannot be completed (DNS failure, timeout, refused
  connection) THEN THE SYSTEM SHALL report the skip and exit zero, mirroring
  the network-failure policy already used by `scripts/vendor-assets.mjs`.
- WHEN the pull request's CI runs THE SYSTEM SHALL execute `check-links.mjs`
  against the built tree so its output appears in the run log.
- WHILE the change is committed THE SYSTEM SHALL carry `docs/link-check.md`,
  recording the exact command, the date of the run and the status of every URL
  checked.
- WHEN `scripts/check-dist.mjs` walks the built tree THE SYSTEM SHALL still find
  equal counts of `class="l en"` and `class="l ru"` in every HTML file and no
  file ending in `.js` under `dist/`.

## Out of scope

Deferred to other cycles in this wave. None of the following is touched by this
proposal:

- The colophon tables' horizontal overflow and the missing scroll affordance.
- Timestamp formatting and lead-time computation in the journal.
- The `/work/` page in its entirety; the only thing this proposal does there is
  pin `.project-links a:visited` so the new rules cannot alter it.
- Navigation state, the skip-link, `role="group"`, `<summary>` headings and
  toggle spacing.
- `og:image`, font preload, `Cache-Control`, the DevLoop diagram and the hero
  name wrap.
- Adopting `.mctl-prose` for page content, and any other typographic change
  (font family, size, margins, `code` and `blockquote` styling).
- Adding or changing any user-facing string other than removing the `:`
  separator in the footer's release line.

## Open questions

Recorded, not blocking; each one is answered below by the reading this proposal
implements.

1. The issue says the footer should have a space added to
   `<span>Release</span>:<span data-release>` (which implies `Release: 0.1.11`)
   but its acceptance criterion 4 quotes the target as `Release 0.1.x` with no
   colon. This proposal follows the acceptance criterion, since that is the
   checkable contract: the separator becomes a single space and the colon is
   dropped, rendering `Release 0.1.11` and `Релиз 0.1.11`. If the reviewer
   prefers the colon, the change is one character in `Footer.astro` and one in
   the test.
2. The issue asks for `ghcr.io/mctlhq/portfolio` to become a link but names no
   target. Measured on 2026-09-11: `https://ghcr.io/mctlhq/portfolio` returns
   404 (it is a registry API host, not a web page) and
   `https://github.com/mctlhq/portfolio/pkgs/container/portfolio` also returns
   404 anonymously, while `https://github.com/mctlhq/portfolio/packages`
   returns 200. This proposal uses the last of the three so acceptance
   criterion 6 can hold. If the container package is later made public under
   its own path, that is a one-line change.
3. The issue offers two approaches for the link colour and asks which was
   chosen to be stated in the pull request body. The implementer cannot edit
   that body (AGENTS.md, "Issue contract"), so the choice and its reasoning are
   recorded in a comment in `src/styles/site.css` and in
   `docs/accessibility-checklist.md`. The choice is the `main a` rule; see
   design.md for why `.mctl-prose` on `<main>` would break acceptance
   criterion 3.
4. The issue's criteria 2 and 6 and its out-of-scope preamble all ask for
   evidence in the pull request body. Per AGENTS.md that evidence instead lands
   in `npm test` (the mutation test), in CI (the link check step) and in two
   committed files (`docs/link-check.md`,
   `docs/accessibility-checklist.md`).
5. Re-running Lighthouse to confirm `/colophon/` moves off 96 needs a browser
   and is therefore a reviewer step, not an acceptance criterion.
