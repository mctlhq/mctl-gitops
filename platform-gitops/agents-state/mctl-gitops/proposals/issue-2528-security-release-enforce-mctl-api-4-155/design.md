# Design: one release gate with verifiable authority and a guarded merge

This revision replaces the 2c3cb1c5 design after its five-P2 AMEND review.
requirements.md defines the invariants; tasks.md defines staged delivery and proof.
Status remains PROPOSED. Editing these files invalidates the old content grant.

## 1. Components and trust boundary

Keep scripts/release-gate.py and platform-gitops/release-gates.yaml/version_holds.
Retain check, verify, diff, --policy-rev and the existing values-block reader.
Add artifact (online evidence), effect (base/candidate classification) and
merge-plan (a read-only, digest-bound pre-merge result). No second release-hold.py.
All external reads use one injected adapter and bounded timeouts. Exit 0 means
observed pass, 6 observed refusal, 7 UNKNOWN; callers stop on either nonzero code.

CI runners do not own production merge authority. A dedicated checker App owns
release-hold checks. A distinct trusted broker owns ordinary merges. Neither
credential is available to model containers, PR worktrees, rendering or generic
Actions jobs. Secrets are provisioned only by the operator; no live Secret reads.

## 2. Immutable packet, approval and allow provenance (P2-1)

Commit a canonical packet under platform-gitops/release-packets/mctl-api/<version>.json
in an inert packet-only PR before requesting deployment approval. Canonical form
is UTF-8 JSON with sorted keys, compact separators and no trailing newline;
reject duplicate keys, unknown fields and noncanonical bytes.

Fields:
- schema_version = mctl-release-packet/v1;
- repository, version and source_repo;
- digest (sha256:64 lowercase hex);
- source_commit, source_tree, release_head, chart_revision (40 lowercase hex);
- release_pr (the API release PR number), policy_digest (sha256:64 hex);
- expires_at (UTC RFC3339 timestamp, seconds, Z suffix).

source_commit is the built tag's commit, not a workflow input ref. source_tree is
that commit's git tree. release_head is the final reviewed API release-PR head,
not the merge commit. Fetch the merged PR, head reviews and git objects; verify
that head and tree, the tag commit and source tree, and chart_revision ==
source_commit. Reject a later main change incorporated in the tag tree. Resolve
annotated tags with bounded peeling and cycle detection. For OCI indexes bind
the index digest, verify the referenced platform manifests/configs by digest and
check revision labels on runnable images. Handle non-runnable attestation
manifests explicitly; do not treat malformed or unknown descriptors as absent.

packet_ref names an immutable GitOps commit and packet path. The approval's
artifact_hash and args_digest must equal sha256(packet bytes), not just the
image digest; its target names packet_ref. Use the existing generic action
approval contract with action_kind release.mctl-api, risk high, side_effect
write, intent_source naming the real release execution, policy_decision
require_approval, and a dedicated policy_rule_id mctl-api.release whose version
is policy_digest. The isolated broker creates the pending request using its dedicated real
MCTL service/requester principal and real release execution identity. The same
requester must consume it: the existing API restricts consumption to the
requester. Do not create under mctl-agent and later consume under another
principal. The checker obtains a read-only preflight result from the broker;
MCTL requester credentials never leave the broker, and preflight never consumes. The owner reads the packet/reference/digest and records a
binding {approval_ref, context_digest, content_digest} through the direct-human
MCTL decision route. No service or agent decides it.

Prove admission/context binding and atomic authority revalidation/consume against
the actual pre-release API version in disposable contract tests before relying
on this path. Respect its registered-policy configuration: do not turn strict
mode off or reuse a DevLoop policy to admit a release. If the dedicated rule
needs registration/capability unavailable in that version, readiness remains
blocked on a separately approved prerequisite; do not deploy a held binary to
bootstrap its own authorization. This is an explicit compatibility gate.

An allow entry contains version, packet_ref, packet_digest, grant (aar_...),
approved_by_principal_id, approved_by_github_id, expires_at, and the packet's
artifact/source/head/chart/policy fields. They must agree byte-for-byte. The
trusted owner list maps approved MCTL principal IDs to GitHub numeric user IDs;
the operator supplies actual IDs. The ledger must record approved state, the
expected intent/context/content binding, that principal, platform_admin basis,
no decided_via principal and a nonempty freshness window. An account name or
GitHub User type alone is not a human authorization proof.

Verify the allow-only PR's immutable merged tree and provenance through GitHub:
only the expected entry changed, it names the same packet/decision, the
configured owner GitHub User ID approved the exact final head, and the configured
broker App merged that head. The direct-human ledger decision is the human
authority proof; a bot review or an account name alone cannot replace it. This
keeps allow publication compatible with broker-only ordinary merge authority.
Protect allow records and packet provenance as policy inputs.

policy_digest hashes canonical JSON of the validated trusted policy with all
allow lists omitted, plus a sorted map of protected enforcement file paths to
blob SHA-256 (gate, reader/renderer, route/apply/shape guards, checker/broker
workflows and authority configuration). The protected-file set is fixed in
trusted code and itself versioned. Require regular files and complete reads.
This avoids self-reference: a grant/allow addition changes no policy digest;
a change to owners, rules or enforcement code does. All planned effects use
the current base's digest. Existing state retains its historical decision;
new effects never inherit an expired/stale authorization.

## 3. Trusted checker and merge authority (P2-2)

Add release-hold-pr.yml on pull_request_target from the default branch. Fetch
refs/pull/<n>/head as git data and compare the API head SHA; pin base SHA too.
Run trusted code and --policy-rev <base> against bounded candidate data. Head
scripts, workflows, local actions and dependencies are never executed/imported.
A separate credential-free rendering worker receives candidate data only.
The dedicated checker App posts release-hold to the exact head; require that
App integration in the ruleset. validate-manifests remains supplementary.

Add release-hold-merge.yml / trusted broker for final merge planning and effect.
Auto-merge must delegate every guarded PR to it rather than gh pr merge itself.
A missing/unavailable broker is a refusal; no owner-merge fallback is documented
as equivalent enforcement.

Enforcement prerequisite, coordinated with #2543: use a separate main update-
authority ruleset (Restrict updates) whose sole ordinary allowed merger is the
isolated broker App, with PR-only allowance. Keep the existing PR/review/required-
check rules in a separate ruleset with NO broker exemption and strict checks true.
The broker must therefore merge PRs and cannot push main directly or skip checks.
No mctl-agents App or admin-role bypass is added. Do not add a new DeployKey
exemption. Existing direct writers must be migrated through #2543's reviewed
trusted-writer/PR path before this restriction is activated. This is not a
silent repository-wide cutover: owner approval, disposable-repo proof, normal
DevLoop/deploy continuity and rollback evidence are required first.

Exact App IDs/environment/ruleset JSON are operator-provisioned artifacts,
validated against the intended capability set. If GitHub cannot enforce this
composition for the repository, the cutover is BLOCKED, never replaced by a
PR-controlled check or a promise to avoid manual merge. Until cutover, report
P2-2/P2-3 as implemented-but-not-enforced at most; release remains NO-GO.

## 4. Merge-time transaction and recovery (P2-3)

The broker serializes guarded merges and loads code/policy from the current
trusted main. It re-reads PR base/head, full diff, packet, allow provenance,
ledger decision, current reviews/checks, git tag/source/tree and registry digests.
Build a merge-plan binding base/head, policy/packet digests, grant, effect type
and a deadline. Require at least 15 minutes left in both packet expiry and API
fresh_until. Right before merging, consume the approval through the API with its
intent hash; the API rechecks current human principal/context/policy authority
and atomically spends it. A failed consume leaves no Git write.

Re-read base/head and artifact evidence after consume; any mismatch stops with
the grant spent and no merge. Then merge with method merge and exact head SHA,
within a 60-second monotonic deadline and before packet/API expiry. Strict checks
must atomically reject an outdated branch at GitHub. Any base change causes a
fresh evaluation/review, not reuse of an earlier merge plan. The broker credential
is the only ordinary merger, so a crash after posting success cannot let another
writer spend a stale green result. Each retry starts from fresh reads.

A consumed grant is never automatically reused for another merge or rollback.
On an ambiguous response, read the merged PR and resulting base to determine
whether exactly the authorized effect landed. If observation fails, stop UNKNOWN.
If it provably did not land, request a new human grant; do not unconsume it.
If it did land, reconcile/mark executed with the original effect identity. Later
pod restarts and unchanged deployments do not consume again. Unrelated releases
are evaluated as steady state for the held workload, not as new release writes.
Registry tag retargeting after the final read is a separate known residual until
a separately reviewed digest-capable API chart is available; do not claim a
repository:tag image is immutable. Any owner acceptance is separate and dated.

## 5. Positive release path and diff classes (P2-4)

Keep post-push detection and pre-merge admission distinct. The existing diff
command's unconditional policy/content alerts must not become a blanket PR
admission rule. effect classifies base and candidate using trusted policy:
- policy/code-only: protected review and owner-controlled broker authorization;
  no deployment effect or allow record bundled with weakened policy;
- packet-only: inert canonical packet, no allow or deployment change;
- allow-only: one version's entry, matching immutable packet/human decision;
  no held workload, packet or enforcement-code changes;
- release-effect: only image.tag and the first API chart targetRevision move,
  both to the packet's version/source_commit, against an allow already in base;
- unrelated: no held deployment/policy effect; existing service rules apply.
Anything mixed or unclassified is refused. Rollback is a new effect requiring
its own exact grant. Never normalize away arbitrary env, paths or Helm changes.

Update BOTH release-deploy.yaml and gitops-bump.yaml producers to construct the
atomic tag+chart patch from trusted packet data. Update release-bump-apply.sh,
release-bump-diff-guard.py, auto-merge's guarded handoff and gate diff together.
The pure shape guard permits the extra chart line only for the one API bootstrap
path, exactly one authorized chart source and a complete tag+pin pair; semantic
validation by the trusted gate remains mandatory. Other services stay tag-only.
Conflicts that touch either bound line cause a fresh base/head evaluation; do
not take a whole file from the patch side or reuse the old grant on a new effect.
No ROLLOUT_MARKER, env, second source or unrelated lines are allowed implicitly.

Policy-only changes and allow-only additions are validated through their own
classes/provenance. The watcher may still flag expected reviewed policy changes
as informational; it must distinguish a verified authorized change, violation
and UNKNOWN rather than suppressing all such changes. Every policy change that
affects an existing release requires an explicit compatibility/rebaseline proof
without treating historical expiry alone as a new write.

## 6. Rendered env graph with complete observation (P2-5)

Retain block_values for inline values extraction. For full Helm inputs use the
trusted pinned Helm executable and explicit source/value profile taken from
GitOps (including candidate overrides). Render the bootstrap and API chart at
the exact candidate pin. Run in a bounded isolated worker with no credentials,
network, kubeconfig, plugins, install hooks, dependency downloads or executable
candidate files. Fetch verified source/dependencies outside the worker first;
regular-file/path/size validation rejects symlinks and escapes.

Strictly parse rendered YAML with duplicate-key detection; parse/render failure,
unsupported profile or unresolved template yields UNKNOWN. There is no raw-text
fallback. Trace actual workload env/envFrom references to desired ConfigMaps,
Secrets, ExternalSecrets and runtime producers across reconciled source paths.
This is graph coverage, not a filename-glob assertion. For each reference record
namespace/name, originating source/pin and exact declared key set. Missing,
ambiguous, computed or newly uncovered references are UNKNOWN.

The zitadel-iac producer needs a machine-readable key contract plus a test that
its source actually writes exactly those keys; a handwritten list alone is not
proof. Dynamic Terraform/Job key sets without such proof remain blocked. Inspect
source and synthetic/rendered desired key names only. Never fetch live Secret
.data (even for key counters) and never run a real Terraform plan with secrets.
The four forbidden names in requirements.md are rejected after rendering and
source resolution at every version. Explicit env.valueFrom keys and prefixes
must be resolved too. A computed/escaped key cannot disappear into a regex scan.

## 7. Staging, dependencies and rollback

Code/fixtures can merge inertly after their own authorization. Capability and
operator cutovers are separate: checker identity, strict rules, broker authority,
producer migration under #2543 and any API policy registration prerequisite must
all be proven before enforcement is certified. No grant is added by this work.
No schema/role/Secret change, API release, Bridge or Basket activation is included.

On failed cutover, keep R0 held and broker gate closed; revert the new inert
wiring through reviewed PRs. Do not remove a required check while opening release
writes, add generic bypass actors or use an unguarded manual merge as recovery.
A broker outage stops guarded merges; authorized break-glass is a separate
incident decision and is not a passing release path.

Protocol references: GitHub documents Restrict updates, integration-specific
required checks and strict up-to-date checks at
https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
and exact-head merge at https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request.
Disposable tests of this exact rule composition are mandatory before production.
