# Design: mctl-agent-rollback

## Source commits

- `mctl-agent:f955a0e` — feat(rollback): resolve previous image tag from gitops history
  (2026-05-02) — core implementation: replaces stub with `p.rollbackImage(ctx, filePath,
  content)`; new file `internal/fixer/previous_tag.go` (+90 lines) walks up to 20
  commits of the GitOps values file via GitHub API to find the prior image tag.
- `mctl-agent:a8e00cf` — fix(rollback): handle indented image blocks (2026-05-02)
- `mctl-agent:73ef4e5` — fix(rollback): strip inline comments on image line (2026-05-02)
- `mctl-agent:2b6d314` — fix(rollback): scope image lookup to chart level (2026-05-02)
- `mctl-agent:60d364b` — fix(rollback): propagate non-404 GitHub API errors (2026-05-03)
- `mctl-agent:2395f74` — fix(rollback): additional YAML hardening (2026-05-03)
- `mctl-agent:9fb40c1` — fix(rollback): YAML parser edge cases (2026-05-03)
- `mctl-gitops:4f05252` — chore: bump mctl-agent to 1.7.0 (2026-05-03) — confirms
  production deployment
- `mctl-gitops:d906880` — chore: bump mctl-agent to 1.7.0 (2026-05-03) — companion
  gitops change

## Current state of documentation

**`docs/guides/rollbacks.md`** — title: "Rollbacks"
The page currently covers only user-initiated rollbacks: rolling back via the mctl CLI
and rolling back by reverting a GitOps PR manually. There is no mention of the
agent-triggered automated path. The page is incomplete because mctl-agent 1.7.0
(in production since 2026-05-03) can now open a rollback PR autonomously; operators
who read the docs today are unaware of this safety net and may perform unnecessary
manual steps.

**`docs/platform/components.md`** — title: "Components"
The mctl-agent block lists high-level capabilities. It may mention fix types in
general terms but does not call out the `rollback_image` type specifically, and does
not link to the rollback guide. This makes the components page a dead end for a reader
who wants to learn more about how an automated rollback works end-to-end.

## Proposed solution

**Primary change — update `docs/guides/rollbacks.md`.**
Add a new H2 section "Agent-triggered rollback" after the existing manual rollback
sections. The section should contain:

1. A short introductory paragraph explaining that as of mctl-agent 1.7.0 the platform
   can roll back a workload automatically when the self-healing agent classifies an
   incident as requiring an image rollback.
2. A mermaid flowchart (or sequence diagram) showing the end-to-end flow:
   AlertManager fires → mctl-agent receives alert → agent determines `rollback_image`
   fix type → agent calls GitHub API to walk GitOps values file history (up to 20
   commits) → previous tag found → PR opened against mctl-gitops → operator reviews
   and merges (or shepherd auto-merges).
3. A "How the previous tag is found" subsection describing: the agent calls the GitHub
   Contents API for the values file history, iterates commits newest-first, parses the
   YAML value at each commit, and uses the first tag that differs from the current
   (broken) tag as the rollback target.
4. A "Supported YAML shapes" subsection (or note) listing the patterns the parser
   handles: top-level `image: tag`, indented `image:` blocks, inline comments on the
   `image:` line, chart-level scoping.
5. A "What operators see" note: the agent opens a PR; operators receive normal GitHub
   PR notification; if the shepherd auto-merge policy is active the PR may merge
   without manual action (`<TODO: confirm auto-merge policy details with
   author of f955a0e>`).
6. Version callout: "Available since mctl-agent 1.7.0 (production since 2026-05-03)."
   Tagged `version-status: unverified via MCP, confirmed via mctl-gitops@4f05252`.

**Secondary change — update `docs/platform/components.md`.**
In the mctl-agent capability list, add one sentence that references the new section:
"For automated image rollbacks, see [Agent-triggered rollback](/guides/rollbacks#agent-triggered-rollback)."

**VitePress config (`.vitepress/config.{js,ts}`).**
No structural sidebar change is needed. The new content is a section inside an
existing page (`docs/guides/rollbacks.md`), which is already in the sidebar. If the
rollbacks page is not yet in the sidebar it must be added, but the docs-tree snapshot
confirms the page already exists.

## Alternatives

**Option A — new standalone page `docs/guides/agent-rollback.md`.**
Would give the feature maximum prominence and allow a focused, long-form guide.
Dropped because the user mental model is "I want to roll back my service" — they
will navigate to the existing rollbacks page first. A standalone page risks being
orphaned. The added content is not large enough to justify a separate top-level entry
in the sidebar.

**Option B — document only in `docs/platform/components.md`.**
Components is a reference page for the platform architecture. Placing a how-to flow
there mixes reference and guide styles, which is against the VitePress structure used
in this repo. Also, readers looking for rollback instructions will land on
`docs/guides/rollbacks.md` via search or the sidebar, not the components page.
Dropped in favour of the primary page update with a cross-link from components.

## Impact

- **VitePress sidebar / nav config:** no change required; `docs/guides/rollbacks.md`
  is already in the sidebar.
- **Mermaid diagram:** yes — one diagram recommended to illustrate the automated flow
  (flowchart LR or sequence diagram). Mermaid 11 is already enabled in the stack.
- **Documentation versioning:** applies to the `main` branch of `mctl-docs`. No
  versioned docs system is in place (single-section build per architecture.md); the
  section should carry an explicit "Available since mctl-agent 1.7.0" callout.
