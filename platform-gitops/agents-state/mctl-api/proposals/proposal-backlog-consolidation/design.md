# Design: proposal-backlog-consolidation

## Current state
Per the platform's spec-driven workflow (`context/architecture.md` doesn't itself describe
proposal lifecycle, but the daily cycle described in this agent's own `CLAUDE.md` does):
researcher → analyst → spec-writer produces one `proposals/<slug>/` folder per finding, and a
separate `mctl_trigger_implementer` tool later picks up exactly one `status=accepted` proposal
at a time. There is currently no automated step that checks whether a new finding is already
covered by an existing unmerged proposal before a new slug is created — that check has been
happening informally, and inconsistently, in the analyst's own reasoning each cycle (this
cycle's inbox documents the analyst almost creating an 11th and 9th duplicate before an
orchestrator correction caught it). As a result, 29 of `proposals/`'s 60 slugs are unmerged
duplicates across four topics, and at least 2 more (`chi-security-patch`,
`pgx-sqli-cve-2025-54236`) are already merged but were still being counted as open duplicates
by this cycle's naive `ls`-based tally.

## Proposed solution
This is a proposal-lifecycle hygiene change, not a code change to `mctl-api` itself. The
"system" being specified is the proposal backlog process:

1. **Status audit.** For each of the 29 candidate slugs, read its `.status.yaml` (if present)
   and its `requirements.md` target version/CVE list. Two are already `status: merged`
   (`chi-security-patch`, `pgx-sqli-cve-2025-54236`) and should be excluded from "duplicate"
   counts going forward — they are done, not open.
2. **Canonical selection per family**, using "targets the newest/most current fix version and
   is not itself stale" as the primary criterion, with correctness of framing as a tiebreaker
   when versions are equal:
   - **go-upgrade (10 slugs → 1 canonical):** `go-1.24-eol-unpatched-cve` — targets a minimum
     of Go 1.26.4 (preferring 1.27.x), is the most recently written (references Go 1.27.0's
     2026-08-19 release), and explicitly self-declares as the escalation superseding the other
     nine (`go-upgrade`, `go-upgrade-1262`, `go-upgrade-stdlib-cves`,
     `go-upgrade-stdlib-cves-v2`, `go-runtime-upgrade`, `go-runtime-upgrade-v2`,
     `go-runtime-cve-upgrade`, `go-runtime-cve-dos`, `go-toolchain-ace-cve-27140`).
   - **pgx (8 slugs → 1 canonical, 1 already merged):** `pgx-critical-memory-safety-cve-v2` —
     targets v5.11.0 (current latest release), self-declares as consolidating 6 sibling
     proposals. `pgx-sqli-cve-2025-54236` is already merged and excluded. The remaining 6
     others (`pgx-critical-memory-safety-cve`, `pgx-cve-sql-injection`,
     `pgx-security-upgrade`, `pgx-sql-injection-fix`, `pgx-sqli-patch`, `pgx-upgrade-v592`) are
     marked superseded.
   - **mcp-go (8 slugs → 1 canonical):** `mcp-go-upgrade-v3` — targets v1.1.0 (current latest
     release), closes both CVE-2026-81092 and CVE-2026-27896. The remaining 7
     (`mcp-go-cve-waf-bypass`, `mcp-go-oauth-upgrade`, `mcp-go-upgrade-v0.50`,
     `mcp-go-upgrade-v2`, `mcp-go-upgrade`, `mcp-go-v051-upgrade`, `mcp-go-v052-upgrade`) are
     marked superseded.
   - **chi (3 unmerged slugs → 1 recommended canonical, flagged for confirmation):**
     `chi-open-redirect-ghsa-mqqf`, `chi-open-redirect-patch`, and `chi-upgrade-v525` all
     target the identical fixed version (chi v5.2.5) — there is no version-based
     differentiator here, unlike the other three families. This proposal recommends
     `chi-upgrade-v525` as canonical because it is the only one whose CVE framing matches
     this cycle's confirmed research exactly (CVE-2025-69725, affected range 5.2.2–<5.2.4,
     correctly noting mctl-api's actual 5.2.1 pin predates that range). Because this is a
     framing-based tiebreak rather than a version-based one, it is flagged in the acceptance
     criteria as needing confirmation (by a human reviewer or a future analyst pass) rather
     than being treated as a fully mechanical decision. `chi-security-patch` is already merged
     and excluded.
3. **Mark, don't delete.** Every non-canonical, unmerged slug in each family gets a
   `.status.yaml` with `status: superseded` and a pointer to the canonical slug, added
   alongside (not replacing) its existing three files. This preserves audit history and avoids
   an irreversible bulk-delete of prior agent work.

## Alternatives
- **Delete the duplicate proposal folders outright.** Rejected: destroys historical record of
  what was researched and why; a `superseded` status marker achieves the same practical
  outcome (keeping the backlog list clean) without the irreversibility.
- **Merge all duplicate proposals' content into one giant combined file per family.** Rejected:
  the canonical proposals already have complete, self-contained requirements/design/tasks;
  merging text from 6-10 near-identical drafts adds noise without adding information.
- **Leave the backlog as-is and rely on the analyst to keep manually deduplicating each
  cycle.** Rejected: this is the status quo, and it has already failed for at least three
  cycles (2026-08-22, 2026-09-19, 2026-09-26), each time re-surfacing the same finding as
  "needs consolidation" without anyone doing the consolidation.

## Platform impact
- **Migrations:** none — no `mctl-api` code, schema, or deployment change. This is metadata
  added to the `proposals/` directory only.
- **Backward compatibility:** not applicable — no running system is affected.
- **Resource impact (`labs`):** none. mctl-api runs only in tenant `admins`; this proposal
  doesn't touch either tenant's runtime resources.
- **Risks and mitigations:**
  - Risk: marking a proposal `superseded` when it actually contains a scoping detail the
    canonical proposal misses. Mitigation: files are left intact (not deleted), so any missed
    detail can be recovered and folded into the canonical proposal later; the audit step in
    Tasks requires reading each file's full acceptance-criteria list before marking it
    superseded, not just comparing titles.
  - Risk: the chi family's canonical pick is later judged wrong once a human reviews it.
    Mitigation: explicitly flagged as "recommended, pending confirmation" rather than treated
    as final in the requirements/acceptance criteria.
  - Risk: this proposal itself becomes stale if new duplicate proposals are opened before it's
    acted on. Mitigation: acceptance criteria state that if a canonical proposal becomes stale,
    it should be updated in place, not superseded by a new sibling — reinforcing the pattern
    this proposal is trying to establish going forward.
