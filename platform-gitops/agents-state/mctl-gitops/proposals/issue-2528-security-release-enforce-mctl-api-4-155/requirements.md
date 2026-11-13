# mctl-api release hold: bound human authority and guarded release effects

Status: PROPOSED. Revision of 2026-11-13 that merges #2604 (base: packet-bound
human decision, broker-only guarded merges, default-branch checker,
credential-free rendering) with #2606 (donor: record-level provenance,
policy_digest, RFC3339 expiry, honest detection) and resolves three independent
reviews (findings A-H, L, M; map in tasks.md). It extends scripts/release-gate.py
and release-gates.yaml version_holds. Merging it authorizes no implementation,
acceptance flip, allow record, release, grant decision or consumption,
ruleset, App, environment, credential, database or production change. Grants
aar_045442c76066428da01870ac379b9d32 and aar_31e2ff84fe6b41b5bf918e79334ca9bd
bind superseded content and must not approve this revision. The coordination
packet is docs/plans/mctl-api-4-155-release-readiness.md.

## Baseline (read 2026-11-13, mctl-gitops main 618cfe917; no Secret data read)

- Hold mctl-api-bootstrap: held_from 4.155.0, allow: [], record field
  `expires` is a YAML date. hold_problems skips tags below held_from;
  run() returns 6 even for an UNKNOWN problem.
- Bootstrap image tag 4.154.0; GHCR resolves ghcr.io/mctlhq/mctl-api:4.154.0 to
  sha256:42d5a572156f179f0f697bd3279fe7817831294d9ccb4a55a91d28b02f9d4488
  (registry read; live pod imageID not observed). Chart pinned to a5b9ef9c.
- Both bump jobs map every nonzero gate exit to 6 (release-deploy.yaml:358-360,
  gitops-bump.yaml:243-245). auto-merge.yml:82 protected_re does not name
  mctl-api.yaml, so a bot-approved claude/* PR can auto-merge it today.
- Ruleset 18465404: bypass DeployKey (null id, always); strict checks TRUE;
  required contexts cloudflare-plan, reserved-hosts, validate (15368) and
  agy-formal-review (5732062); one approval; non_fast_forward and deletion rules.
  Classic protection on main: allow_force_pushes false, enforce_admins false.
- Write deploy keys 165489378 (gitops-bump) and 166128843
  (argo-workflows-bot-2026-10). Every environment has can_admins_bypass true.
  APP_PRIVATE_KEY and AGENTS_APP_PRIVATE_KEY are repository-level secrets,
  readable by a workflow on any branch a writer pushes.
- mctlhq/mctl-api#1022 (OPEN, owner GO 2026-11-13) specifies the fresh,
  MFA-backed decide-page decision; the existing DevLoop decide page
  (internal/api/handlers_devloop_decide.go) has prompt=login, max_age=0 and
  auth_time but no amr check. #2543 is OPEN.

## Required behavior

### R0. The only human signal is a #1022 ledger decision (A)

- mctl-api#1022 is a hard prerequisite: until it is released and contract-tested,
  readiness is BLOCKED. Every owner decision this proposal relies on (packet
  release grant, policy change, owners change) is a fresh browser decision on a
  decide page modelled on handlers_devloop_decide.go: prompt=login, max_age=0,
  auth_time not earlier than the challenge start, amr containing a second
  factor (mfa, hwk or swk), the decide page's own client ID only. Bearer and MCP
  routes refuse these intents for every principal, including the owner.
- The ledger record carries decider principal ID, auth_time, amr, client_id,
  challenge ID and the binding digests. The gate and broker verify that record
  through a read-only API call. A GitHub login, review, merge, environment
  approval or App approval is never a human signal; an agent holding the
  owner's gh or MCP token produces none that counts.
- "Green gate = merge without asking" never applies to packet, allow or policy
  PRs, nor to release-effect PRs. Failed ledger reads are UNKNOWN.

### R1. Authorization binds the whole release

- A held release names a committed canonical packet, a #1022 decision bound to
  sha256(packet bytes), and an allow record merged by the broker.
- The packet binds repository/version/image digest, API release PR, reviewed
  release_head, source_commit/source_tree, chart_revision == source_commit,
  policy_digest and RFC3339 UTC expires_at. The tag resolves to source_commit;
  tree(source_commit) == source_tree == tree(release_head); the image revision
  label equals source_commit. packet_ref is first-parent reachable from main.
- The allow record copies the packet fields, names its allow_pr and the
  decision ID, and passes record-level provenance: the first-parent commit that
  last changed it is the merge commit of allow_pr, merged by the broker App,
  changing only allow entries. A deploy-key edit of an existing record makes the
  record absent. `expires` is replaced by quoted `expires_at`
  (YYYY-MM-DDTHH:MM:SSZ); the old field is malformed.
- policy_digest covers the hold minus allow lists plus protected enforcement
  file hashes. Expiry and policy_digest gate new writes and merges only, never
  deployed state, pod restarts or unrelated releases.

### R2. Trust never comes from PR-controlled code (E)

- release-hold is computed on pull_request_target by default-branch code that
  reads the candidate only as git data, and is posted by a dedicated checker App
  whose integration ID the ruleset requires.
- Checker and broker run only in environments restricted to main, with
  can_admins_bypass false and environment-scoped secrets; their workflows refuse
  any ref other than refs/heads/main. No workflow_dispatch from another branch
  can reach their credentials. Repository-level App keys are a listed risk
  with a migration task.

### R3. The broker validates every guarded merge

- The broker is the sole ordinary merger. Before every guarded merge it re-reads
  base/head, trusted policy and its provenance (B), effect class, the ledger
  decision, checks and, for release effects, packet, allow provenance, expiry,
  tag/source/tree/digest/chart. Strict checks and the exact head SHA bind
  GitHub's merge. App approvals (e.g. mctl-agy-reviewer[bot]) and owner-login
  GitHub approvals never count toward human authority.
- A deployment grant is consumed only for a release or rollback effect, after
  all reads pass, with at least 15 minutes of freshness and packet expiry left;
  merge within 60 seconds. Ambiguity is reconciled, never retried blindly.

### R4. The authorized path works and fails closed

- Classes: policy, packet-only, allow-only, release-effect, unrelated; mixed or
  unclassified is refused. A release effect moves exactly the API tag and chart
  pin. Both bump producers, apply, shape guard, auto-merge handoff and diff agree.
- Exit codes: 0 pass, 6 refused, 7 UNKNOWN; 7 outranks 6 and is preserved
  through run(), both bump jobs and every caller (G).

### R5. The hold covers the image anywhere (C, D)

- A repo-wide scan of rendered manifests finds every reference to the held
  repository, keyed on repository, not on the hold file. A new or unparseable
  reference is UNKNOWN. Admission is cluster-wide.
- While the hold is in force, any mctl-api tag other than the pinned baseline
  4.154.0@sha256:42d5a572... needs a record, including tags below held_from.
- build-image refuses to overwrite an existing tag of the held repository (no
  commit-named exception) and confirms the pushed digest. Steady-state
  verification compares the registry digest and pod imageIDs with the pin.

### R6. Rendered env sources fail closed

- Trusted pinned Helm render, strict duplicate-key parsing, no regex fallback.
  Resolve env/envFrom/valueFrom through reconciled sources and producer key
  contracts. MCTL_BRIDGE_ENABLED, MCTL_BRIDGE_PROVIDERS,
  MCTL_BRIDGE_PROVIDER_TOKENS and MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE are
  forbidden at every version. Rendering has no credentials, network or plugins;
  never read live Secret payloads.

### R7. Detection is honest (L, H, M)

- The in-repo watcher runs from the pushed commit and is not a control. A
  detector in a repository no mctl-gitops write credential can change, running a
  pinned gate SHA, plus a heartbeat whose absence alerts, is a GO precondition.
- Expiry is judged at the GitHub-recorded time of the first-parent merge commit
  that introduced the effect, never the detector clock or a committer date.
- The first-parent walk is sound only while the previously observed tip stays on
  the new tip's first-parent chain and allow_force_pushes false and the
  non_fast_forward rule are observed; otherwise violation or UNKNOWN.

### R8. Residual risk is accepted, named and compensated (F)

- Choice: accepted risk plus compensating detection, not remediation before
  4.155.0. The owner accepted it in chat on 2026-11-13. A dated GitHub record by
  the owner (scope 4.155.0, expiry, incident and rollback owner) naming deploy
  keys 165489378 and 166128843, cluster-admin overrides, P9 env injection and
  repository-level App keys is a GO precondition; it is not fabricated here.
- No new or wider bypass is added. These paths stay ACCEPTED-RISK, never
  reported as enforced, until #2543 lands.
