# Spike: competitive landscape and MCP-native media engine (build vs fork vs integrate)

## Context
Issue mctlhq/seerrsense#127 asks for a research spike, not an implementation. The question is whether MCTL should evolve SeerrSense into a lightweight MCP-first media manager that replaces Seerr, Radarr and Sonarr, and eventually Prowlarr. qBittorrent (downloads) and Jellyfin (library and playback) would stay. Today SeerrSense (`src/mcp/server.ts`, `src/providers/seerr/client.ts`) is a TypeScript/Fastify MCP + REST layer over one Seerr per caller. It does not manage media itself: everything that goes past "file a request" is delegated to Seerr and, through it, Radarr/Sonarr.

The spike must produce:
- an evidence-backed competitor matrix;
- a weighted decision matrix for a do-nothing baseline plus options A (extend SeerrSense as a federated MCP over the existing stack), B (integrate a unified backend such as HolyArrs through its API), C (fork) and D (a clean-room MCTL media engine with SeerrSense as the front door);
- a first vertical-slice design that uses only synthetic or public-domain fixtures;
- a benchmark methodology;
- effort and risk ranges;
- a recommendation on whether a separate `mctlhq/mctl-media` repo is warranted.

It matters because a wrong choice either locks the household into an immature AGPL single-maintainer backend or commits MCTL to re-implementing years of *arr domain logic. Either outcome must not regress the deployed `labs/seerrsense` service or its clients.

## User stories
- AS the platform owner I WANT an evidence-based comparison of existing unified media managers and MCP servers SO THAT I decide build/fork/integrate on primary sources rather than press articles.
- AS the platform owner I WANT a weighted, sensitivity-tested decision matrix with GO/NO-GO per strategy SO THAT the decision is explainable and revisitable.
- AS the platform owner with a resource-constrained Mac mini I WANT a reproducible benchmark plan that separates measured numbers from upstream claims SO THAT any resource-saving claim is verified on my hardware.
- AS an existing SeerrSense user I WANT the current MCP tools (`search_media`, `resolve_media`, `get_media`, `request_media`, plus `whoami`) and OAuth behaviour to stay unchanged SO THAT my clients keep working throughout the spike and any follow-up.
- AS a future implementer I WANT a defined MVP vertical slice with component boundaries and negative tests SO THAT implementation can start safely after an explicit owner GO.

## Acceptance criteria (EARS)
- WHEN the spike is delivered THE SYSTEM SHALL include a competitor matrix covering HolyArrs, Streamline, Mediarium, Reelix, MovieClaw, MediaManager, arr-mcp, MediaStack MCP and Mediabox MCP. Each row SHALL give the canonical repo, the license/SPDX, the language, the observed version or tag, the MCP status, and every claim's evidence class (released, gated, planned, unknown) and source link.
- IF a named project cannot be located or its canonical repo is ambiguous THEN THE SYSTEM SHALL record it as "not found" or "ambiguous" with the search performed, and SHALL NOT invent a repo, version or capability.
- IF a claim was obtained only from a secondary source (article, aggregator, search summary) THEN THE SYSTEM SHALL label it "secondary, unverified at tag" until it is checked against a tag or commit in the primary repo.
- WHEN the decision matrix is produced THE SYSTEM SHALL score baseline, A, B, C and D with these weights: functional fit 25%, safety/operability 20%, developer effort 20%, resource footprint 15%, license/governance 10%, migration/reversibility 10%. The matrix SHALL also give the rationale, at least one weight-sensitivity scenario, and a GO/NO-GO or CONDITIONAL verdict per strategy.
- WHILE no benchmark has been run on the owner's hardware THE SYSTEM SHALL mark every resource-footprint score as provisional and SHALL NOT state a memory or CPU saving as fact.
- WHEN the vertical slice is specified THE SYSTEM SHALL describe the following flow using only synthetic or public-domain fixtures and a mock or isolated downloader: resolve a lawful test title, check the library, select a release from a synthetic Torznab indexer, preview a plan, confirm, execute, import, and show observable library state.
- WHEN the vertical slice is specified THE SYSTEM SHALL enumerate negative tests for: duplicate request, missing episode, failed download, insufficient disk space, wrong language/quality, revoked or expired grant, cross-tenant access, and replay of a confirmation token.
- WHEN any future write tool is designed THE SYSTEM SHALL follow intent -> verified canonical ID -> deterministic plan -> explicit confirmation bound to the plan digest, caller and expiry -> idempotent execution -> observable status.
- WHILE the spike is in progress THE SYSTEM SHALL NOT change any file in the seerrsense repo, its deployed configuration (`platform-gitops/services/labs/seerrsense/values.yaml`), production authentication, household media, or any production data.
- WHILE the spike is in progress THE SYSTEM SHALL NOT create a new repository, start the implementer, approve the proposal, or deploy anything.
- IF the agent cannot access an external source or run a local experiment THEN THE SYSTEM SHALL record the limitation and convert the item into a follow-up research task rather than assume a result.
- WHEN the spike concludes THE SYSTEM SHALL recommend whether a separate `mctlhq/mctl-media` repo is warranted, with the condition that would trigger creating it.
- WHEN the spike concludes THE SYSTEM SHALL keep the proposal at status=proposed pending independent review and explicit owner GO.

## Out of scope
- Any code change to seerrsense, any deployment, any production benchmark or write against the household Seerr (`SEERR_URL=https://media.mctl.ai`).
- Creating `mctlhq/mctl-media` or any fork.
- Music, subtitles, playback, transcoding, and native torrent/usenet implementation.
- Fetching, indexing or downloading copyrighted media. All fixtures are synthetic or public-domain.
- Changes to OAuth, scopes or identity work (#120). These are only analysed for compatibility.
- Exposing home services to the internet.

## Open questions
- Actual baseline of the owner's Mac mini (RAM is reported as 8 GB but not verified; macOS version; Colima vs Docker Desktop vs native; which of Seerr/Radarr/Sonarr/Prowlarr/qBittorrent/Jellyfin run there today). This proposal could not observe it.
- Where the household Seerr at `https://media.mctl.ai` physically runs and how it is fronted. The deployment carries `CF_ACCESS_CLIENT_ID`, which suggests Cloudflare Access, but the topology is not observed.
- The scope and status of identity work #120. It could not be read in this run. The proposal assumes it concerns per-person backend binding as implemented in `src/providers/seerr/tenants.ts`.
- "Streamline", "MediaStack MCP" and "Mediabox MCP": no canonical media-manager repo was found. The owner should supply URLs if specific projects were meant.
- Reelix: several unrelated repos share the name, and the likely canonical one (demonzoned/Reelix) must be confirmed.
- HolyArrs: version references are inconsistent (1.1.0, 1.1.3, 1.1.4 and 1.2.0 across sources), and it is unclear whether MCP is released, gated behind a setting, or planned.
- HolyArrs uses a metadata server operated by its maintainer. What it does with request data is unclear, and so is whether that dependency is acceptable to the owner.
- Whether "replace Seerr" includes Seerr's multi-user request/approval workflow, which SeerrSense currently relies on for attribution (`attributedUserId`).
- License metadata in seerrsense is inconsistent: `package.json` says ISC and `LICENSE` says MIT. This matters if any AGPL/GPL code is ever combined.
