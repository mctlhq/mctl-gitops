# Tasks: issue-575-docs-runbook-document-the-tg-login-looku

- [ ] 1. Re-verify every behavioural claim against `main` before writing a
      word: `ResolveScopes`' lookup branch (`internal/oauth/server.go:1049`)
      and its position relative to `AdminTelegramIDs` (`:984`) and
      `isClientTier` (`:1052`); the two `requireAnyScope` sites
      (`internal/mcp/tools.go:1070`, `:1526`) and the write tools' plain
      `requireScope(id, "admin:users")` gates; the `isLookupOnly` binding
      (`internal/oauth/server.go:1558`) and its two uses (`:1559` exemption,
      `:1631` enable_access skip); `handleTokenRefresh`'s bound-and-guard
      (`:2136-2145`) and `boundRefreshGrant` (`:2231`); `isClientTier`'s
      open-registration `default:` branch (`:1073`); and the config path
      `internal/config/config.go:337` → `cmd/server/main.go:812`.
      — DoD: each claim in the planned section maps to a file:symbol the
      implementer has read on `main`; no claim sourced from a PR description
      or from this proposal alone.
- [ ] 2. Confirm the removal-path branch condition experimentally rather than
      by reading (depends on 1): run
      `go test ./internal/oauth/ -run 'TestToken_RefreshCannotExpandLookupGrantAfterAllowlistRemoval|TestToken_RefreshGraceRecoveryCannotExpandGrant|TestResolveScopes_AutoApprove|TestResolveScopes_Tiers' -v`.
      — DoD: the implementer can state, with the test output in hand, that
      `AUTO_APPROVE_CLIENTS=true` yields HTTP 400 `invalid_grant` on refresh
      after removal, and that the scopeless HTTP 200 case requires the
      identity to resolve to no scopes (open registration off, or DB tier
      `none`).
- [ ] 3. Draft the section body (depends on 1, 2): heading
      `## Lookup-admin tier and TG_LOGIN_LOOKUP_ADMINS`, covering, in order —
      scope granted and the exact two tools it opens; no-MTProto onboarding;
      tier precedence and the dual-listing mistake; allowlist-before-first-
      sign-in ordering; the `AUTO_APPROVE_CLIENTS` materialization exemption
      and its reason; both refresh outcomes on removal with the condition that
      selects them; where the env var is parsed and set; positive and negative
      verification steps.
      — DoD: every acceptance-criteria bullet in `requirements.md` has a
      corresponding sentence; prose matches the register of the neighbouring
      `## OAuth refresh re-authorization after scope changes` and
      `## Deployment compatibility boundaries` sections; no sub-headings; no
      emoji; English only.
- [ ] 4. Insert the section into `docs/runbook.md` (depends on 3) immediately
      after the `## OAuth refresh re-authorization after scope changes`
      section (after line 46, before `<a id="deployment-compatibility"></a>`),
      with the same `---` separator style the neighbours use, and with NO
      `<a id="...">` anchor.
      — DoD: `git diff --stat` shows `docs/runbook.md` only; the section reads
      in document order between the refresh section and the deployment
      compatibility section.
- [ ] 5. Add the TOC bullet (depends on 4):
      `- [Lookup-admin tier and TG_LOGIN_LOOKUP_ADMINS](#lookup-admin-tier-and-tg_login_lookup_admins)`
      immediately after the existing `OAuth refresh re-authorization` bullet.
      — DoD: exactly one line added to the `## Table of contents` block; no
      other line in that block touched; the bullet's format matches its
      neighbours.
- [ ] 6. Self-check the scope limits (depends on 4, 5): grep the new text for
      `mctl_` (must be zero hits) and for `<a id=` (must be zero hits in the
      added lines); confirm no `.go` file, no `deploy/` file and no
      `.env.example` is in the diff.
      — DoD: `git status --porcelain` lists `docs/runbook.md` and nothing else;
      both greps come back empty on the added hunk.
- [ ] 7. Cross-reference, do not duplicate (depends on 3): the removal
      paragraph points at the adjacent refresh re-authorization section for the
      general monotonicity rule instead of restating it.
      — DoD: the two sections do not contradict each other and the new one
      adds only tier-specific facts.
- [ ] 8. Open the PR with a `docs:` conventional-commit subject, e.g.
      `docs(runbook): document the TG_LOGIN_LOOKUP_ADMINS lookup-admin tier`
      (depends on 6). Call out in the PR body that the section documents BOTH
      removal outcomes because the labs deployment runs
      `AUTO_APPROVE_CLIENTS: "true"`, where removal produces `invalid_grant`
      rather than the scopeless HTTP 200 the issue text predicts.
      — DoD: PR references issue #575, merge strategy is a merge commit per
      `.claude/CLAUDE.md`, and the deviation from the issue's literal wording
      is stated for the reviewer rather than buried.

## Tests

- [ ] T1. `go test ./docs/... ./deploy/...` — passes, including
      `TestRunbookAnchorsPresent` (seven alert anchors still present and
      untouched) and `TestRunbookMetricNamesRegistered` (no new `mctl_*`
      token), plus `deploy/alerts/runbook_links_test.go`.
- [ ] T2. `go build ./... && go vet ./...` — unchanged and green; proves the
      diff is documentation-only and touched no package.
- [ ] T3. `go test ./internal/oauth/ -run 'Lookup|RefreshCannotExpand'` —
      green, and the assertions in
      `internal/oauth/refresh_test.go:554` and
      `internal/oauth/enable_access_test.go:545` still match what the new
      section claims. If a future change makes one of them disagree with the
      prose, the prose is what is wrong.
- [ ] T4. Manual render check on the PR: the new table-of-contents bullet
      scrolls to the new heading on GitHub (the link relies on the generated
      slug, not an explicit anchor), and every other TOC link still resolves.
- [ ] T5. Manual read-back: each acceptance-criteria checkbox in issue #575 is
      satisfiable by pointing at a specific sentence of the new section.

## Rollback

The change is a single-file documentation edit with no runtime effect, so
rollback is `git revert` of the merge commit (merge commits, never squash, per
`.claude/CLAUDE.md`) — no redeploy, no migration, no config change. If only the
removal-semantics paragraph is disputed, prefer a follow-up PR that rewords
that paragraph over reverting the whole section: the scope, onboarding,
precedence and configuration-location material is independently correct and is
the part #400 depends on. Because nothing outside `docs/runbook.md` is touched,
no service state can be left inconsistent by a partial revert.
