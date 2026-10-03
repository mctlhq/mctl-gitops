# Triage and close duplicate go-upgrade / pgx / mcp-go / chi proposal families

## Context
`proposals/` (a symlink to `/workdir/mctl-gitops/platform-gitops/agents-state/mctl-api/proposals`)
currently holds 60 slugs, of which at least 29 are unmerged duplicates clustered around just
four underlying topics: 10 Go-toolchain/EOL upgrade slugs, 8 `pgx` CVE slugs, 8 `mcp-go` CVE
slugs, and 3 `chi` open-redirect CVE slugs. This is not a one-off: the analyst has flagged the
go-upgrade pile as needing "a backlog triage/consolidation pass, not another new proposal" for
at least two prior cycles (2026-08-22, 2026-09-19) without the consolidation itself ever being
proposed as a unit of work.

Verification during spec-writing confirms the sprawl and refines the picture: of the four
families, `pgx` and `mcp-go` already each have a self-declared "escalation/consolidation"
proposal (`pgx-critical-memory-safety-cve-v2`, targeting v5.11.0; `mcp-go-upgrade-v3`,
targeting v1.1.0) that name themselves as superseding the older slugs in their family — but
none of those older slugs have actually been marked superseded or closed, so the duplication
persists in practice. The `go-upgrade` family's most complete candidate is
`go-1.24-eol-unpatched-cve`, which similarly self-declares as an escalation over nine sibling
proposals and targets the highest/most current version (minimum Go 1.26.4, 1.27.x preferred).
For `chi`, all three remaining unmerged slugs (`chi-open-redirect-ghsa-mqqf`,
`chi-open-redirect-patch`, `chi-upgrade-v525`) target the same fixed version (chi v5.2.5); a
fourth chi slug, `chi-security-patch`, is excluded from the count because it already has a
`status: merged` record (PR #39, merged 2026-05-01) — this was not visible to the analyst's
naive slug count and is documented here as a correction. `chi-upgrade-v525` is the most
accurate and current framing (it correctly identifies the CVE as CVE-2025-69725, cites the
precise affected range 5.2.2–<5.2.4, and correctly notes mctl-api's actual pin of 5.2.1
predates that range — matching this cycle's confirmed research), making it the recommended
canonical for the `chi` family. Additionally, one `pgx` slug (`pgx-sqli-cve-2025-54236`) was
found to already carry a `status: merged` record (PR #40, merged 2026-05-01) even though it
was counted among the "8 pgx slugs" in this cycle's inbox — another correction surfaced only
by this proposal's verification pass, underscoring exactly why this hygiene work is needed:
duplicate-count estimates produced by naive directory listings silently include already-merged
work.

Because the platform's own tooling (`mctl_trigger_implementer`) only picks up proposals with
`status=accepted` one at a time, this sprawl actively wastes research-agent cycles
(re-researching the same EOL status and CVE framing every week) and blocks a human/orchestrator
reviewer from being able to tell which proposal in each family is "the" one to accept.

## User stories
- AS the analyst agent I WANT each of the four duplicate-prone topics (Go upgrade, pgx, mcp-go,
  chi) to have exactly one open, canonical, currently-accurate proposal SO THAT I stop
  re-surfacing the same finding as if it were new every cycle.
- AS a human/orchestrator reviewer I WANT the non-canonical duplicates marked superseded (or
  confirmed already merged) rather than left open and ambiguous SO THAT I can accept the
  correct proposal in each family without needing to read all 29 files myself.
- AS the spec-writer agent I WANT a documented, one-time correction of which slugs are already
  merged vs. genuinely open SO THAT future cycles don't recount merged work as unresolved
  duplication.

## Acceptance criteria (EARS)
- WHEN this proposal's triage task inspects each of the 29 candidate slugs (10 go-upgrade, 8
  pgx, 8 mcp-go, 3 chi, per the Context section's corrected counts) THE SYSTEM SHALL record,
  for each slug, its current `.status.yaml` state (if any) and its targeted fix version.
- WHEN a slug is found to already carry `status: merged` (e.g. `chi-security-patch`,
  `pgx-sqli-cve-2025-54236`) THE SYSTEM SHALL exclude it from the "to be superseded" set and
  instead record it as "already resolved, no action needed."
- IF a family has no single proposal whose target version is unambiguously the newest/most
  current within that family THEN THE SYSTEM SHALL flag that family as needing a human
  decision rather than the automation guessing.
- WHEN the canonical proposal for a family is identified (or a human decision is requested)
  THE SYSTEM SHALL mark every other unmerged, non-canonical proposal in that family with a
  `status: superseded` record pointing at the canonical slug, rather than deleting the files.
- WHEN this triage is complete THE SYSTEM SHALL leave exactly one open (non-superseded,
  non-merged) proposal per family: `go-1.24-eol-unpatched-cve` for go-upgrade,
  `pgx-critical-memory-safety-cve-v2` for pgx, `mcp-go-upgrade-v3` for mcp-go, and
  `chi-upgrade-v525` for chi (pending confirmation per the acceptance criterion above, since
  chi's three candidates are version-equivalent and the choice is based on accuracy of
  framing, not a version delta).
- WHILE this triage is in progress THE SYSTEM SHALL NOT modify the content of any
  `requirements.md`/`design.md`/`tasks.md` file being marked superseded — only status metadata
  is added; the historical proposal text is left intact for audit purposes.
- IF new information later shows the chosen canonical proposal for any family is itself stale
  (e.g. a newer CVE or release supersedes its target) THEN THE SYSTEM SHALL update that single
  canonical proposal in place rather than opening a new sibling slug.

## Out of scope
- Writing or reviewing the actual upgrade code for Go, pgx, mcp-go, or chi — this proposal is
  about proposal-lifecycle hygiene only; the canonical proposals in each family already specify
  the implementation work.
- Re-litigating which CVEs are in scope for each family — this proposal takes the existing
  canonical proposals' scoping as given and only addresses which slug is authoritative.
- Any change to the `mctl_trigger_implementer` tool's one-at-a-time acceptance behavior.
- Closing or touching any of the `issue-*` proposal slugs, `roadmap-governed-maintenance-operations`,
  or `argocd-*`/`client-go-version-drift`/`go-oidc-dep-bump` slugs — those are outside the four
  named duplicate families and not part of this proposal's scope.
- Deleting any proposal file or directory — superseded proposals are marked, not removed.
