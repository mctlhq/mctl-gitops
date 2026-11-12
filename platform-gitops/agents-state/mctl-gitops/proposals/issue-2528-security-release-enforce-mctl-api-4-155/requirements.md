# mctl-api release hold: bound authority and guarded release effects

Status: PROPOSED / AMENDED after review of content 2c3cb1c5 (five P2).
This proposal extends the existing release-gate.py/version_holds implementation.
It authorizes no implementation, acceptance flip, release, grant consumption,
production configuration, ruleset, credential or database change by being merged.
The pending implementation grant aar_045442c76066428da01870ac379b9d32 binds the
superseded content and must not approve this revision.

## Baseline and scope

Baseline: mctl-gitops dfe61c780b820cb8b73f048441863fbd2edf03df. The bootstrap
image is 4.154.0, the API chart is pinned to a5b9ef9c, version_holds has allow: [],
the API uses the release-bump PR route, and builds stamp the source revision.
Keep one values-block reader and one policy. The five P2 in the independent
review are addressed by the requirements below and mapped in tasks.md.
The canonical coordination packet is docs/plans/mctl-api-4-155-release-readiness.md.

## Required behavior

### R1. Authorization binds the whole release (P2-1)

- A held release must name a committed canonical release packet, a direct-human
  MCTL action approval of that packet and an owner-reviewed, broker-merged allow-record PR.
  Implementation/proposal approvals and deployment approvals are different intents.
- The packet binds repository/version/image digest, API release PR and reviewed
  release_head, source_commit/source_tree, chart_revision, policy_digest and
  RFC3339 UTC expires_at. chart_revision must equal source_commit. The actual
  tag resolves to source_commit; tree(source_commit) equals source_tree and
  tree(release_head); release_head is the final reviewed head of the merged API
  release PR. The image revision label must equal source_commit.
- Human decision context must show the immutable packet reference and digest.
  The gate must verify the ledger intent/target/digests, recorded decision
  binding, decider principal, direct-human authority and exact packet. It must
  verify owner identity against trusted principal IDs and GitHub numeric IDs,
  not free-text approved_by or account type alone.
- The broker must use the API's atomic consume operation to revalidate current
  human authority/context/freshness before a new release merge. Missing authority
  capabilities must block readiness; never substitute SQL writes, a typed actor,
  a bot identity, weaker API policy settings or a string GO.
- Policy hashing excludes allow records to avoid circular grants. It includes
  the trusted owner set, hold rules and protected guard/renderer/workflow code.
  Adding an allow does not change policy_digest; a security policy/code change does.

### R2. Trust does not come from PR-controlled Actions (P2-2)

- A default-branch pull_request_target workflow executes trusted guard and policy
  code; it reads the candidate only as bounded git data. It never runs/imports
  candidate scripts, Actions or dependencies and never exposes checker credentials
  to candidate code or rendering. Pin and verify the fetched PR head and base SHA.
- Its required release-hold result is produced by a dedicated checker App;
  require that integration ID, not the generic GitHub Actions identity.
  PR-defined same-named jobs and removal of validate-manifests steps cannot
  satisfy the gate. No privileged caller workflow comes from a PR head.
- A separate broker holds merge authority. Generic agents, Apps and users must
  not be able to merge guarded PRs using a stale green result. This is a tested
  enforcement prerequisite, not a claim supplied by a workflow convention.

### R3. Validate the deployment-causing merge (P2-3)

- Before every guarded merge, the broker re-reads exact current base/head,
  trusted policy, packet/allow provenance, expiry, tag/source/tree/digest/chart,
  reviews and all required checks. Recheck after every retry; strict checks
  enforce up-to-date base at GitHub's actual merge, and the merge names the head SHA.
- Consume only after all reads pass, with at least 15 minutes left in the API
  freshness window and packet expiry. The merge request has a 60-second deadline;
  do not start/retry after that window. A crash or ambiguous response must not
  release another writer or permit a consumed grant to be replayed.
- The broker is the sole ordinary PR merger, enforced at the repository authority
  boundary described in design.md. A leftover successful status grants nobody
  else merge authority. There is no unsafe manual-merge fallback.
- Existing deployed state is distinct from a new effect: expiry must block new
  tag/chart/runtime changes and rollback writes, not pod restarts or unrelated
  releases whose held deployment is unchanged. Runtime dark-policy checks remain
  mandatory. Failure/partial observation is UNKNOWN, never clean.

### R4. The authorized path must work (P2-4)

- Recognize separate policy/code, release-packet, allow-only and release-effect
  PRs. Reject combining a grant/policy change with its deployment effect.
- Allow-only PRs verify a genuine packet-bound human decision and authorized
  broker merge with an exact-head owner review. They change only one version's allow entry. Policy changes require
  their own protected review and cannot disable the hold implicitly.
- A release-effect PR changes exactly the API tag and chart pin together, as
  authorized by the packet. Wire the producer, patch apply/conflict rules,
  release-bump-diff-guard, auto-merge handoff and diff semantics consistently.
  Other services retain their tag-only behavior. Unrelated edits remain refused.
- Demonstrate the entire positive path on a disposable remote, then show that
  deliberate mutations are rejected without updating main or publishing an
  unauthorized release-bump branch. Do not turn the post-push detector's expected
  policy-change alerts into unconditional denials of all legitimate policy PRs.

### R5. Render and observe env sources fail closed (P2-5)

- Use a trusted pinned Helm renderer for Helm inputs, then strict duplicate-key
  YAML parsing. Do not strip directive lines and fall back to regex on parse
  failure. Malformed/unsupported/unresolved input is UNKNOWN.
- Render the exact candidate bootstrap values and API chart source. Resolve the
  workload's env/envFrom/Secret/ConfigMap references through reconciled GitOps
  sources and declared runtime-producer key contracts. Missing/ambiguous sources,
  new uncovered references, parse failures and dynamic key sets with no proven
  contract block the check. Fixed globs alone do not prove coverage.
- Enforce MCTL_BRIDGE_ENABLED, MCTL_BRIDGE_PROVIDERS,
  MCTL_BRIDGE_PROVIDER_TOKENS and MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE
  as forbidden names at every image version. Scan desired rendered names and
  producer contracts only; never fetch live Secret payloads or real credentials.
- Rendering is isolated, has no credentials, kubeconfig, plugins, hooks, network
  or dependency installation, and is bounded. Candidate chart data is untrusted.
  The normal real baseline must pass; malformed and uncovered inputs must fail.

## Boundaries and implementation gates

- The gate, renderer, checker and broker code can be prepared and tested inertly.
  Owner/operator authorization is separate for installing Apps, environments,
  strict checks or merge-authority restrictions. No such change occurs here.
- R2/R3 require the #2543 trusted-writer migration/authority proof before they
  are certified effective. A mere scoped flag or written acceptance of stale
  checks does not close these P2. No cutover may break ordinary DevLoop/deploys.
- Wildcard DeployKey/direct cluster-admin paths remain separately tracked in
  #2543/P8. Do not expand bypass actors or claim arbitrary production writes
  are prevented while these paths are open. Any owner residual-risk decision
  must name the exact remaining paths; it is not inferred from this proposal.
- The current API chart renders repository:tag, not image.digest. Tag mutation
  after the final check remains an explicit release risk until a separately
  reviewed digest-capable chart is available. It is not disguised as artifact
  pinning by adding an unused values key.
- No allow is added, API release moved, schema migrated, Bridge enabled or
  Basket activated by this implementation proposal. All remain separately held.
