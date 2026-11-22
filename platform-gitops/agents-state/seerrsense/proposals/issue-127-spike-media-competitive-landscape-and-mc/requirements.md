# Spike (revision 2): competitive landscape and MCP-native media engine (build vs fork vs integrate)

## Context
Issue mctlhq/seerrsense#127 asks for a research spike, not an implementation. The question is whether MCTL should evolve SeerrSense into a lightweight MCP-first media manager. That manager would replace Seerr, Radarr and Sonarr, and later Prowlarr. qBittorrent and Jellyfin would stay. SeerrSense 1.14.4 (`src/mcp/server.ts`, `src/providers/seerr/client.ts`) is a TypeScript/Fastify MCP + REST layer over one Seerr per caller. Everything past "file a request" is delegated to Seerr, and through it to Radarr/Sonarr.

This is revision 2. It answers the independent review "REQUEST CHANGES / HOLD - revision 2" on the issue, which asked for four things:
- primary-source evidence delivered now, not a plan to collect it later;
- coverage of all nine named candidates;
- a corrected HolyArrs MCP/OAuth assessment;
- an auditable matrix with uncertainty, a hybrid option, the #120 two-door identity model, a data-plane security model and a next isolated experiment.

The evidence annex in design.md was gathered on 2026-11-22 through the GitHub API (tags, commit SHAs, trees, docs and code at tag). Nothing was cloned, built, run or benchmarked. Every resource number in this proposal is therefore an upstream claim or unknown, never a measurement.

## User stories
- AS the platform owner I WANT a competitor matrix whose every material claim cites a repo, tag, commit SHA and date SO THAT I can audit it, not trust it.
- AS the platform owner I WANT a weighted matrix with per-score evidence, uncertainty ranges and rank-reversal analysis SO THAT I can see which unknown would change the answer.
- AS the platform owner I WANT the experiment decision kept separate from the business decision SO THAT I can approve a cheap isolated test without committing to a strategy.
- AS an existing SeerrSense user (door 1, Google sign-in) I WANT tools, schemas, scopes and sign-in unchanged SO THAT my client keeps working.
- AS an mctl principal (door 2, mctl-api token, #120) I WANT any future media capability to respect audience checks, principal mapping, linked revocation and per-person tool filtering SO THAT the second door is not weakened.
- AS a future implementer I WANT one vertical slice, defined identically for every option, plus a data-plane security model SO THAT options are compared on equal terms and implementation can start safely after an owner GO.

## Acceptance criteria (EARS)
- WHEN the spike is delivered THE SYSTEM SHALL include a competitor row for each of the nine named candidates: HolyArrs, Streamline, Mediarium, Reelix, MovieClaw, MediaManager, arr-mcp, MediaStack MCP and Mediabox MCP. Each row SHALL give the canonical repo, the tag, commit SHA and date inspected, the SPDX license, the language, the contributor and release counts, the CI/security files, and the MCP status classed released / gated / planned / absent / unknown, with an evidence id.
- IF a candidate name maps to more than one repo THEN THE SYSTEM SHALL name each candidate repo, state which one was scored and why, and SHALL NOT silently pick one.
- IF a claim is documentation-only, or main-branch only rather than in a tag, THEN THE SYSTEM SHALL label it so, and SHALL NOT present it as released or as live-interoperable.
- WHEN the decision matrix is produced THE SYSTEM SHALL score baseline, A (extend SeerrSense), B (HolyArrs integration), C (Streamline as engine), D (clean-room minimal Go movie engine) and H (incremental hybrid: replace Radarr first) with weights fit 25%, safety/operability 20%, effort 20%, footprint 15%, license/governance 10%, migration/reversibility 10%. Every cell SHALL cite evidence ids or a stated assumption.
- WHEN totals are reported THE SYSTEM SHALL also report low/high totals, at least three weight scenarios, a sampled first-place share, and the specific score changes that reverse the leading ranks.
- WHILE no measurement has been taken on the owner's host THE SYSTEM SHALL mark footprint scores as upstream-claim-based, and SHALL NOT issue a final NO-GO or GO business decision that depends on them.
- WHEN a verdict is given THE SYSTEM SHALL give an experiment verdict (may an isolated test run) separately from a business verdict (adopt this strategy).
- WHEN gate criteria are set THE SYSTEM SHALL express them as demonstrable reliability, security and recovery tests, not calendar age or maintainer counts.
- WHEN the vertical slice is specified THE SYSTEM SHALL define one slice, used for every option, with synthetic or public-domain fixtures only: resolve a lawful test title, check the library, select from a synthetic indexer, preview, approve, mock download, import, observable state. It SHALL include negative tests for duplicate, missing episode, failed download, insufficient space, wrong language/quality, revoked/expired grant, cross-tenant access and replay.
- WHEN a future write path is designed THE SYSTEM SHALL treat a plan digest token as a preview handle, not as proof of human consent. Execution SHALL require a trusted approval bound to subject, tenant, backend, device/agent, plan digest and expiry, consumed atomically, executed idempotently, and reconciled after a crash.
- WHEN identity compatibility is specified THE SYSTEM SHALL define tests for both doors of #120: Google-backed tokens unchanged, mctl-api tokens with the correct audience accepted, wrong audience refused, unmapped principal refused, revoked principal refused, per-person tool filtering applied. The spike itself SHALL make no identity change.
- WHEN licensing is assessed THE SYSTEM SHALL state obligations per integration boundary (unmodified network use, modified network use, distribution), labelled not legal advice. It SHALL also record the verified MIT (`LICENSE`) vs ISC (`package.json`) mismatch in seerrsense as a follow-up only.
- WHILE the spike is in progress THE SYSTEM SHALL NOT change seerrsense code, `platform-gitops/services/labs/seerrsense/values.yaml`, production authentication, household media or production data. It SHALL NOT create a repository, deploy, start the implementer, approve the proposal, or contact users.
- IF a source could not be read THEN THE SYSTEM SHALL record the exact failed retrieval and the human input requested, not "not found".
- WHEN the spike concludes THE SYSTEM SHALL propose the next isolated, read-only experiment for owner decision, and SHALL keep the proposal at status=proposed.

## Out of scope
- Any code, schema, gitops, identity or deployment change. No new MCP write tools during research.
- Production benchmarks, writes against the household Seerr (`SEERR_URL=https://media.mctl.ai`), access to household volumes or private data.
- Creating `mctlhq/mctl-media`, a fork, or any repo.
- Music, subtitles, playback, transcoding, and a native torrent or usenet client.
- Fetching, indexing or downloading copyrighted media. Fixtures are synthetic or public-domain only.
- Contacting early users. Discovery questions are drafted only, and run only with owner approval.
- Legal conclusions. The license analysis is engineering triage, not legal advice.

## Open questions
- Owner host baseline: actual RAM of the Mac mini (reported as 8 GB, unverified), macOS version, container runtime (Colima, Docker Desktop or native), and which of Seerr/Radarr/Sonarr/Prowlarr/qBittorrent/Jellyfin run there, at what versions and RSS. Not observable from this run.
- Where `https://media.mctl.ai` (household Seerr) runs and how it is fronted. The CF Access secret mappings in values.yaml suggest Cloudflare Access, but that was not observed.
- MediaStack MCP is ambiguous. The reviewer supplied clive-stokes/mediastack-mcp, which is what this proposal scores. aderaaij/mcp-mediastack (MIT, v0.1.0, FastMCP) also matches the name.
- Mediabox MCP: the reviewer supplied createmediabox.dev. This proposal maps it to github.com/JuanCMPDev/mediabox-mcp, matched by the README's "create-mediabox" installer and the product name. The site itself was not fetched. The owner should confirm.
- Reelix: the reviewer named demonzoned/Reelix, which is what this proposal scores. 4444zyf/Reelix (MIT, "agent-native", created 2026-11-17) is unrelated. TheMightyTRex/starboard is a dashboard that mentions Reelix.
- HolyArrs main vs tag: the reviewer verified main-branch docs. This proposal verified tag 1.2.0 (d63e43f, 2026-11-17). main was at 4b0349e (2026-11-19) and moves daily. Live interoperability with Claude/ChatGPT connectors is unverified.
- Whether "replace Seerr" must keep Seerr's multi-user request/approval workflow. SeerrSense relies on it for household attribution (`attributedUserId` in `src/providers/seerr/tenants.ts`). HolyArrs, Streamline and Mediarium each have their own request system, but none exposes the Seerr API that SeerrSense calls.
- #120 is draft and not started (its body says do not add `agents:intake` until the line starts). Any media write capability depends on its final principal and tool-filtering contract.
- Owner risk appetite for a maintainer-operated metadata server (HolyArrs default `https://api.holyarrs.com`), even though it can be replaced through `HOLYARRS_METADATA_URL` or `HOLYARRS_TMDB_KEY`.
