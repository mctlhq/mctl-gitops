# Design: issue-21-docs-license-file-reference-in-readme

## Current state
Read directly from the `mctlhq/mctl-design` clone:

- `LICENSE` (repo root, 11358 bytes) is the standard Apache License 2.0 text.
- `README.md` already ends with:
  ```
  ## License

  Apache-2.0 — see [LICENSE](./LICENSE).
  ```
  (confirmed via `git log -p --follow -- README.md`: this section has been
  present since the squashed initial history, unchanged through PR #18).
- `package.json` (root) declares `"license": "Apache-2.0"`, and the same
  field is present and identical in `packages/tokens/package.json`,
  `packages/css/package.json`, `packages/ui/package.json`, and
  `apps/storybook/package.json`.
- `scripts/check-versions.mjs` is the existing precedent for a small,
  dependency-free Node script that walks `packages/*` and `apps/*`
  `package.json` files and fails with a clear message on drift. It is wired
  into `package.json`'s `"check:versions"` script and into
  `.github/workflows/ci.yml` as the final CI step.
- `.github/workflows/ci.yml` runs on `pull_request` and `push: [main]`,
  executing install, lint, typecheck, build, build:storybook, then
  `check:versions`, in that order.

So the issue's literal ask ("link README to LICENSE") is already implemented
in the current codebase. There is no README content change required.

## Proposed solution
Add a new, narrowly-scoped verification script, `scripts/check-license.mjs`,
modeled directly on `scripts/check-versions.mjs`'s structure and tone:

1. Assert `LICENSE` exists at the repository root.
2. Assert `README.md` contains a Markdown link whose target is `./LICENSE`
   (or `LICENSE`) — e.g. a regex/string search for `](./LICENSE)` /
   `](LICENSE)` within a `## License` (or `# License`) section.
3. Assert the root `package.json` `license` field is a non-empty string, and
   that every non-private workspace package (`packages/*`, `apps/*`) that
   declares a `license` field matches the root value — reusing the same
   package-discovery loop already written in `check-versions.mjs`.
4. Exit non-zero with a clear, actionable message on any failure (mirroring
   `check-versions.mjs`'s `console.error` + `process.exit(1)` pattern).

Wire it in exactly like `check:versions`:
- `package.json`: add `"check:license": "node scripts/check-license.mjs"`.
- `.github/workflows/ci.yml`: add a `Check license reference` step after
  `Check lockstep versions`, running `pnpm check:license`.

This keeps the change additive and low-risk: no existing script, workflow
step, or README prose is modified — only a new script and two small
additions (one `package.json` script entry, one CI step) are introduced.

## Alternatives
1. **Do nothing / close as already-resolved.** Technically correct (the
   issue's literal ask is met), but produces no artifact for the Tier 2
   implementer to build and leaves the passing state unguarded against
   future regressions (e.g. someone renaming `LICENSE` to `LICENSE.md`
   during an unrelated cleanup, which would silently break the existing
   link). Rejected because the pipeline this issue is testing expects a
   real, mergeable change, and a guard has genuine long-term value.
2. **Add a markdown-link-checker (e.g. `lychee` or
   `markdown-link-check`) as a new dev dependency and CI job.** More
   general (catches all broken links, not just LICENSE), but heavier:
   new external dependency, new tool to configure/maintain, and broader
   blast radius (would need allowlisting for any intentionally-external or
   flaky links) for a repo whose CLAUDE.md conventions favor small, precise
   tooling (`scripts/check-versions.mjs` is the existing pattern). Rejected
   as disproportionate to the issue's scope; can be proposed separately if
   broader link-rot protection is wanted.
3. **Modify `README.md` anyway** (e.g. reword the existing License section,
   add a badge). Rejected: nothing is factually wrong with the current
   section, and CLAUDE.md/README conventions don't call for badges; changing
   working prose without a concrete defect would be unmotivated churn.

## Platform impact
- **Migrations**: none — no database, service, or deployment changes;
  `mctl-design` is a static packages/Storybook repo built centrally via
  mctl-gitops (per this repo's CLAUDE.md), unaffected by this change.
- **Backward compatibility**: fully additive. No published package's public
  API, CSS, or tokens change. `pnpm check:versions` behavior is untouched.
- **Resource impact**: negligible — one more fast, dependency-free Node
  script step in CI (sub-second execution, same class as
  `check-versions.mjs`).
- **Risks**:
  - False positive if a future, legitimate README restructuring changes the
    License section heading or link format. Mitigation: keep the check's
    string/regex match intentionally loose (accepts `./LICENSE` or
    `LICENSE`, any heading level) and give a precise error message pointing
    at what the script expected, so a maintainer can fix it in seconds.
  - Script duplicates some package-walking logic from `check-versions.mjs`.
    Mitigation: keep the shared logic small and inline (as
    `check-versions.mjs` itself does) rather than introducing a shared
    module now; note as a possible follow-up refactor if a third such
    script appears.
