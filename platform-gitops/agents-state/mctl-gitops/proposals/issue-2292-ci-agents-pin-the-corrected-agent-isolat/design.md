# Design: issue-2292-ci-agents-pin-the-corrected-agent-isolat

## Current state

- `.github/workflows/validate-manifests.yml` defines one `validate` job (ubuntu-latest, `contents: read`,
  `fetch-depth: 0`). It runs on `pull_request` and on `push` to `main`. The second trigger matters because
  `gitops-bump.yaml` and `release-deploy.yaml` push straight to main. Each detector is a
  `scripts/validate-*.py` that runs `--selftest` first and then the real check ("a detector that has never been
  seen to fire is not known to work"). Line 262 is the step "Validate agent pod security context", which runs
  `scripts/validate-agent-pod-security.py --selftest` and then the script itself.
- `scripts/validate-agent-pod-security.py` (mctl-gitops#1717) finds agent steps as CWFT templates whose
  `container`/`script` image contains `workflow.parameters.agent_image`. It checks pod `runAsNonRoot`,
  `runAsUser`/`fsGroup` 1000, `seccompProfile: RuntimeDefault`, container `allowPrivilegeEscalation: false`,
  `capabilities.drop: [ALL]`, and the same on initContainers. It fails closed when it matches zero templates.
  It does NOT check `serviceAccountName`, `automountServiceAccountToken`, resources, deadlines, NetworkPolicies,
  RBAC or quota.
- Agent CWFTs: `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-*.yaml`. Seven of them use
  `agent_image`: implement, investigate, reconcile, run, scout, shepherd and usage-collector. Each has exactly
  one `automountServiceAccountToken: false`, for example `cwft-mctl-agents-investigate.yaml:287-290`
  (`serviceAccountName: mctl-agents-runner`, `automountServiceAccountToken: false`,
  `executor.serviceAccountName: mctl-agents-executor`). `approve` and `daily` have no agent step and no
  automount line. Pods carry `podMetadata.labels.app.kubernetes.io/name: mctl-agents`.
- Inputs the auditor reads: `platform-gitops/argo-workflows/config/{sa-and-rbac,networkpolicy,local-workdir-quota}.yaml`,
  `platform-gitops/agent-platform/execution-profiles/*/profile.yaml`, and the egress-proxy policies in
  `platform-gitops/infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml`.
  `allow-agent-ingress` there (#2159) admits a single peer that combines
  `namespaceSelector: kubernetes.io/metadata.name=argo-workflows` with
  `podSelector: app.kubernetes.io/name=mctl-agents`, on port 3128. The pre-#921 auditor misreads this AND-peer
  as namespace-wide, which is the known false positive.
- The auditor design is in
  `platform-gitops/agents-state/mctl-agents/proposals/issue-807-spike-which-kubernetes-primitives-rbac-n/design.md`
  ("1. tools/agent_isolation_audit.py"). It is pure: PyYAML only, no network, no subprocess, stdout only. Its CLI
  is `--gitops-root <platform-gitops> --format json|md`, and its rows are
  `{primitive, scope, status, severity, source, field, detail, recommendation}` with
  `status in enforced|partial|absent|not-observed`. A missing input yields `not-observed`. That proposal is
  `status: merged` (mctl-agents PR #810).
- Precedent for vendoring with provenance: `infrastructure/cloudflare/portal/allowlists/sources.json`
  (`{"servers": {"<id>": {"repo","path","ref","sha"}}}`), checked by `scripts/validate-portal-allowlists.py`
  and refreshed by `.github/workflows/portal-allowlist-vendor.yml`.
- Fixture convention: `scripts/tests/fixtures/<detector>/{valid,invalid}/`.

Deployed state checked:
- `gh issue view 921 -R mctlhq/mctl-agents`: OPEN, "fix(auditor): model NetworkPolicy peers with
  namespaceSelector + podSelector correctly for agent isolation". The prerequisite has not landed.
- `gh api repos/mctlhq/mctl-agents`: `private: false`. The pinned file can be fetched without credentials for
  the byte-identity check.
- Gitops paths read: those listed above in the clone. This change is CI-only and touches no tenant service, so
  mctl MCP tenant/service tools were not called and `$MCTL_GITOPS_ROOT` was not needed.
- Not observed: the auditor's actual post-#921 output. #921 has not merged, so the row format, version fields
  and the initial row set are unverified. See Open questions.

## Proposed solution

### 1. Vendored, pinned auditor (chosen source: vendored copy at a pinned commit)

New directory `scripts/agent-isolation/`:

- `auditor/agent_isolation_audit.py`: a verbatim copy of `tools/agent_isolation_audit.py` from mctlhq/mctl-agents
  at the pinned commit, plus any sibling module it imports. The file is never edited locally.
- `auditor.pin.json`:
  ```json
  {"schema_version": 1,
   "repo": "mctlhq/mctl-agents",
   "commit": "<40-hex sha at or after the #921 merge>",
   "includes": ["mctlhq/mctl-agents#921"],
   "files": [{"source_path": "tools/agent_isolation_audit.py",
              "vendored_path": "auditor/agent_isolation_audit.py",
              "sha256": "<hex>"}],
   "auditor_version": "<value the auditor reports, or null>",
   "output_schema_version": "<value the auditor reports, or null>"}
  ```
- `README.md`: the source, why it is vendored, and the upgrade procedure (section 4).

Why vendor rather than check out mctl-agents at a SHA in CI: the run is hermetic and the gate does not depend
on GitHub at PR time. The bytes being executed are right there in the PR diff, so a reviewer sees the oracle
change. This also follows the existing `sources.json` provenance pattern. The repo is public, so a byte-identity
check against the pinned commit stays cheap. It runs only when the pin or the vendored files change.

### 2. Gate: `scripts/validate-agent-isolation-baseline.py`

This follows the repo convention: Python 3, PyYAML, `--selftest`, and exit 1 on violations.

1. **Pin integrity.** Load `auditor.pin.json`. Validate its schema (40-hex commit, non-empty files). Check that
   the SHA-256 of each vendored file matches. With `--verify-upstream`, also fetch
   `https://raw.githubusercontent.com/<repo>/<commit>/<source_path>` and compare bytes.
2. **Run the auditor** as a subprocess:
   `python3 -I scripts/agent-isolation/auditor/agent_isolation_audit.py --gitops-root <tree> --format json`.
   Any non-zero exit (exit 2 = unreadable input), stderr-only output, unparseable JSON, a missing required row
   field, a status outside the four allowed values, or a duplicate key fails the run. The row key is
   `(primitive, scope, field)`.
3. **Baseline load** (`scripts/agent-isolation/baseline.json`). If the file is missing, fail. Its
   `schema_version` must equal the gate's supported version (1), else fail. Duplicate keys fail.
   `baseline.auditor.{commit,sha256}` must equal the pin, else fail with "auditor upgraded without
   re-baselining". Every row needs `owner in {agent-isolation-gate, validate-agent-pod-security}`, and every
   non-`enforced` row needs `issue`. A `not-observed` baseline row is allowed only as an explicit gap with an
   issue, and it never satisfies `enforced`.
4. **Compare** gate-owned rows:

   | baseline | current | result |
   |---|---|---|
   | enforced | enforced | pass |
   | enforced | partial/absent/not-observed/missing | FAIL regression |
   | partial/absent (gap+issue) | same | pass, listed as open gap |
   | partial | absent | FAIL worsened |
   | gap | enforced | FAIL "gap closed: update baseline in this PR" |
   | gap | not-observed/missing | FAIL recognized object became unknown |
   | (absent from baseline) | any | FAIL unbaselined row |

   Peer check: the peer-required set is every `(primitive, field)` that is `enforced` for all baselined
   agent-step scopes. For each current agent-step scope that is not in the baseline, the gate lists the members
   of that set that are not `enforced` ("new agent step lacks controls of its peers: ..."). The gate also
   applies this check to the baseline file itself. A baselined agent step whose peer-required row is not
   `enforced` must carry an `issue`, so a new weak step cannot slip into the baseline unnoticed. The auditor
   output decides what counts as an agent step: rows from CWFT templates classified as agent steps. The gate
   does not re-implement that heuristic.
5. **Ownership.** Rows whose field belongs to the pod-security validator are tagged
   `owner: validate-agent-pod-security`. Those fields are `runAsNonRoot`, `runAsUser`, `fsGroup`,
   `seccompProfile`, `allowPrivilegeEscalation` and `capabilities.drop` on the container and initContainers. The
   gate records them and skips the comparison. A fixed `POD_SECURITY_OWNED` table in the gate, checked in
   selftest, stops ownership from being reassigned to dodge a check. `readOnlyRootFilesystem`,
   `automountServiceAccountToken`, SA, bindings, NetworkPolicy, quota, `runtimeClassName`, secrets, limits,
   deadlines and fan-out are `agent-isolation-gate`.
6. **Output.** Errors go to stderr. A Markdown summary goes to `$GITHUB_STEP_SUMMARY`: counts by status, every
   open gap with its issue, and the pin commit.
7. **`--regenerate`** (local only) writes a candidate baseline to stdout, or to `--out`, with provenance:
   `schema_version`, `auditor{repo,commit,sha256,auditor_version,output_schema_version}`, `generated_from_gitops`
   (the git SHA of the tree, informational) and `rows[]`. It carries over the existing `owner`/`issue` per key
   and marks new non-enforced rows `issue: null`. Validation then rejects those rows until a human fills them
   in. CI never calls `--regenerate`. The CI invocation has no write path to `baseline.json`.

### 3. CI wiring (`validate-manifests.yml`)

Add a step right after "Validate agent pod security context":

```yaml
- name: Validate agent isolation matrix against baseline (#2292)
  run: |
    set -euo pipefail
    python3 -m pip install --quiet pyyaml
    scripts/validate-agent-isolation-baseline.py --selftest
    scripts/validate-agent-isolation-baseline.py
```

A second step, `if:` the pin or vendored files changed vs. the PR base (computed with `git diff --name-only`,
which the existing `fetch-depth: 0` allows), runs `--verify-upstream`. On `push` it always runs. A fetch failure
fails the step.

### 4. Upgrade procedure (README)

1. Pick a new mctl-agents commit and copy the file(s) verbatim. Update `auditor.pin.json`.
2. Run `--regenerate --out /tmp/new.json` and diff it against `baseline.json`.
3. Commit the new baseline in the same PR. The PR body must include the baseline diff and explain every changed
   status as an interpretation change from the auditor or a GitOps change. Because `baseline.auditor.sha256`
   changes in the same diff, the PR itself shows that the oracle changed, and that is the provenance signal.
4. A GitOps-only PR leaves `baseline.auditor` untouched. Any baseline row diff in such a PR is therefore a
   posture change by construction.

### 5. Selftest and proof

`--selftest` runs:

- Fixture cases under `scripts/tests/fixtures/agent-isolation/{valid,invalid}/`, each holding a baseline plus a
  canned auditor-output JSON. They cover regression, worsened gap, closed gap, not-observed, missing baseline,
  bad schema, duplicate key in baseline, duplicate key in output, pin mismatch, unbaselined row, a gap without
  an issue, a pod-security row reassigned to the gate, and exit-2 / non-JSON auditor output (a stub auditor).
- A #921 semantics fixture: a small gitops tree whose ingress peer is namespace+pod. The real pinned auditor must
  not report it at the namespace-wide status. The namespace-only variant must be reported weaker.
- Mutation replay on a temporary copy of the real `platform-gitops/`:
  (a) unmodified: the gate passes;
  (b) `automountServiceAccountToken: false` removed from `cwft-mctl-agents-investigate.yaml`: the gate fails;
  (c) `podSelector` removed from the `allow-agent-ingress` peer: the gate fails;
  (d) a new template with `image: "{{workflow.parameters.agent_image}}"` and no SA, automount, resources or
  securityContext appended to `cwft-mctl-agents-implement.yaml`: the gate fails with the unbaselined-row error
  and the peer-check error. The selftest also runs `scripts/validate-agent-pod-security.py --dir <copy>` and
  asserts that it fails too, which proves the composed gate catches the pod-security part without duplicating
  it.

## Alternatives

- **Check out mctl-agents at a pinned SHA in CI** (`actions/checkout` with `repository`/`ref`). This is still an
  immutable pin, but every PR run depends on GitHub, and the executed code never appears in a mctl-gitops diff.
  Dropped in favour of vendoring plus a byte-identity check.
- **Publish the auditor as a pip package or container image pinned by digest.** It would need a release
  pipeline in mctl-agents that does not exist for a stdlib+PyYAML script. Could be done later. Dropped as
  overkill.
- **Re-implement the matrix checks in a mctl-gitops script.** This forks the oracle from the #807 report, and
  the two would drift. The issue explicitly asks for the pinned auditor. Dropped.
- **Snapshot test (exact output equality).** Any `detail` text change would fail. It cannot tell a regression
  from an improvement and does not force closed gaps through a deliberate update. Dropped in favour of the
  status-lattice comparison.

## Platform impact

- **Migrations:** none. CI-only. No cluster objects change, and ArgoCD does not sync `scripts/`.
- **Backward compatibility:** existing steps are unchanged. The pod-security validator keeps its ownership.
- **Resource impact:** a few seconds per `validate` run. One small HTTPS fetch, only when the pin changes.
- **Risks and mitigations:**
  - *Pinning a pre-#921 auditor.* The #921 semantics fixture in selftest fails, and `includes` in the pin is
    reviewed.
  - *Auditor row identity unstable across versions.* Only upgrades can change identity, and upgrades must
    re-baseline in a reviewed PR. Duplicate-key detection fails closed.
  - *Every new agent step now needs a baseline edit.* This is intended: the step's controls become reviewed.
  - *Someone accepts a regression by editing the baseline.* That is visible in review because the baseline row
    diff shows `enforced` turning into a gap, and a gap requires `issue`. CODEOWNERS on `scripts/agent-isolation/`
    is recommended (open question).
  - *Implementation started before #921 merges.* Task 1 is gated on it, and the proposal must not be implemented
    until then.

## Open questions

- #921 not yet merged (2026-10-31): this blocks the pin SHA and the real baseline.
- Post-#921 output shape and version fields, whether the auditor is multi-file, whether it emits a row for
  `allow-agent-ingress`, and how agent-step scopes are named. All need verification against the pinned
  revision.
- Initial accepted gaps and owning issues (G1-G6 from the #807 report and later follow-ups) to confirm at
  generation time.
- Whether to add a CODEOWNERS entry for `scripts/agent-isolation/`.
