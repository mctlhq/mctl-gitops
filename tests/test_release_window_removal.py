"""release-window-removal-pr.yml: the wiring that keeps a window REMOVAL safe.

Plain script: `python3 tests/test_release_window_removal.py`.

The sibling of release-window-pr.yml (docs/plans/sync-window-write-path.md,
section 6): it opens a release-window-removal/<id> pull request that deletes ONE
deny window and queues it for merge, with the mctl-gitops-pr App token. The
rules of the add workflow hold here too (trigger, main-only environment, no
write grant, inputs checked before the token, only a ref push under the removal
prefix, the enqueue only in the separate enqueue-window job), and are checked
with the same function. What is specific to a removal, each with a mutant that
has to turn it red:
  * the hash is the REMOVAL hash (hash-remove), so an approval to add a window
    is a different number and cannot be spent here;
  * the window must exist exactly once before the edit, and the render after
    must equal the render before minus that window;
  * the edit must be a pure deletion (no added line) of one file;
  * the branch is under release-window-removal/ and the queue gate runs with
    WINDOW_KIND=remove, which is what makes it demand a deletions-only diff;
  * it does not call the add tool (render-sync-window.py, `insert`).
"""
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_release_window_pr as add  # noqa: E402  (shared wiring checks)

WF = ROOT / ".github/workflows/release-window-removal-pr.yml"

ORDER = ["Check the inputs", "Generate a write token", "actions/checkout", "Check the approval is still current",
         "Rebuild the window and check it is the approved one", "Remove the window from the project template",
         "Check the edit changed nothing else", "Open the removal pull request"]


def problems(text):
    out = []
    doc = yaml.safe_load(text)
    on = doc.get(True, doc.get("on"))
    if set(on) != {"workflow_dispatch"}:
        out.append(f"triggers are {sorted(map(str, on))}, expected only workflow_dispatch")
    if doc.get("permissions") != {}:
        out.append("workflow-level permissions are not {}")
    if list(doc["jobs"]) != ["open-pr", "enqueue-window"]:
        out.append("the workflow jobs are not exactly open-pr and enqueue-window")
    job = doc["jobs"]["open-pr"]
    ejob = doc["jobs"].get("enqueue-window", {})
    out += add.enqueue_problems(ejob)
    if set(job.get("outputs", {})) != {"pr", "head"}:
        out.append("open-pr must hand the PR number and the pushed head to enqueue-window, nothing else")
    if doc.get("concurrency") is not None or ejob.get("concurrency") is not None:
        out.append("enqueue-window must stay outside any concurrency group (it waits up to 50 minutes)")
    c = job.get("concurrency") or {}
    if c.get("group") != "release-window-pr" or c.get("cancel-in-progress") is not False:
        out.append("open-pr is not serialised in the release-window-pr group (shared with additions) without cancelling")
    if job.get("environment") != "app-gitops-pr":
        out.append("job is not in the app-gitops-pr environment")
    if job.get("if") != "github.ref == 'refs/heads/main'":
        out.append("job is not limited to main")
    if job.get("permissions") != {"contents": "read"}:
        out.append(f"job permissions are {job.get('permissions')}, expected contents: read")
    steps = job["steps"]
    label = lambda s: s.get("name") or s.get("uses", "")
    idx = []
    for want in ORDER:
        hit = [i for i, s in enumerate(steps) if label(s).startswith(want)]
        if not hit:
            out.append(f"step {want!r} is missing")
        else:
            idx.append(hit[0])
    if idx != sorted(idx):
        out.append("steps are not in the required order (inputs, token, checkout, approval, rebuild, remove, check, open)")
    runs = [s.get("run", "") for s in steps]
    for i, r in enumerate(runs):
        if re.search(r"\$\{\{\s*(inputs|github\.event)", r):
            out.append(f"step {i} puts an input into a shell script through ${{{{ }}}}")
    allrun = "\n".join(runs)
    if re.search(r"--force|-f\b.*git push|git push[^\n]*\+", allrun):
        out.append("a push is forced")
    if re.findall(r"git push[^\n]*", allrun) != ['git push origin "HEAD:refs/heads/${branch}"']:
        out.append("the only push must be HEAD to the removal branch")
    if "release-window-removal/?*" not in allrun or 'branch="release-window-removal/${WINDOW_ID}"' not in allrun:
        out.append("the branch is not guarded to release-window-removal/")
    if re.search(r"enqueuePullRequest|gh\s+pr\s+merge|merge-gitops-pr\.sh\s+\d|--admin", allrun):
        out.append("open-pr enqueues or merges")
    if "secrets.GITHUB_TOKEN" in text:
        out.append("GITHUB_TOKEN is used")
    if '--trailer "Agent: ' not in allrun:
        out.append("the commit has no Agent: trailer")
    if ('git config user.name "mctl-gitops-pr[bot]"' not in allrun
            or 'git config user.email "353875018+mctl-gitops-pr[bot]@users.noreply.github.com"' not in allrun):
        out.append("the commit is not authored as the App bot")
    check_in = next((s for s in steps if label(s).startswith("Check the inputs")), {}).get("run", "")
    for needle in ("release-window-removal/${WINDOW_ID}", "BASE_SHA", "WINDOW_SHA256", "APPLICATIONS", "SCHEDULE", "DURATION"):
        if needle not in check_in:
            out.append(f"the input check does not cover {needle}")
    appr = next((s for s in steps if label(s).startswith("Check the approval")), {}).get("run", "")
    if "merge-base --is-ancestor" not in appr or "git diff --quiet" not in appr:
        out.append("the approval check lost its ancestry or unchanged-target test")
    reb = next((s for s in steps if label(s).startswith("Rebuild the window")), {}).get("run", "")
    if ('release-window-insert.py hash-remove "$PROJECT"' not in reb or '[ "$got" = "$WINDOW_SHA256" ]' not in reb):
        out.append("the rebuild step does not compare the REMOVAL hash")
    if "n != 1" not in reb:
        out.append("the rebuild step does not require the window exactly once")
    rem = next((s for s in steps if label(s).startswith("Remove the window")), {}).get("run", "")
    if 'release-window-insert.py remove "$target"' not in rem:
        out.append("the edit step does not run the remove command")
    if "render-sync-window.py" in allrun or "release-window-insert.py insert" in allrun:
        out.append("the removal workflow calls the add tooling")
    chk = next((s for s in steps if label(s).startswith("Check the edit")), {}).get("run", "")
    if ("validate-argocd-sync-windows.py" not in chk or "expected.remove(want)" not in chk
            or '--expect-project "$PROJECT"' not in chk):
        out.append("the post-edit check lost the validator or the before-minus-window test")
    if '"$added" = 0' not in chk or '"$deleted" -ge 1' not in chk:
        out.append("the post-edit check lost the pure-deletion test")
    wait = next((s for s in ejob.get("steps", []) if (s.get("name") or "").startswith("Wait for the approval")), {})
    if "export WINDOW_KIND=remove" not in wait.get("run", ""):
        out.append("the queue gate is not run with WINDOW_KIND=remove")
    for s in steps:
        if label(s).startswith("actions/checkout") and s.get("with", {}).get("ref") != "main":
            out.append("checkout is not pinned to main")
    return out


def mutants(text):
    def sub(old, new):
        assert old in text, f"mutant anchor missing: {old!r}"
        return text.replace(old, new, 1)
    yield "pull_request trigger added", sub("on:\n  workflow_dispatch:", "on:\n  pull_request:\n  workflow_dispatch:")
    yield "environment dropped", sub("    environment: app-gitops-pr\n", "")
    yield "main-only guard dropped", sub("    if: github.ref == 'refs/heads/main'\n", "")
    yield "job write grant", sub("    permissions:\n      contents: read\n    outputs:", "    permissions:\n      contents: write\n    outputs:")
    yield "workflow-level grant", sub("permissions: {}\n\njobs:", "permissions:\n  contents: write\n\njobs:")
    yield "separate concurrency group", sub("      group: release-window-pr\n", "      group: release-window-removal-pr\n")
    yield "enqueue-window in the group", sub("    timeout-minutes: 50\n", "    timeout-minutes: 50\n    concurrency:\n      group: release-window-pr\n")
    yield "input interpolated into a script", sub('[[ "$BASE_SHA" =~', '[[ "${{ inputs.base_sha }}" =~')
    yield "force push", sub('git push origin "HEAD:refs/heads/${branch}"', 'git push --force origin "HEAD:refs/heads/${branch}"')
    yield "push to main", sub('git push origin "HEAD:refs/heads/${branch}"', 'git push origin "HEAD:refs/heads/main"')
    yield "merge added to open-pr", sub('echo "::notice::opened ${pr_url}"', 'gh pr merge "$pr_url" --merge\n          echo "::notice::opened ${pr_url}"')
    yield "GITHUB_TOKEN used", sub("GH_TOKEN: ${{ steps.token.outputs.token }}", "GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}")
    yield "trailer dropped", sub('--trailer "Agent: none"', '')
    yield "unattributed author", sub("353875018+mctl-gitops-pr[bot]@users.noreply.github.com", "ci@mctl.ai")
    yield "ancestry check dropped", sub('git merge-base --is-ancestor "$BASE_SHA" HEAD ||', 'true ||')
    yield "unchanged-target check dropped", sub('git diff --quiet "$BASE_SHA" HEAD -- "$target"', 'true')
    yield "add hash used instead of the removal hash", sub('release-window-insert.py hash-remove "$PROJECT"', 'release-window-insert.py hash "$PROJECT"')
    yield "hash comparison dropped", sub('[ "$got" = "$WINDOW_SHA256" ] \\', 'true \\')
    yield "window-exactly-once test dropped", sub("if n != 1:", "if False:")
    yield "insert instead of remove", sub('release-window-insert.py remove "$target"', 'release-window-insert.py insert "$target"')
    yield "add tooling called", sub('python3 scripts/release-window-insert.py remove', 'python3 scripts/render-sync-window.py --help; python3 scripts/release-window-insert.py remove')
    yield "pure-deletion test dropped", sub('[ "$added" = 0 ] && [ "$deleted" -ge 1 ] \\', 'true \\')
    yield "allows added lines", sub('[ "$added" = 0 ] && [ "$deleted" -ge 1 ]', '[ "$deleted" -ge 1 ]')
    yield "before-minus-window test dropped", sub("expected.remove(want)", "pass")
    yield "target project not expected by the validator", sub('--expect-project "$PROJECT" ', '')
    yield "branch under the add prefix", sub('branch="release-window-removal/${WINDOW_ID}"', 'branch="release-window/${WINDOW_ID}"')
    yield "branch guard dropped", sub("release-window-removal/?*", "x/?*")
    yield "queue gate not told it is a removal", sub("          export WINDOW_KIND=remove\n", "")
    yield "queue gate told it is an addition", sub("export WINDOW_KIND=remove", "export WINDOW_KIND=add")
    yield "checkout off main", sub("          ref: main\n", "          ref: ${{ github.ref }}\n")
    yield "enqueue pin dropped", sub(",expectedHeadOid:$h", "")
    yield "enqueue job without the environment", sub("  enqueue-window:\n    needs: open-pr\n    if: github.ref == 'refs/heads/main' && needs.open-pr.result == 'success'\n    runs-on: ubuntu-latest\n    environment: app-gitops-pr\n", "  enqueue-window:\n    needs: open-pr\n    if: github.ref == 'refs/heads/main' && needs.open-pr.result == 'success'\n    runs-on: ubuntu-latest\n")
    yield "wait runs with the App token", sub("          GH_TOKEN: ${{ github.token }}\n          REPO: ${{ github.repository }}\n          PR: ${{ needs.open-pr.outputs.pr }}\n          EXPECT_HEAD", "          GH_TOKEN: ${{ steps.token.outputs.token }}\n          REPO: ${{ github.repository }}\n          PR: ${{ needs.open-pr.outputs.pr }}\n          EXPECT_HEAD")
    yield "enqueue without waiting for ready", sub("      - name: Enqueue the judged head with the App token\n        if: steps.ready.outputs.ready == 'true'\n", "      - name: Enqueue the judged head with the App token\n")
    yield "wait script not run", sub("bash scripts/release-window-enqueue-wait.sh", "true")
    yield "pushed head not passed to the wait", sub("          EXPECT_HEAD: ${{ needs.open-pr.outputs.head }}\n", "")
    yield "enqueue-window write grant", sub("      pull-requests: read\n      checks: read\n", "      pull-requests: write\n      checks: read\n")
    yield "open-pr outputs dropped", sub("    outputs:\n      pr: ${{ steps.open.outputs.pr }}\n      head: ${{ steps.open.outputs.head }}\n", "")
    a = text.index("      - name: Check the inputs")
    b = text.index("      - name: Generate a write token")
    c = text.index("      - uses: actions/checkout")
    yield "token minted before the input check", text[:a] + text[b:c] + text[a:b] + text[c:]


def main():
    text = WF.read_text()
    got = problems(text)
    assert got == [], f"release-window-removal-pr.yml: {got}"
    for name, m in mutants(text):
        assert problems(m), f"mutant not caught: {name}"
    print("ok")


if __name__ == "__main__":
    main()
