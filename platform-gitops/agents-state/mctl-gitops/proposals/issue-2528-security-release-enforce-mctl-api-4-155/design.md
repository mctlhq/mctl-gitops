# Design: one release gate with verifiable human authority and a guarded merge

requirements.md defines the invariants and the verified baseline; tasks.md the
staged delivery, tests and finding map. Status PROPOSED. Any edit changes the
content digest and needs a fresh review and a fresh digest-bound decision.

## 0. Write-path inventory

| # | Path | Control after this design | Status |
|---|---|---|---|
| P1/P2 | release-deploy.yaml / gitops-bump.yaml bump | check before write, exit 7 kept, pre-push diff, direct route refused for held | ENFORCED after tasks 2-4 |
| P3 | Human or agent PR | checker (§4), broker-only merge (§5) | ENFORCED after cutover (task 9) |
| P4 | claude/* auto-merge | mctl-api.yaml in protected_re (task 0), broker handoff | GAP TODAY until task 0 |
| P4b | release-bump/* by mctl-gitops-pr App | auto-merge hands held PRs to the broker; await-bump skipped | ENFORCED after tasks 5, 7 |
| P5 | Deploy keys 165489378, 166128843 | provenance makes pushed records absent; detector §8 | ACCEPTED-RISK (§9) |
| P6 | Repo-level APP_PRIVATE_KEY, AGENTS_APP_PRIVATE_KEY | migration to main-only environments (task 8) | ACCEPTED-RISK until migrated |
| P7 | Chart source revision | 40-hex pin; moves only with the tag in a release effect | ENFORCED after task 2 |
| P8 | Argo CD override, kubectl by cluster-admin | cluster-wide admission (§7), selfHeal | ACCEPTED-RISK (§9) |
| P9 | envFromOptionalSecrets (zitadel-iac) | env graph (§7.3), Secret admission | ACCEPTED-RISK until both live |
| P10 | Other manifest naming ghcr.io/mctlhq/mctl-api | repo-wide image scan (§7.1) | ENFORCED after task 6 |
| P11 | GHCR tag overwrite or lower tag | no-overwrite, pinned digest, any-new-tag rule (§7.2) | detection for other GHCR writers |

## 1. Components, trust boundary, exit codes

Keep scripts/release-gate.py (check, verify, diff, --policy-rev, values-block
reader) and release-gates.yaml version_holds. Add policy-digest, artifact
(online evidence), effect (classification) and merge-plan (read-only,
digest-bound). No second script or policy file. All external reads go through
one injectable adapter with bounded timeouts.

Exit 0 pass, 6 refused, 7 UNKNOWN; 7 outranks 6. run() returns 7 when any
problem is UNKNOWN. The bump jobs replace `sys.exit(6)` at
release-deploy.yaml:358-360 and gitops-bump.yaml:243-245 with
`sys.exit(7 if rc == 7 else 6)` and print "could not observe" for 7;
release-preflight.py check_gate does the same. Every caller still stops on any
nonzero code.

A dedicated checker App owns release-hold; a separate broker App owns ordinary
merges. Neither key is a repository secret: each lives in its own environment
(release-hold-checker, release-hold-merge) whose deployment branch policy is
main only, can_admins_bypass false. The workflows also refuse
`github.ref != 'refs/heads/main'`. pull_request_target runs with the base ref,
so the checker environment admits it. No model container, PR worktree, render
worker or generic Actions job sees either key. The operator provisions them;
nothing here reads Secret data.

## 2. Human decision, packet and allow record

### 2.1 Decision (#1022)

Authority comes only from a ledger decision made on the #1022 decide page:
fresh ZITADEL login (prompt=login, max_age=0), auth_time >= challenge start,
amr containing mfa, hwk or swk, ID token audience equal to the decide page client
ID held in trusted policy. Bearer and MCP routes refuse these intents. The
record stores principal ID, auth_time, amr, client_id, challenge ID, intent and
binding digests. The gate verifies all of them plus principal ID in the hold's
`owners` (MCTL principal IDs; GitHub logins are not authority inputs) and state
approved. Intents: release.mctl-api (binds packet digest, consumable once) and
policy.mctl-gitops.release-hold (binds PR head SHA and resulting policy_digest).

The broker creates the pending release request with its own MCTL service
principal and is the only consumer (the API restricts consumption to the
requester). Preflight reads never consume. If the pre-release API lacks
registration or capability for these intents, readiness stays BLOCKED; never
weaken strict policy, reuse a DevLoop policy, or deploy a held binary to
bootstrap its own authorization.

### 2.2 Packet

platform-gitops/release-packets/mctl-api/<version>.json, merged by the broker in
an inert packet-only PR before the decision. Canonical UTF-8 JSON, sorted keys,
compact separators, no trailing newline; duplicate or unknown fields and
noncanonical bytes are refused. Fields: schema_version mctl-release-packet/v1,
repository, version, source_repo, digest (sha256:64 hex), source_commit,
source_tree, release_head, chart_revision (40 hex), release_pr, policy_digest,
expires_at (RFC3339 UTC, seconds, Z).

source_commit is the tag commit (merge of the release PR), release_head the
final reviewed PR head; tree(source_commit) == source_tree == tree(release_head),
chart_revision == source_commit. Peel annotated tags with bounded depth and
cycle detection. For OCI indexes bind the index digest, verify each runnable
platform manifest/config and revision label, handle attestation manifests
explicitly; malformed descriptors are UNKNOWN. packet_ref names a commit on
main's first-parent chain (not merely reachable) plus the path.

### 2.3 Allow record and record-level provenance

```yaml
allow:
  - version: "4.155.0"
    allow_pr: <mctl-gitops PR number>
    decision: <ledger approval id>
    packet_ref: "<40 hex>:platform-gitops/release-packets/mctl-api/4.155.0.json"
    packet_digest: "sha256:<64 hex>"
    expires_at: "2026-MM-DDTHH:MM:SSZ"   # <= packet expires_at
    # digest, source_commit, source_tree, release_head, chart_revision,
    # policy_digest copied byte-for-byte from the packet
```

For record R of version V at policy revision P:
1. Walk `git rev-list --first-parent P -- platform-gitops/release-gates.yaml`
   newest first; the first commit C where canonical(R@C) != canonical(R@C^1)
   (absent is a value) is L. Shallow history, git error or no L is 7. Line-based
   `git log -L/-S` is not used.
2. GET commits/L/pulls must return allow_pr with merged_at set and
   merge_commit_sha == L; none is 6 (a deploy-key or direct push), API error 7.
3. merged_by is the configured broker App; the paginated file list (count equal
   to changed_files, else 7) is a subset of {release-gates.yaml, admission
   params}; diff L^1 L classifies allow-only; the record's decision verifies
   (§2.1) against the packet at packet_ref, read through the immutable merged
   tree. The decision is verified, not consumed.

A deploy-key edit of an existing record's digest becomes L and fails step 2; a
record carried unchanged keeps its provenance.

## 3. policy_digest, policy provenance and expiry

policy_digest = "sha256:" + sha256(canonical(H)), where H is the hold mapping
from yaml.safe_load with `allow` removed, plus key `protected_files`: a sorted
map of protected enforcement paths (gate, reader/renderer, route/apply/shape
guards, checker/broker/auto-merge/bump/watch workflows, admission policy) to
blob SHA-256. canonical is json.dumps(sort_keys=True, separators=(",", ":"),
ensure_ascii=False) in UTF-8. A non-JSON value (YAML date, set) is 7. Other
holds and gates are outside H, so a worker min_tag raise or an added allow
changes nothing; owners, held_from, runtime keys, guarded paths, chart_pin,
file or protected code do. `release-gate.py policy-digest --hold NAME
[--policy-rev REV]` prints it.

Policy provenance (B): every first-parent commit after the cutover anchor C0
that changed H must be the merge commit of a broker-merged PR carrying a
verified policy decision bound to its head and the new digest. C0 is pinned by
SHA in broker configuration and in the out-of-repo detector, and is itself
recorded by a policy decision. The broker refuses all guarded merges while the
current main policy fails this check (6) or cannot be checked (7). Owners
cannot be added by the PR that uses them: authority is read at L^1.

Expiry: expires_at is a quoted RFC3339 UTC string; unquoted values and the old
`expires` field are malformed. allow is empty, so nothing migrates. Margin 15
minutes at push and merge, 0 in check. verify keeps the existing rule: a
deployed held version needs only an existing record, so lapse or policy drift
never freezes restarts or other releases.

## 4. Trusted checker (release-hold-pr.yml)

pull_request_target, environment release-hold-checker. Checks out base SHA with
persist-credentials false, copies the gate and hashed requirements to
RUNNER_TEMP, runs `python3 -I` with --policy-rev <base>. Fetches
refs/pull/<n>/head as data and refuses (7) unless it equals head_sha. Head
scripts, workflows, actions and dependencies are never executed or imported; a
separate credential-free render worker gets candidate data only. Exit 7 never
posts success. validate-manifests stays supplementary.

## 5. Broker and merge-time transaction (release-hold-merge.yml)

Restrict updates on main through a separate ruleset whose bypass actors are the
broker App and the existing DeployKey class only (the accepted residual, not
widened). 18465404 keeps PR/review/strict checks with no broker exemption, so
the broker must merge PRs and cannot push or skip checks. No mctl-agents App or
admin bypass. If GitHub cannot enforce this composition, cutover is BLOCKED.

protected_re conflict: today auto-merge.yml leaves protected paths open "for a
human merge". After cutover humans cannot merge, so that branch changes to a
handoff: auto-merge never merges a protected or held PR and dispatches the
broker instead; the broker's class rules replace the human-merge rule.
Before cutover, protected PRs stay human-merge and release stays NO-GO.

Per guarded merge, serialized, code and policy from current main:
1. Read PR (open, same repo, head == head_sha), base tip, policy provenance
   (§3), class, checks. App approvals never satisfy human review; GitHub review
   or merge identity never substitutes for a decision.
2. Policy class: verify a policy decision bound to head and new digest.
   Packet-only and allow-only: verify, never consume. Release or rollback
   effect: re-read packet, allow provenance, decision, tag/tree/registry digests.
3. Build merge-plan (base, head, digests, decision, class, deadline); require 15
   minutes left in packet expiry and API fresh_until. Consume atomically with
   the intent hash; a failed consume leaves no Git write.
4. Re-read base/head/artifacts; mismatch stops with the grant spent.
5. PUT merge with sha=head_sha, method merge, within 60 seconds. Strict checks
   reject an outdated base. Each retry starts from fresh reads.

A consumed grant is never reused. On an ambiguous response read the PR and base:
landed means reconcile once; provably not landed means a new decision;
unobservable stops UNKNOWN. A broker outage stops guarded merges; break-glass
is an incident, not a release path.

## 6. Effect classes and producers (P4b)

effect classifies base vs candidate with trusted policy: policy (H or protected
code), packet-only, allow-only (one entry, matching packet and decision),
release-effect (exactly image.tag and the first API chart targetRevision, to the
packet's version and source_commit, against an allow already in base),
unrelated. Mixed or unclassified is refused; never normalize env, paths or Helm
changes. Rollback is its own effect and grant. Post-push detection
distinguishes authorized change, violation and UNKNOWN instead of alerting on
every policy change.

check gains `--route` and prints held=true|false; a held version on the direct
route is refused. Before every push the last command is `diff --context push
--expiry-margin 15m --since START_SHA`, re-reading everything; a changed
policy_digest since START_SHA aborts. Both producers build the tag+pin patch
from packet data; release-bump-apply.sh, release-bump-diff-guard.py and the
auto-merge handoff accept the extra chart line only for the API bootstrap file.
await-bump runs only when held == 'false'; for a held PR the run summary says
"awaits release-hold-merge" and ends; a missing held output counts as held.

## 7. Image coverage, admission and env graph

### 7.1 Repo-wide image scan (C)

verify renders every Argo source under platform-gitops (bootstrap, services,
infra components) and collects every container image whose repository is a
held repository, wherever it appears. Any reference outside the hold file, a
reference that does not parse as repository[:tag][@digest], or a render that
fails is UNKNOWN (7) for that hold. Fixed globs are not coverage.

### 7.2 Tags and digests (D)

While a hold is in force, the only tag admitted without a record is the pinned
baseline {4.154.0, sha256:42d5a572156f179f0f697bd3279fe7817831294d9ccb4a55a91d28b02f9d4488}
in policy; any other tag, below or above held_from, needs a record. The
existing no-overwrite check (release-preflight.py check_tag_free, exits 10/11)
loses its commit-named exemption for held repositories, and build-image re-reads
the tag after push and fails if it does not resolve to the digest just built.
Other packages:write holders can still retarget a tag: the detector and a
post-sync verifier compare registry digest and pod imageIDs with the pin or
record and alert on mismatch or unreadable state. The chart renders
repository:tag, so admission checks the tag; digest enforcement at admission
needs a separately reviewed digest-capable chart and stays a named residual.

### 7.3 Admission and env graph

A ValidatingAdmissionPolicy bound cluster-wide (all namespaces) denies Pods,
ReplicaSets and Deployments using ghcr.io/mctlhq/mctl-api outside the baseline
or a listed record, the forbidden env names, and Secrets carrying them in
mctl-api. [Warn, Audit] first, failurePolicy Fail, paramNotFoundAction Deny;
[Deny] in a separate PR after a clean sync. The params file changes only in an
allow-only PR.

Rendering: trusted pinned Helm, explicit value profile, isolated bounded worker
without credentials, network, kubeconfig, plugins, hooks or dependency
downloads; symlinks and escapes refused. Strict duplicate-key parsing; failure
is UNKNOWN, no raw-text fallback. Trace env/envFrom/valueFrom to desired
ConfigMaps, Secrets, ExternalSecrets and runtime producers. zitadel-iac needs a
machine-readable key contract tested against its source. Never fetch live
Secret .data or run a real Terraform plan.

## 8. Detection (L, H, M)

The in-repo watcher (release-gate-watch.yml) runs the workflow and script of
the pushed commit, so a push editing them disables its own detection. It stays
as a cheap check and is never counted as a control.

Out-of-repo detector (D7): a repository no mctl-gitops write credential can
change, every 15 minutes, gate pinned by reviewed SHA, full-history read-only
clone. It stores the last observed tip T. New tip T' must have T on its
first-parent chain, else FIRST_PARENT_REWRITE violation (a fast-forward can
graft a fabricated first-parent history). It also reads classic protection
allow_force_pushes and the non_fast_forward rule each run; a changed or
unreadable value is a violation or UNKNOWN. For each new first-parent commit C
it runs `diff --base C^1 --head C --context push`, judging expiry at the
GitHub-recorded merged_at of the PR whose merge commit is C; a commit with no
provenance PR is judged without a time and violates. Exit 6 alerts "violated",
anything else nonzero "could not observe". A heartbeat to an independent
channel; its absence for 45 minutes alerts. Lag, schedule drops and the
detector repository's own admins are part of the accepted residual.

## 9. Residual risk (#2543): accepted, compensated

Both write deploy keys can push any path to main with no PR or check: tag,
policy, records and params in one commit. Write, PR and merge controls do not stop that. What remains:
such a record has no broker PR and is absent for every later write; policy
provenance fails and the broker stops; the detector alerts. Cluster-admin can
override admission (P8); optional Secret env injection (P9) is open until the
graph and Secret admission are live; repository-level App keys (P6) are
branch-readable until migrated. The owner chose accept-plus-detect in chat on
2026-11-13; the dated GitHub record naming exactly these paths and the live
detector are GO preconditions. Nothing here changes keys or rulesets.

## 10. Staging and rollback

Code and fixtures merge inertly after their own authorization. Cutovers
(checker App, environments, ruleset composition, auto-merge handoff, admission
Deny) are separate owner/operator steps after disposable-repository proof and
DevLoop/deploy continuity. On failed cutover keep the hold and broker closed and
revert through reviewed PRs. Remove the release-hold required context before
deleting its workflow, never after. No step touches releases, images,
credentials, deploy keys or Bridge state.

## Owner decisions

- D1 release-hold context bound to the checker App in 18465404.
- D2 checker App (checks write) and broker App (contents, pull_requests write),
  each key only in its main-only environment; neither is the mctl-agents App.
- D3 the dated GitHub residual-risk record (§9).
- D4 GHCR read credential for gate and broker.
- D5 admission Deny.
- D6 cluster-admin disposition (P8).
- D7 detector repository, not writable by any credential that writes mctl-gitops.

References: rulesets https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets ;
exact-head merge https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request .
