"""Wiring of the PR-based release bump route (mctlhq/mctl-gitops#2543, stage 1 fast track).

Static checks on release-deploy.yaml, gitops-bump.yaml, auto-merge.yml and
claude-review.yml, and a mutation run: each named mutation of the workflow text
must turn at least one check red. Plain script:
`python3 tests/test_release_bump_pr_route.py`.

What is held: the PR route writes only to a release-bump/* ref, never to main;
the release gate and the tag-only guard run before that push; the job that
prepares the bump holds no credential; the deploy-key push stays confined to the
direct route; the PR is enqueued by the enqueue-bump job of both workflows
(after publish-pr, in the app-gitops-pr environment), and auto-merge.yml no
longer handles release-bump PRs. The enqueue job's wiring and its guards are
tested in tests/test_release_bump_enqueue.py.
"""
import copy
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows"
failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(f"{name}: {detail}")


def load(text):
    return yaml.safe_load(text)


def steps_text(job):
    return "\n".join(str(s.get("run", "")) + "\n" + str(s.get("uses", "")) + "\n" + str(s.get("with", "")) + "\n" + str(s.get("env", ""))
                     for s in job.get("steps", []))


def step(job, name_part):
    hits = [s for s in job["steps"] if name_part in str(s.get("name", ""))]
    return hits[0] if len(hits) == 1 else None


def judge(files):
    """files: dict name -> text. Returns [(check name, ok)]."""
    out = []
    for label, fn in (("release-deploy", "release-deploy.yaml"), ("gitops-bump", "gitops-bump.yaml")):
        doc = load(files[fn])
        jobs = doc["jobs"]
        bump, pd, pp = jobs.get("bump"), jobs.get("publish-direct"), jobs.get("publish-pr")
        out.append((f"{label}: bump, publish-direct and publish-pr exist", all([bump, pd, pp])))
        if not all([bump, pd, pp]):
            continue
        btxt = steps_text(bump)
        out.append((f"{label}: the bump job pushes nothing", not re.search(r"\bgit push\b", btxt)))
        out.append((f"{label}: the bump job has no environment", "environment" not in bump))
        out.append((f"{label}: the bump job reads no secret and no deploy key",
                    "secrets." not in str(bump) and "ssh-key" not in str(bump) and "DEPLOY_KEY" not in str(bump)))
        out.append((f"{label}: the bump job checks out main without persisting credentials",
                    any(s.get("uses", "").startswith("actions/checkout") and s.get("with", {}).get("persist-credentials") is False
                        and s["with"].get("ref") == "main" for s in bump["steps"])))
        out.append((f"{label}: the bump job reads permissions: contents: read only", bump.get("permissions") == {"contents": "read"}))
        out.append((f"{label}: the route comes from release-bump-route.py with the image bound through env",
                    "scripts/release-bump-route.py --image \"$IMAGE_NAME\"" in btxt and "inputs.image_name" not in str(step(bump, "Decide how").get("run", ""))))
        out.append((f"{label}: the route is exposed as a job output", "route" in bump.get("outputs", {}) and "has_change" in bump.get("outputs", {})))
        # exclusive conditions
        out.append((f"{label}: publish-direct runs only for route == direct", "route == 'direct'" in pd.get("if", "") and "has_change == 'true'" in pd.get("if", "")))
        out.append((f"{label}: publish-pr runs only for route == pr", "route == 'pr'" in pp.get("if", "") and "has_change == 'true'" in pp.get("if", "")))
        # direct route
        dtxt = steps_text(pd)
        out.append((f"{label}: publish-direct is the gitops-bump environment", pd.get("environment") == "gitops-bump"))
        out.append((f"{label}: publish-direct keeps the deploy key", "GITOPS_BUMP_DEPLOY_KEY" in dtxt))
        out.append((f"{label}: publish-direct verifies with the trusted policy before it pushes",
                    re.search(r"release-gate\.py verify --policy-rev origin/main", dtxt) is not None
                    and dtxt.find("release-gate.py verify") < re.search(r"^\s*(?:if )?git push\b", dtxt, re.M).start()))
        # both publishing jobs apply the patch through the conflict-resolving script
        out.append((f"{label}: publish-direct applies the patch through release-bump-apply.sh and never a bare git am",
                    'bash scripts/release-bump-apply.sh "$RUNNER_TEMP/bump-patch/bump.patch"' in dtxt and "git am" not in dtxt))
        # PR route
        ptxt = steps_text(pp)
        out.append((f"{label}: publish-pr applies the patch through release-bump-apply.sh and never a bare git am",
                    'bash scripts/release-bump-apply.sh "$RUNNER_TEMP/bump-patch/bump.patch"' in ptxt and "git am" not in ptxt))
        out.append((f"{label}: the bump branch is keyed by the image basename in both workflows",
                    'SERVICE=$(basename "$IMAGE_NAME")' in str((step(pp, "Open the release-bump") or {}).get("run", ""))))
        out.append((f"{label}: publish-pr is the app-gitops-pr environment", pp.get("environment") == "app-gitops-pr"))
        out.append((f"{label}: publish-pr never touches the deploy key", "DEPLOY_KEY" not in ptxt and "ssh-key" not in ptxt and "gitops-bump" not in str(pp.get("environment"))))
        tok = step(pp, "write token")
        w = (tok or {}).get("with", {})
        perm = {k: v for k, v in w.items() if k.startswith("permission-")}
        out.append((f"{label}: the App token asks for contents and pull-requests write on mctl-gitops only",
                    perm == {"permission-contents": "write", "permission-pull-requests": "write"} and w.get("repositories") == "mctl-gitops"
                    and w.get("owner") == "mctlhq" and "GITOPS_PR_APP_PRIVATE_KEY" in str(w)))
        pushes = re.findall(r"^\s*git push[^\n]*$", ptxt, re.M)
        out.append((f"{label}: publish-pr pushes exactly once, to a refs/heads/ ref held in the release-bump/ variable",
                    len(pushes) == 1 and re.fullmatch(r'\s*git push --force origin "HEAD:refs/heads/\$\{branch\}"', pushes[0]) is not None))
        out.append((f"{label}: that variable is under release-bump/ and refused otherwise",
                    'branch="release-bump/${SERVICE}-${NEW_TAG}"' in ptxt and 'case "$branch" in release-bump/?*) ;;' in ptxt))
        out.append((f"{label}: publish-pr has no push to main in any spelling",
                    not re.search(r"git push[^\n]*(\bmain\b|HEAD:main|--mirror|--all|\+)", ptxt.replace("--force", ""))))
        gate = ptxt.find("release-gate.py verify --policy-rev origin/main")
        guard = ptxt.find("release-bump-diff-guard.py")
        push = ptxt.find("git push")
        out.append((f"{label}: publish-pr runs the gate and the tag-only guard before the push", 0 < gate < push and 0 < guard < push))
        out.append((f"{label}: publish-pr re-authors the commit as the App bot",
                    "mctl-gitops-pr[bot]" in ptxt and "--reset-author" in ptxt and "Agent: none" in ptxt))
        out.append((f"{label}: publish-pr opens the pull request idempotently",
                    "gh pr list" in ptxt and "--state open" in ptxt and "gh pr create" in ptxt))
        out.append((f"{label}: publish-pr holds contents: read for GITHUB_TOKEN", pp.get("permissions") == {"contents": "read"}))
        # supersede older bumps (behaviour is run in test_release_bump_supersede.py)
        out.append((f"{label}: publish-pr records the pull request number as a step and job output",
                    'echo "pr=${pr}" >> "$GITHUB_OUTPUT"' in ptxt and (step(pp, "Open the release-bump") or {}).get("id") == "open_pr"
                    and pp.get("outputs", {}).get("pr") == "${{ steps.open_pr.outputs.pr }}"))
        out.append((f"{label}: publish-pr orders tags with semver_lt, closes only lower tags and fails when a newer bump is open",
                    "semver_lt() {" in ptxt and 'rc=0; semver_lt "$other_tag" "$NEW_TAG" || rc=$?' in ptxt
                    and len(re.findall(r"gh pr close", ptxt)) == 2 and "Not newer than #" in ptxt
                    and re.search(r'is not newer"\n\s*exit 1\n', ptxt) is not None
                    and 'others=$(gh pr list' in ptxt and "set -euo pipefail" in ptxt))
        # the wait: its own job, outside every concurrency group, no secret, read-only
        aw = jobs.get("await-bump")
        out.append((f"{label}: await-bump exists and follows publish-pr", aw is not None and aw.get("needs") == "publish-pr"))
        if aw is not None:
            wt = step(aw, "Wait for the bump to merge")
            wtxt = (wt or {}).get("run", "")
            out.append((f"{label}: await-bump has no environment, no secret, no concurrency group and read-only access",
                        "environment" not in aw and "concurrency" not in aw and "secrets." not in str(aw)
                        and aw.get("permissions") == {"pull-requests": "read"} and aw.get("timeout-minutes") == 55))
            # No lock shared between releases. release-deploy may carry one
            # workflow-level block (mctlhq/mctl-gitops#2993), and only in this
            # shape: `-preview` components built from a `main-<sha>` tag share a
            # cancelling group, everything else resolves to its own run id.
            wc = doc.get("concurrency")
            preview = "endsWith(inputs.component_name, '-preview') && startsWith(inputs.image_tag, 'main-')"
            out.append((f"{label}: the workflow itself is in no concurrency group shared between releases",
                        wc is None or (
                            "release-deploy" in label and isinstance(wc, dict)
                            and " ".join(str(wc.get("group")).split()) == (
                                "${{ " + preview
                                + " && format('release-deploy-preview-{0}-{1}', inputs.team_name, inputs.component_name)"
                                + " || format('release-deploy-{0}', github.run_id) }}")
                            and str(wc.get("cancel-in-progress")) == "${{ " + preview + " }}")))
            out.append((f"{label}: await-bump waits for MERGED and fails on closed, unknown state or timeout",
                        wt is not None and "MERGED)" in wtxt and "was closed without merging" in wtxt and "unexpected pull request state" in wtxt
                        and re.search(r'did not merge within 50 minutes"\n\s*exit 1\s*$', wtxt) is not None
                        and "needs.publish-pr.outputs.pr" in str(wt.get("env")) and "github.token" in str(wt.get("env"))))
            out.append((f"{label}: only a superseded-by comment from the App turns a closed bump into a notice",
                        "Superseded by #" in wtxt and "mctl-gitops-pr(\\\\[bot\\\\])?$" in wtxt and '-gt 0' in wtxt))
        # the enqueue: a plain job after publish-pr (details: test_release_bump_enqueue.py)
        eq = jobs.get("enqueue-bump")
        out.append((f"{label}: enqueue-bump follows publish-pr and reads the PR number from it",
                    eq is not None and eq.get("needs") == "publish-pr" and eq.get("if") == "needs.publish-pr.result == 'success'"
                    and "uses" not in eq and "needs.publish-pr.outputs.pr" in str(eq.get("steps"))))
        out.append((f"{label}: enqueue-bump is in no concurrency group", eq is not None and "concurrency" not in eq))
        # nothing but the two publishing jobs names an environment
        envs = {n: j.get("environment") for n, j in jobs.items() if "environment" in j}
        out.append((f"{label}: only the publishing jobs and enqueue-bump have an environment",
                    set(envs) == {"publish-direct", "publish-pr", "enqueue-bump", "dispatch-formal-review"} and envs.get("enqueue-bump") == "app-gitops-pr"
                    and envs.get("dispatch-formal-review") == "app-dispatch-main", envs))

    am = files["auto-merge.yml"]
    amdoc = load(am)
    job = amdoc["jobs"]["auto-merge"]
    out.append(("auto-merge: release-bump/ heads no longer reach the job", "release-bump/" not in job["if"]))
    out.append(("auto-merge: nothing in auto-merge.yml enqueues", "enqueuePullRequest" not in am))
    out.append(("auto-merge: the claude/ and portal-allowlist/ routes are unchanged",
                "startsWith(github.event.pull_request.head.ref, 'claude/')" in job["if"] and "portal-allowlist/" in job["if"]))
    cr = files["claude-review.yml"]
    out.append(("claude-review: the App may start a review", re.search(r'allowed-bots: "[^"]*\bmctl-gitops-pr\b[^"]*"', cr) is not None))
    return out


FILES = {n: (WF / n).read_text() for n in ("release-deploy.yaml", "gitops-bump.yaml", "auto-merge.yml", "claude-review.yml")}
base = judge(FILES)
for n, ok, *d in [(a, b, *c) for a, b, *c in base]:
    check(n, ok, d)

MUT = [
    ("publish-pr may push to main", "release-deploy.yaml", 'git push --force origin "HEAD:refs/heads/${branch}"', "git push --force origin HEAD:main"),
    ("publish-pr may push to main (gitops-bump)", "gitops-bump.yaml", 'git push --force origin "HEAD:refs/heads/${branch}"', "git push origin HEAD:refs/heads/main"),
    ("branch outside release-bump/", "release-deploy.yaml", 'branch="release-bump/${SERVICE}-${NEW_TAG}"', 'branch="${SERVICE}-${NEW_TAG}"'),
    ("branch guard dropped", "release-deploy.yaml", 'case "$branch" in release-bump/?*) ;;', 'case "$branch" in *) ;;'),
    ("gate dropped from publish-pr", "release-deploy.yaml", "          python3 scripts/release-gate.py verify --policy-rev origin/main\n          git push --force", "          git push --force"),
    ("guard dropped from publish-pr", "gitops-bump.yaml", "run: git diff origin/main..HEAD | python3 scripts/release-bump-diff-guard.py", "run: 'true'"),
    ("deploy key in publish-pr", "release-deploy.yaml", "for the bump pull request\n        id: token\n        uses: actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510 # v3.3.0\n        with:\n", "for the bump pull request\n        id: token\n        uses: actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510 # v3.3.0\n        with:\n          ssh-key: ${{ secrets.GITOPS_BUMP_DEPLOY_KEY }}\n"),
    ("App token widened", "release-deploy.yaml", "          permission-pull-requests: write\n\n      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7\n        with:\n          ref: main\n          token:", "          permission-pull-requests: write\n          permission-workflows: write\n\n      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7\n        with:\n          ref: main\n          token:"),
    ("bump job gets the environment back", "gitops-bump.yaml", "  bump:\n    needs: [validate-inputs, check-digest]\n    runs-on: ubuntu-latest\n", "  bump:\n    needs: [validate-inputs, check-digest]\n    runs-on: ubuntu-latest\n    environment: gitops-bump\n"),
    ("bump job pushes", "release-deploy.yaml", '          git format-patch -1 --stdout > "$RUNNER_TEMP/bump-patch/bump.patch"', '          git push\n          git format-patch -1 --stdout > "$RUNNER_TEMP/bump-patch/bump.patch"'),
    ("both publish jobs run for pr", "gitops-bump.yaml", "needs.bump.outputs.route == 'direct'", "needs.bump.outputs.route != 'x'"),
    ("route interpolated into the shell", "release-deploy.yaml", 'route=$(python3 scripts/release-bump-route.py --image "$IMAGE_NAME")', 'route=$(python3 scripts/release-bump-route.py --image "${{ inputs.image_name }}")'),
    ("direct route loses its gate", "gitops-bump.yaml", "          python3 scripts/release-gate.py verify --policy-rev origin/main\n          git push\n", "          git push\n"),
    ("auto-merge: takes release-bump again", "auto-merge.yml", "startsWith(github.event.pull_request.head.ref, 'portal-allowlist/'))", "startsWith(github.event.pull_request.head.ref, 'portal-allowlist/') || startsWith(github.event.pull_request.head.ref, 'release-bump/'))"),
    ("enqueue-bump renamed away", "release-deploy.yaml", "  enqueue-bump:\n    needs: publish-pr\n", "  enqueue-other:\n    needs: publish-pr\n"),
    ("enqueue-bump joins the publish concurrency group", "gitops-bump.yaml", "  enqueue-bump:\n    needs: publish-pr\n", "  enqueue-bump:\n    needs: publish-pr\n    concurrency:\n      group: gitops-bump\n"),
    ("enqueue-bump in the deploy-key environment", "release-deploy.yaml", "    if: needs.publish-pr.result == 'success'\n    runs-on: ubuntu-latest\n    environment: app-gitops-pr\n", "    if: needs.publish-pr.result == 'success'\n    runs-on: ubuntu-latest\n    environment: gitops-bump\n"),
    ("wait: closed unmerged is success", "release-deploy.yaml", 'echo "::error::release-bump pull request #${PR} was closed without merging"; exit 1', 'exit 0'),
    ("wait: timeout is success", "gitops-bump.yaml", 'did not merge within 50 minutes"\n          exit 1', 'did not merge within 50 minutes"\n          exit 0'),
    ("wait: any closed bump counts as superseded", "release-deploy.yaml", 'if [[ "$sup" -gt 0 ]]; then', 'if true; then'),
    ("wait step removed", "gitops-bump.yaml", "      - name: Wait for the bump to merge\n", "      - name: Something else\n"),
    ("wait moved back into publish-pr", "gitops-bump.yaml", "  await-bump:\n    needs: publish-pr\n", "  await-bump:\n    needs: publish-pr\n    concurrency:\n      group: gitops-bump\n"),
    ("await-bump takes a secret", "release-deploy.yaml", "      - name: Wait for the bump to merge\n        env:\n          GH_TOKEN: ${{ github.token }}\n", "      - name: Wait for the bump to merge\n        env:\n          GH_TOKEN: ${{ secrets.GITOPS_PR_APP_PRIVATE_KEY }}\n"),
    ("await-bump gets write access", "gitops-bump.yaml", "    permissions:\n      pull-requests: read\n", "    permissions:\n      pull-requests: write\n"),
    ("workflow-wide concurrency back", "gitops-bump.yaml", "# a queued bump of another service would be cancelled behind it.\njobs:\n", "# a queued bump of another service would be cancelled behind it.\nconcurrency:\n  group: gitops-bump\n  cancel-in-progress: false\njobs:\n"),
    ("release-deploy: every release shares one group", "release-deploy.yaml", "        || format('release-deploy-{0}', github.run_id) }}\n", "        || 'release-deploy' }}\n"),
    ("release-deploy: semver release of a preview component is cancellable", "release-deploy.yaml", "  cancel-in-progress: ${{ endsWith(inputs.component_name, '-preview') && startsWith(inputs.image_tag, 'main-') }}\n", "  cancel-in-progress: ${{ endsWith(inputs.component_name, '-preview') }}\n"),
    ("newer bump no longer stops this run", "release-deploy.yaml", 'is not newer"\n              exit 1', 'is not newer"\n              true'),
    ("publish-direct applies with a bare git am", "release-deploy.yaml", 'bash scripts/release-bump-apply.sh "$RUNNER_TEMP/bump-patch/bump.patch"\n\n          # Concurrent', 'git am --3way "$RUNNER_TEMP/bump-patch/bump.patch"\n\n          # Concurrent'),
    ("publish-pr applies with a bare git am", "gitops-bump.yaml", 'bash scripts/release-bump-apply.sh "$RUNNER_TEMP/bump-patch/bump.patch"\n          git commit --amend', 'git am --3way "$RUNNER_TEMP/bump-patch/bump.patch"\n          git commit --amend'),
    ("release-deploy branch keyed by component_name", "release-deploy.yaml", '          SERVICE=$(basename "$IMAGE_NAME")\n          branch=', '          SERVICE="${COMPONENT}"\n          branch='),
    ("claude-review: App not allowed", "claude-review.yml", ",mctl-codex,mctl-gitops-pr", ",mctl-codex"),
]
for name, fn, old, new in MUT:
    n = FILES[fn].count(old)
    check(f"mutant anchor exists: {name}", n == 1, f"count={n}")
    mutated = dict(FILES)
    mutated[fn] = FILES[fn].replace(old, new)
    try:
        res = judge(mutated)
        killed = any(not ok for _, ok, *_ in res)
    except Exception:  # a mutation that breaks parsing is also caught, but be explicit
        killed = True
    check(f"mutant killed: {name}", killed)

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("all release-bump PR route checks passed")
