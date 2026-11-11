# mctl-api 4.155.0 release readiness

Status: **NO-GO / preparation only**, 2026-11-11. This is the canonical
coordination and owner decision packet for R0. It does not approve the #2528
implementation, establish a freeze, decide a grant, or authorize release or
production changes. The #2528 proposal remains the implementation specification;
this packet records its reconciliation and release prerequisites rather than
maintaining a second implementation design.

## Pinned baseline and evidence

Read-only repository inspection used mctl-gitops
`df077807d` (the #2600 merge). GitHub reads confirmed:

| Item | Observed value | Meaning |
|---|---|---|
| API main | `a5b9ef9cf0f880f28b841033a8b2a6d9563ce050` | Candidate source baseline |
| API #934 | `5820073f20abc78ab1db2b1b42c146c70ac8cbf3`, OPEN, Draft | Release remains held |
| Chart source | pinned to the API main SHA above | Later chart merges alone do not change this chart source |
| Bootstrap image tag | `4.154.0` | Desired state; live pod digest not re-observed in this audit |
| #2528 proposal content | `sha256:13a4fd9cdf6b1063a9f50ed3b94604e82541d8b19b1f52bda77f6f9128e3443c` | Recomputed with `proposal-content-digest.py --rev HEAD` |
| Proposal state | `proposed`, `requires_human_approval: true` | No implementation approval inferred |
| #2589 review | APPROVED on final head `21d5711933a2d68daf7b3613a33bf04f2f6b64a9`, MERGED | Historical review evidence, not approval of future amendments |
| Ruleset 18465404 | `DeployKey`, null actor id, `always`; strict checks false | Wildcard bypass persists; no mutation performed |

The issue reports fresh grant `aar_31e2ff84fe6b41b5bf918e79334ca9bd` and
superseded grant `aar_e6e35315c8f54debaa834845d6f2d550`. Its current ledger
state was not read here: **UNKNOWN**, never approved by inference. A closed
issue, merged documentation, review approval or successful CI is not release GO.

Sources: [#934](https://github.com/mctlhq/mctl-api/pull/934),
[#2528](https://github.com/mctlhq/mctl-gitops/issues/2528),
[#2589](https://github.com/mctlhq/mctl-gitops/pull/2589),
[#2543](https://github.com/mctlhq/mctl-gitops/issues/2543), and the
[write-path inventory](../runbooks/mctl-api-release-hold.md).

## Reconcile before deciding the implementation grant

| Subsystem | Implemented at baseline | Work or proof still required |
|---|---|---|
| Bootstrap reader and floor | `scripts/release-gate.py`, `version_holds`, `allow: []` | Extend this reader; do not introduce a duplicate `release-hold.py` |
| Grant validation | Version, grant/approver strings, expiry date | Verify grant provenance, owner identity, policy digest, reviewed release head, source commit/tree and image digest |
| Bump routes | `release-bump-routes.yaml` selects the API PR route; both workflows verify trusted policy before publishing | Prove the first real routed bump, final-head review, expiry at merge and effect-time revalidation |
| Image provenance | `build-image.yaml` stamps resolved `org.opencontainers.image.revision` | Verify label against tag source and digest; SBOM/provenance evidence for the actual build remains pending |
| Chart | Pinned to `a5b9ef9c`, preserving `/devloop` | Do not follow the stale task to pin 4.154.0's chart; move tag and chart pin together after approval |
| Trusted review gate | Existing Actions checks; ruleset strict false | Close PR-controlled guard/check spoofing and stale merge verdicts (P2-2/P2-3) |
| Effect boundary | Workflow floor and post-push detection | P2-1 / #2543 residual; admission and runtime injection protection are not established by this audit |
| Dark configuration | #2591 removes orchestrator identity envFrom entry | Audit all literal env, secret references and producer definitions without reading Secret payloads |

Before implementing #2528, amend its requirements/design/tasks through a PR to
reflect these facts and obtain independent review on the final content digest.
Amendment changes the digest: obtain the corresponding fresh grant; do not reuse
a stale grant. Keep the current proposal and ledger untouched during preparation.

The minimal proposed gate interface extends existing `allow` records with
`digest` and `source_commit`, plus bindings to reviewed release head/tree and
policy digest. Preserve the existing owner/grant/expiry fields. The implementation
proposal must define their exact validation and timestamp format before approval.
Use injectable GitHub/GHCR reads; missing, malformed, partial or unreadable
responses must refuse the operation. Expiry gates new writes/merges, not restarts
of an already authorized deployment.

## Execution sequence and owner decision packet

1. **Freeze decision.** Owner confirms the API main and #934 head above and
   pauses merges affecting the candidate until the release decision. This is the
   selected policy, not an enforced freeze. Check both SHAs before every review,
   build and decision; movement marks candidate evidence stale and requires a
   refreshed packet and any affected grants. Do not merge Basket PRs into R0.
2. **Implementation decision.** Present the reviewed amended #2528 digest,
   grant reference, exact changes and validation evidence. Owner decides through
   the authenticated human path. No typed approver identity, bot substitute,
   automatic acceptance or DeployKey bypass. Separate operator approval covers
   any App, environment, ruleset or admission changes.
3. **Implement and verify the approved gate.** Extend the existing gate and
   close the three P2 findings. Prove that merging #934 can build/tag but cannot
   publish a production bump without a deployment grant. Do not rely on Draft
   state or a post-push watcher as this proof.
4. **Release readiness.** Attach full-source reviews on the exact candidate,
   CI, API/worker/Temporal compatibility, queue/drain evidence and the DB rehearsal
   below. Record exact worker versions and commits. Preserve the disabled Bridge,
   deferred queue, orchestrator identity and Glovo states across every env source.
5. **BUILD GO.** Owner separately authorizes #934 merge/tag/build with the
   pinned release head and tree. Capture the actual tag/source commit, source
   tree, immutable GHCR digest, revision label and available attestations. A
   different tree or missing provenance evidence invalidates the packet.
6. **DEPLOY GO.** Owner reviews the built artifact, policy digest, expiry,
   prerequisite evidence, production diff, rollback and risk disposition. Add the
   bound allow record through its reviewed PR only after this decision. Move
   image tag and chart pin together through the authorized PR route. Validate the
   current head immediately before merge; observe the first real App PR, review,
   auto-merge and absence of App direct pushes to main. Failure leaves NO-GO.
7. **Post-deploy.** Operator verifies Argo Synced/Healthy, actual pod imageIDs
   against the authorized digest and all dark flags. Failed reads remain UNKNOWN.
   Keep Basket, migrations and activation on their separate holds.

### Residual risk decision (#2543)

Both write deploy keys can bypass PR checks and change guarded tag, policy or
allow records. PR routing and monitoring do not remove this ability. The owner
must either accept this exact residual in a dated, attributed record with scope,
expiry and incident/rollback owner, or wait for verified remediation. No
acceptance has been obtained. #2543 stays open; its research authorization does
not permit credential, ruleset or production changes. Cluster-admin overrides and
unverified runtime env injection paths must also have explicit dispositions.

### Evidence required before GO

| Check | Acceptance | Current packet status |
|---|---|---|
| Floor gate | Converged current tree accepted; held 4.155.0 refused without grant | Current-tree verify executed; bootstrap regression suite recorded in PR |
| Bound authorization | Wrong/missing digest/source/head, expired grant, changed policy and unavailable GitHub/GHCR cause no target-main write or deployment | NOT VERIFIED; implementation prerequisite |
| Race and trust | Retry/rebase, moved base/head, spoofed check and PR-controlled guard cannot authorize effect | NOT VERIFIED; isolated tests required |
| Positive control and mutations | Valid isolated release path succeeds; removing each guard makes its test fail | Existing floor suite only; extended gate proof pending |
| Compatibility | Exact API + worker versions pass Part M #993, Part S #992, B4 #1007 and API drain #935 evidence | NOT VERIFIED; older compatibility report #2529 is insufficient |
| OAuth DB upgrade | Disposable representative DB: long transaction/lock timeout on `oauth_refresh_tokens` fails boundedly, successful upgrade preserves data | NOT VERIFIED; no production DB accessed |
| Rollback | Same disposable volume DB supports 4.155.0 then 4.154.0; refresh and queue/drain behavior checked | NOT VERIFIED; operator rehearsal required |
| Artifact and live route | Tag/source/tree/digest/label agree; first routed bump and live imageIDs match | NOT VERIFIED; requires separate build/deploy authorizations |

Attach command, commit, environment, timestamp and outcome for each evidence
item; never mark a missing result PASS. Negative tests use disposable repos/DBs,
synthetic identities and no production credentials. No Secret `.data` reads,
credential exports, impersonation or production bypass experiments are permitted.

## Basket handoff preserved

Glovo Basket MCP remains **NOT LIVE** according to the handoff; this audit did
not probe its live endpoint. V1 means six tools, synthetic catalog, team/user
allowlist, immutable revisions and an authenticated human owner's basket decision.
It excludes real Glovo API, orders/payments, Telegram, Temporal and provider effects.

After 4.155.0: #1008 -> #1007 -> #1014/#1018 -> #1017 and chart pin update ->
4.156.0, with separate release holds. Retarget #1014 and #1018 before deleting
#1008's base branch. Final-head CI/review is required after integration changes.
Activation follows [the canary runbook](../runbooks/glovo-basket-canary.md):
Vault -> DB inventory -> roles/ownership -> ExternalSecrets/env -> authorized
migrator rehearsal and apply/verify -> ZITADEL -> flags/UI -> ingress -> allowlist
-> real OAuth/human decision E2E, negative checks and kill switch.
The pilot team and second real human account remain unverified. Production D2
requires separate operator authorization. `GLOVO_ENABLED=false` is the documented
kill switch. None of this packet activates Basket or authorizes migration.
