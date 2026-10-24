# Design: issue-119-docs-observability-three-consistency-nit

## Current state
- `docs/reference/telemetry-attributes.md` (454 lines) is the catalog. It is a plain
  VitePress Markdown page; site config is `docs/.vitepress/config.ts`.
- **Naming rules**, rule 6 (around line 44): "**Identifiers end in `id`; human-readable
  names end in `name`.** If both exist, emit both ... A leaf may be `_id` when the
  identifier qualifies a sub-entity of the level above it - `mctl.workflow.run_id` ...
  `mctl.edge.request_id` likewise. Upstream has the same shape (`k8s.pod.uid`). Promote it
  to its own level only when the sub-entity gains attributes of its own."
  Nothing covers `.number`, yet `mctl.issue.number` and `mctl.pr.number` (int, reserved;
  correlation identity table, lines ~111-112) end in `number`. The "Upstream namespaces
  deliberately not adopted" table (line ~66) already justifies `mctl.pr.number` as an
  integer PR number versus upstream's string `vcs.change.id`.
- **Cardinality** (line ~365): "Three classes of *dimension*, plus one kind of attribute
  that is not a dimension at all:" followed by **Bounded**, **Unbounded but necessary - join
  keys, not grouping keys** ("never as a dashboard dimension"), a paragraph on
  `gen_ai.usage.*_tokens` and `mctl.policy.decided_at` ("neither ... measurements, not
  dimensions and not join keys"), and **Must not become attributes**.
- **Cross-repo references**: almost all are full (`mctlhq/mctl-gitops#1332`,
  `mctlhq/mctl-telegram#658`, `mctlhq/.github#48` in References). Exceptions found by grep:
  - line ~27 (Ownership prose): `mctl-agents#196`
  - line ~102 (`mctl.execution.id` row): `mctl-agents#196`
  - line ~191 (DevLoop execution trace): "the `#1280` soak"
  - line ~253 (`gen_ai.*` / token counters): `.github#48`
  - line ~391 (Bounded class): "since `#658` removes this one"
- `docs/public/llms-full.txt` is git-tracked and is generated from `docs/` by
  `scripts/generate-llms-full.ts` (`bun run generate:llms`, also run inside
  `bun run build`). It currently contains the same stale text (e.g. line ~3962 "Three
  classes of *dimension*", line ~3847 `.github#48`).
- Release is via release-please (`release-please-config.json`, `CHANGELOG.md`); a tag
  push builds the image and updates gitops.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-docs/values.yaml`: tenant `admins`, image tag
  `0.1.57` (matches `package.json` version `0.1.57`), ingress hosts `docs.mctl.ai` and
  `admins-mctl-docs.mctl.ai`. The change is static content only; no runtime config is
  involved. MCP tools were not called; the gitops file was sufficient for a content-only change.

## Proposed solution
Three wording edits in `docs/reference/telemetry-attributes.md`, then regenerate
`docs/public/llms-full.txt`.

1. **Cardinality opener.** Replace "Three classes of *dimension*, plus one kind of
   attribute that is not a dimension at all:" with wording that names the subject as
   cardinality and lets each class say what it is, e.g.:
   "Three cardinality classes follow, each stating what its members may be used for,
   plus a note on the measurements and per-decision values that fit none of them:"
   The class headings and bodies stay as they are; they already say what each class is
   ("join keys, not grouping keys", "Must not become attributes").
2. **Rule 6 extension.** Append to rule 6, after the `_id` amendment, a sentence such as:
   "An identifier assigned by an external system may keep that system's own term for it:
   `mctl.issue.number` and `mctl.pr.number` carry the GitHub issue and pull-request
   number, which GitHub calls a number and keeps distinct from its own internal `id`, so
   renaming them `.id` would obscure which identifier is meant."
   This mirrors how the `_id` amendment was written (rule plus named precedent plus reason)
   and is the cheaper side recommended by the issue. Rule 6's bold heading may stay; the
   amendments qualify it, as the `_id` one already does.
3. **Full cross-repo references.** `.github#48` -> `mctlhq/.github#48`;
   `mctl-agents#196` -> `mctlhq/mctl-agents#196` (both sites); `#1280` ->
   `mctlhq/mctl-gitops#1280`; `#658` -> `mctlhq/mctl-telegram#658`. Keep the backtick code
   formatting the page already uses.
4. Run `bun run generate:llms` so the tracked `docs/public/llms-full.txt` matches.

## Alternatives
- **Rename `mctl.issue.number` / `mctl.pr.number` to `.id`.** Complies with rule 6 as
  written, but changes names (out of scope), conflicts with GitHub's own `id` vs `number`
  distinction, and contradicts the "Upstream namespaces" table rationale. Dropped.
- **Keep "of dimension" and reclassify the opener as "one dimension class and two
  non-dimension classes".** Accurate, but heavier and still frames the section around
  dimensions rather than cardinality, which is the section's subject. Dropped in favour of
  the issue's suggestion.
- **Expand only `.github#48`.** Minimal, but leaves `mctl-agents#196` (which is not a
  back-reference to an earlier full mention) bare and fails "in full throughout". Dropped;
  the short back-references are included but flagged as an open question.

## Platform impact
- Migrations: none. Backward compatibility: no attribute name, type, status or class
  changes; producers are unaffected.
- Resources: none; static content.
- Risks: wording drift from the reviewed meaning - mitigated by limiting edits to the
  sentences listed above and diff review. Stale `llms-full.txt` - mitigated by regenerating it
  in the same commit. Accidental edits elsewhere in the generated file - check that its diff
  is limited to the same sentences.
