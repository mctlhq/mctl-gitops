"""release-window-pr.yml: the wiring that keeps a window request safe.

Plain script: `python3 tests/test_release_window_pr.py`.

The workflow opens a release-window/<id> pull request with the mctl-gitops-pr
App token (proposal issue-2828, 8.2). What must hold, each with a mutant that
has to turn it red (a check that cannot fail proves nothing):
  * only workflow_dispatch starts it, on main, in the main-only app-gitops-pr
    environment, with no workflow-level or job-level write grant;
  * the inputs are shape-checked BEFORE the App token is minted, and no input
    reaches a shell through ${{ }};
  * the approval is re-checked (base_sha ancestry, target unchanged) and the
    window hash compared before anything is edited;
  * the only push targets a release-window/ ref, never forced, never main;
  * nothing here enqueues or merges, and nothing uses GITHUB_TOKEN to write;
  * the commit is the App bot's and carries an Agent: trailer.
The insert script has its own selftest, run here as well.
"""
import pathlib
import re
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github/workflows/release-window-pr.yml"
INSERT = ROOT / "scripts/release-window-insert.py"

ORDER = ["Check the inputs", "Generate a write token", "actions/checkout", "Check the approval is still current",
         "Render the window against the live inventory", "Add the window to the project template",
         "Check the edit changed nothing else", "Open the release-window pull request"]


def problems(text):
    out = []
    doc = yaml.safe_load(text)
    on = doc.get(True, doc.get("on"))  # PyYAML reads the key `on` as True
    if set(on) != {"workflow_dispatch"}:
        out.append(f"triggers are {sorted(map(str, on))}, expected only workflow_dispatch")
    if doc.get("permissions") != {}:
        out.append("workflow-level permissions are not {}")
    job = doc["jobs"]["open-pr"]
    if list(doc["jobs"]) != ["open-pr"]:
        out.append("the workflow has jobs besides open-pr")
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
        out.append("steps are not in the required order (inputs, token, checkout, approval, render, add, check, open)")
    runs = [s.get("run", "") for s in steps]
    for i, r in enumerate(runs):
        if re.search(r"\$\{\{\s*(inputs|github\.event)", r):
            out.append(f"step {i} puts an input into a shell script through ${{{{ }}}}")
    allrun = "\n".join(runs)
    if re.search(r"--force|-f\b.*git push|git push[^\n]*\+", allrun):
        out.append("a push is forced")
    pushes = re.findall(r"git push[^\n]*", allrun)
    if pushes != ['git push origin "HEAD:refs/heads/${branch}"']:
        out.append(f"pushes are {pushes}")
    if "release-window/?*" not in allrun:
        out.append("no guard that the branch is under release-window/")
    if re.search(r"enqueuePullRequest|gh\s+pr\s+merge|merge-gitops-pr\.sh\s+\d|--admin", allrun):
        out.append("the workflow enqueues or merges")
    if "secrets.GITHUB_TOKEN" in text:
        out.append("GITHUB_TOKEN is used")
    if '--trailer "Agent: ' not in allrun:
        out.append("the commit has no Agent: trailer")
    if ('git config user.name "mctl-gitops-pr[bot]"' not in allrun
            or 'git config user.email "353875018+mctl-gitops-pr[bot]@users.noreply.github.com"' not in allrun):
        out.append("the commit is not authored as the App bot")
    check_in = next((s for s in steps if label(s).startswith("Check the inputs")), {}).get("run", "")
    for needle in ("release-window/${WINDOW_ID}", "BASE_SHA", "WINDOW_SHA256", "APPLICATIONS", "SCHEDULE", "DURATION"):
        if needle not in check_in:
            out.append(f"the input check does not cover {needle}")
    appr = next((s for s in steps if label(s).startswith("Check the approval")), {}).get("run", "")
    if "merge-base --is-ancestor" not in appr or "git diff --quiet" not in appr:
        out.append("the approval check lost its ancestry or unchanged-target test")
    ren = next((s for s in steps if label(s).startswith("Render the window")), {}).get("run", "")
    if "render-sync-window.py" not in ren or "WINDOW_SHA256" not in ren or 'release-window-insert.py hash' not in ren:
        out.append("the render step lost the tool or the hash comparison")
    chk = next((s for s in steps if label(s).startswith("Check the edit")), {}).get("run", "")
    if "validate-argocd-sync-windows.py" not in chk or "before + [want]" not in chk:
        out.append("the post-edit check lost the validator or the exact-one-more-window test")
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
    yield "job write grant", sub("    permissions:\n      contents: read\n    steps:", "    permissions:\n      contents: write\n    steps:")
    yield "workflow-level grant", sub("permissions: {}\n\nconcurrency", "permissions:\n  contents: write\n\nconcurrency")
    yield "input interpolated into a script", sub('[[ "$BASE_SHA" =~', '[[ "${{ inputs.base_sha }}" =~')
    yield "force push", sub('git push origin "HEAD:refs/heads/${branch}"', 'git push --force origin "HEAD:refs/heads/${branch}"')
    yield "push to main", sub('git push origin "HEAD:refs/heads/${branch}"', 'git push origin "HEAD:refs/heads/main"')
    yield "enqueue added", sub('echo "::notice::opened ${pr_url}"', 'gh pr merge "$pr_url" --merge\n          echo "::notice::opened ${pr_url}"')
    yield "GITHUB_TOKEN used", sub("GH_TOKEN: ${{ steps.token.outputs.token }}", "GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}")
    yield "trailer dropped", sub('--trailer "Agent: none"', '')
    yield "unattributed author", sub("353875018+mctl-gitops-pr[bot]@users.noreply.github.com", "ci@mctl.ai")
    yield "ancestry check dropped", sub('git merge-base --is-ancestor "$BASE_SHA" HEAD ||', 'true ||')
    yield "unchanged-target check dropped", sub('git diff --quiet "$BASE_SHA" HEAD -- "$target"', 'true')
    yield "hash comparison dropped", sub('python3 scripts/release-window-insert.py hash < "$out/window.json"', 'echo "$WINDOW_SHA256"')
    yield "exact-one-more test dropped", sub("after != before + [want]", "False")
    yield "branch guard dropped", sub("release-window/?*", "x/?*")
    yield "checkout off main", sub("          ref: main\n", "          ref: ${{ github.ref }}\n")
    # Order: minting the token before the inputs are checked.
    a = text.index("      - name: Check the inputs")
    b = text.index("      - name: Generate a write token")
    c = text.index("      - uses: actions/checkout")
    yield "token minted before the input check", text[:a] + text[b:c] + text[a:b] + text[c:]


def main():
    text = WF.read_text()
    got = problems(text)
    assert got == [], f"release-window-pr.yml: {got}"
    for name, m in mutants(text):
        assert problems(m), f"mutant not caught: {name}"
    r = subprocess.run([sys.executable, str(INSERT), "--selftest"], capture_output=True, text=True)
    assert r.returncode == 0, f"release-window-insert.py selftest failed:\n{r.stdout}{r.stderr}"
    # A shape the insert script does not recognise is exit 2 and leaves the file alone.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "p.yaml"
        f.write_text("spec:\n  syncWindows: []\n")
        r = subprocess.run([sys.executable, str(INSERT), "insert", str(f)], input='{"kind":"deny"}', capture_output=True, text=True)
        assert r.returncode == 2 and f.read_text() == "spec:\n  syncWindows: []\n", (r.returncode, r.stderr)
    print("ok")


if __name__ == "__main__":
    main()
