"""The release-bump enqueue: its guards, its wait, and the token it enqueues with.

Plain script: `python3 tests/test_release_bump_enqueue.py`.

Release-bump PRs used to be enqueued from auto-merge.yml with GITHUB_TOKEN.
Events caused by GITHUB_TOKEN start no workflow run, merge_group included, so
those queue entries sat in AWAITING_CHECKS until a person re-enqueued them
(mctl-api 4.167.0 #2780, 4.168.0 #2792). The enqueue-bump job of
release-deploy.yaml and gitops-bump.yaml now enqueues with the mctl-gitops-pr
App token, from main, after scripts/release-bump-enqueue-wait.sh has judged the
head. It is a plain job in the release workflow: as a reusable (workflow_call)
workflow the app-gitops-pr environment secret arrived empty (4.169.0, #2798).
Three layers, each with mutants that must turn a case red:
  * the wait script, run for real with a fake gh: every guard auto-merge.yml
    applied (App author, head in this repository, full file list, protected
    paths, tag-only diff, approval on the exact head, green checks) refuses;
  * the wiring of the enqueue-bump job, identical in both workflows: main-only
    environment, the App token minted after the wait and used for the one
    enqueue, pinned with expectedHeadOid;
  * repo-wide: no workflow step enqueues with GITHUB_TOKEN, and every job that
    mints the mctl-gitops-pr App token is a plain job in the app-gitops-pr
    environment of a workflow that is not a workflow_call file.
"""
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release-bump-enqueue-wait.sh"
WF_DIR = ROOT / ".github/workflows"
CALLERS = ("release-deploy.yaml", "gitops-bump.yaml")
WINDOWS = ("release-window-pr.yml", "release-window-removal-pr.yml")
REQ = "agy-formal-review,cloudflare-plan,reserved-hosts,validate"
HEAD = "a" * 40
APP = "mctl-gitops-pr[bot]"
BUMP_FILE = "platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml"
TAG_DIFF = (f"diff --git a/{BUMP_FILE} b/{BUMP_FILE}\nindex 1..2 100644\n--- a/{BUMP_FILE}\n+++ b/{BUMP_FILE}\n"
            '@@ -1,3 +1,3 @@\n ctx\n-        tag: "4.154.0"\n+        tag: "4.154.1"\n ctx\n')
OTHER_DIFF = TAG_DIFF.replace('+        tag: "4.154.1"', '+        tag: "4.154.1"\n+        privileged: true')


def run_for(name, status="completed", conclusion="success", i=[0]):
    i[0] += 1
    return {"id": i[0], "name": name, "status": status, "conclusion": conclusion}


def green():
    return [run_for(n) for n in REQ.split(",")] + [run_for("claude-review / review"), run_for("auto-merge", conclusion="skipped")]


def run_script(*, script_text=None, author=APP, head_repo="o/r", head_ref="release-bump/mctl-api-4.154.1",
               state="open", merged="false", pr_ok=True, files=(BUMP_FILE,), changed=None, files_ok=True,
               diff=TAG_DIFF, diff_ok=True, cur=HEAD, gstate="OPEN", decision="APPROVED", on_head=1, review_ok=True,
               runs=None, total=None, runs_ok=True, wait_seconds=100000):
    """Run the wait script with a fake gh. Returns (rc, outputs, log)."""
    runs = green() if runs is None else runs
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        # The script resolves auto-merge.yml and the guard scripts relative to
        # itself; give it a tree where they are the real files.
        (d / "scripts").mkdir()
        (d / ".github/workflows").mkdir(parents=True)
        (d / "scripts/release-bump-enqueue-wait.sh").write_text(script_text or SCRIPT.read_text())
        for f in ("scripts/release-bump-diff-guard.py", "scripts/release-bump-checks-ready.py", ".github/workflows/auto-merge.yml"):
            (d / f).symlink_to(ROOT / f)
        # The PR as the REST API returns it; the fake gh applies the script's
        # own --jq, so the field separator is exercised, not assumed. An empty
        # head_repo is a deleted head repository (head.repo null).
        (d / "info").write_text(json.dumps({
            "head": {"sha": HEAD, "ref": head_ref, "repo": {"full_name": head_repo} if head_repo else None},
            "changed_files": len(files) if changed is None else changed, "user": {"login": author},
            "state": state, "merged": merged == "true", "node_id": "PRID"}))
        (d / "listing").write_text("".join(f"{f}\t\n" for f in files))
        (d / "diff").write_text(diff)
        (d / "review").write_text(f"{cur} {gstate} {decision} {on_head}\n")
        (d / "runs").write_text("\n".join(json.dumps(r) for r in runs))
        (d / "total").write_text(str(len(runs) if total is None else total))
        bin_ = d / "bin"
        bin_.mkdir()
        gh = bin_ / "gh"
        pr_cmd = f'jq -r "$jqf" "{d}/info"' if pr_ok else "exit 1"
        gh.write_text(
            "#!/bin/bash\n"
            # The value after --jq, for the calls whose filter is under test.
            'jqf=; prev=; for a in "$@"; do [ "$prev" = --jq ] && jqf=$a; prev=$a; done\n'
            'case "$*" in\n'
            f'  *enqueuePullRequest*) echo "$*" >> "{d}/enqueue"; exit 0 ;;\n'
            f'  *graphql*) {"cat " + str(d / "review") if review_ok else "exit 1"} ;;\n'
            # An unreadable diff still prints a valid tag move: a failed read
            # must refuse on its own, not because the text was empty.
            f'  *compare*) cat "{d}/diff"; {"exit 0" if diff_ok else "exit 1"} ;;\n'
            f'  *"/files?"*) {"cat " + str(d / "listing") if files_ok else "exit 1"} ;;\n'
            f'  *"per_page=1 "*) cat "{d}/total" ;;\n'
            f'  *check-runs*) {"cat " + str(d / "runs") if runs_ok else "exit 1"} ;;\n'
            f'  *"pulls/7 "*) {pr_cmd} ;;\n'
            '  *) echo "unexpected gh call: $*" >&2; exit 1 ;;\n'
            "esac\n")
        # A wait must not stall the test: the third sleep kills the script.
        sleep = bin_ / "sleep"
        sleep.write_text(f'#!/bin/sh\necho x >> "{d}/sleeps"\n[ "$(wc -l < "{d}/sleeps")" -ge 3 ] && kill -9 $PPID\nexit 0\n')
        for f in (gh, sleep):
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        out = d / "out"
        out.write_text("")
        env = {"PATH": f"{bin_}:{os.environ['PATH']}", "GH_TOKEN": "x", "REPO": "o/r", "PR": "7",
               "GITHUB_OUTPUT": str(out), "RUNNER_TEMP": str(d), "WAIT_SECONDS": str(wait_seconds)}
        r = subprocess.run(["bash", str(d / "scripts/release-bump-enqueue-wait.sh")], env=env,
                           capture_output=True, text=True, timeout=60, cwd=d)
        assert not (d / "enqueue").exists(), "the wait script must never enqueue itself"
        return r.returncode, out.read_text(), r.stdout + r.stderr


def script_cases(script_text=None):
    """(name, thunk returning got, want); thunks keep a mutant run short."""
    def ready(**kw):
        rc, out, _ = run_script(script_text=script_text, **kw)
        return rc == 0 and "ready=true" in out and f"head_sha={HEAD}" in out and "pr_id=PRID" in out

    def refused(**kw):  # an explicit refusal, not a wait cut short by the fake sleep
        rc, out, log = run_script(script_text=script_text, **kw)
        return rc not in (0, -9) and "::error::" in log and "ready=true" not in out

    def refused_for(msg, **kw):
        rc, out, log = run_script(script_text=script_text, **kw)
        return rc not in (0, -9) and "::error::" in log and msg in log and "ready=true" not in out

    def idle(**kw):  # neither ready nor refused: still waiting when the sleeps ran out
        rc, out, log = run_script(script_text=script_text, **kw)
        return "ready=true" not in out and "waiting" in log

    def hints(**kw):
        _, _, log = run_script(script_text=script_text, **kw)
        return log.count("::warning::no agy-formal-review")

    def hinted(**kw):
        _, _, log = run_script(script_text=script_text, **kw)
        return ("gh workflow run agy-formal-dispatch.yml --repo mctlhq/.github --ref main "
                f"-f repository=o/r -f pr_number=7 -f head_sha={HEAD}") in log

    def done(**kw):
        rc, out, _ = run_script(script_text=script_text, **kw)
        return rc == 0 and "ready=false" in out and "ready=true" not in out

    pending = green() + [run_for("trivy", "in_progress", None)]
    return [
        ("approved, green, App author, tag-only diff -> ready", lambda: ready(), True),
        ("a human author is refused", lambda: refused(author="mashkovd"), True),
        ("another bot is refused", lambda: refused(author="mctl-agents[bot]"), True),
        ("a head in a fork is refused", lambda: refused(head_repo="evil/r"), True),
        ("a head with no repository is refused", lambda: refused(head_repo=""), True),
        # An empty field must not shift the later ones: the refusal names the
        # missing repository, not a branch that landed in head_repo.
        ("a head with no repository is refused for that reason",
         lambda: refused_for("the head of #7 is in '', not o/r", head_repo=""), True),
        ("the deadline refusal names the recovery",
         lambda: refused_for("re-run only this failed enqueue-bump job", runs=pending, wait_seconds=0), True),
        ("a branch outside release-bump/ is refused", lambda: refused(head_ref="claude/x"), True),
        ("an unreadable PR is refused", lambda: refused(pr_ok=False), True),
        ("an unreadable file list is refused", lambda: refused(files_ok=False), True),
        ("a short file list is refused", lambda: refused(changed=2), True),
        ("a protected path is refused", lambda: refused(files=("platform-gitops/argo-workflows/cluster-templates/wft-deploy-service.yaml",)), True),
        ("a diff beyond the tag is refused", lambda: refused(diff=OTHER_DIFF), True),
        ("an unreadable diff is refused", lambda: refused(diff_ok=False), True),
        ("an empty diff is refused", lambda: refused(diff=""), True),
        ("a merged PR is a no-op", lambda: done(merged="true", state="closed"), True),
        ("a closed PR is a no-op", lambda: done(state="closed"), True),
        ("a moved head is refused", lambda: refused(cur="b" * 40), True),
        ("an unreadable review state is refused", lambda: refused(review_ok=False), True),
        ("changes requested is refused", lambda: refused(decision="CHANGES_REQUESTED"), True),
        ("an unknown review decision is refused", lambda: refused(decision="SOMETHING"), True),
        ("no review yet waits", lambda: idle(decision="REVIEW_REQUIRED", on_head=0), True),
        ("APPROVED with no approval on this head waits", lambda: idle(on_head=0), True),
        ("a pending check waits", lambda: idle(runs=pending), True),
        ("a pending auto-merge run is not ignored", lambda: idle(runs=green() + [run_for("auto-merge", "in_progress", None)]), True),
        ("a missing required check waits", lambda: idle(runs=[r for r in green() if r["name"] != "validate"]), True),
        ("a failed check is refused", lambda: refused(runs=green() + [run_for("trivy", conclusion="failure")]), True),
        ("a missing formal review waits",
         lambda: idle(runs=[r for r in green() if r["name"] != "agy-formal-review"]), True),
        ("a missing formal review names the dispatch for this head", lambda: hinted(
            runs=[r for r in green() if r["name"] != "agy-formal-review"]), True),
        ("the dispatch hint is printed once", lambda: hints(
            runs=[r for r in green() if r["name"] != "agy-formal-review"]), 1),
        ("a reported formal review prints no dispatch hint", lambda: hints(runs=pending), 0),
        ("a running formal review waits", lambda: idle(
            runs=[r for r in green() if r["name"] != "agy-formal-review"]
            + [run_for("agy-formal-review", "in_progress", None)]), True),
        ("a failed formal review is refused", lambda: refused(
            runs=[r for r in green() if r["name"] != "agy-formal-review"]
            + [run_for("agy-formal-review", conclusion="failure")]), True),
        ("an unreadable check list is refused", lambda: refused(runs_ok=False), True),
        ("a truncated check list is refused", lambda: refused(total=len(green()) + 3), True),
        ("the deadline is a refusal", lambda: refused(runs=pending, wait_seconds=0), True),
        ("no approval by the deadline is a refusal", lambda: refused(on_head=0, wait_seconds=0), True),
    ]


SCRIPT_MUTANTS = {
    "formal review not required": ("REQUIRED_CHECKS=agy-formal-review,", "REQUIRED_CHECKS="),
    "no dispatch hint": ('echo "::warning::no agy-formal-review', 'true "'),
    "dispatch hint repeated": ("          hinted=1\n", ""),
    "author check dropped": ('[ "$author" = "$APP_LOGIN" ] ||', 'true ||'),
    "fork check dropped": ('[ "$head_repo" = "$REPO" ] ||', 'true ||'),
    "branch check dropped": ("case \"$head_ref\" in release-bump/?*) ;;", "case \"$head_ref\" in *) ;;"),
    "file count ignored": ('[ "$listed" = "$expected" ] ||', 'true ||'),
    "protected paths ignored": ('[ -z "$protected" ] ||', 'true ||'),
    "diff guard skipped": ('python3 "$root/scripts/release-bump-diff-guard.py" < "$RUNNER_TEMP/bump.diff" \\\n  ||', 'true \\\n  ||'),
    "unreadable diff ignored": ('"repos/${REPO}/compare/main...${head_sha}" > "$RUNNER_TEMP/bump.diff" \\\n  ||',
                                '"repos/${REPO}/compare/main...${head_sha}" > "$RUNNER_TEMP/bump.diff" || true \\\n  ||'),
    "moved head accepted": ('[ "$cur" = "$head_sha" ] ||', 'true ||'),
    "approval on another head accepted": ('APPROVED) [[ "$on_head" =~ ^[1-9][0-9]*$ ]] && approved=1 ;;', 'APPROVED) approved=1 ;;'),
    "review not required": ('REVIEW_REQUIRED|null) ;;', 'REVIEW_REQUIRED|null) approved=1 ;;'),
    "changes requested waits": ('CHANGES_REQUESTED) die', 'CHANGES_REQUESTED) : die'),
    "not-ready verdict accepted": ("    case \"$rc\" in\n      0)", "    case \"$rc\" in\n      0|10|11|12)"),
    "a failed check waits": ('*) die "#${PR} is not mergeable: ${verdict}" ;;', '*) echo waiting ;;'),
    "own check excludes auto-merge": ('--own-check ""', '--own-check auto-merge'),
    "deadline ignored": ('if [ "$SECONDS" -ge "$deadline" ]; then', 'if false; then'),
    "tab separator again": ('join("\\u001f")\'); then', '@tsv\'); then'),
    "tab IFS again": ("IFS=$'\\x1f' read", "IFS=$'\\t' read"),
    "deadline names no recovery": ("re-run only this failed enqueue-bump job", "give up"),
    "closed PR treated as ready": ('if [ "$state" = closed ]; then not_ready "#${PR} is closed."; fi',
                                   'if [ "$state" = closed ]; then state=open; fi'),
}


def step(job, sid=None, uses=None, name=None):
    for s in job["steps"]:
        if (sid and s.get("id") == sid) or (uses and str(s.get("uses", "")).startswith(uses)) or (name and name in str(s.get("name", ""))):
            return s
    return None


def app_token_step_ids(job):
    return {s.get("id") for s in job.get("steps", []) if str(s.get("uses", "")).startswith("actions/create-github-app-token@")}


def enqueue_steps(docs):
    """Every step in every workflow whose run mentions enqueuePullRequest: (file, job, step)."""
    out = []
    for fn, doc in docs.items():
        for jn, job in (doc.get("jobs") or {}).items():
            for s in job.get("steps", []) or []:
                if "enqueuePullRequest" in str(s.get("run", "")):
                    out.append((fn, job, s))
    return out


def on_triggers(doc):
    on = doc.get(True, doc.get("on"))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    return set(on or {})


def wiring_cases(texts):
    """texts: {workflow file name: text}. (name, ok)."""
    docs = {fn: yaml.safe_load(t) for fn, t in texts.items()}
    out = []
    # Repo-wide: an enqueue never runs with GITHUB_TOKEN, only with an App token.
    eqs = enqueue_steps(docs)
    # The release-window PRs are the other enqueues: the enqueue-window job in
    # release-window-pr.yml (an addition) and in release-window-removal-pr.yml (a
    # removal), judged by scripts/release-window-enqueue-wait.sh and pinned by
    # tests/test_release_window_pr.py, tests/test_release_window_removal.py and
    # tests/test_release_window_enqueue.py.
    out.append(("exactly the two enqueue-bump jobs and the two enqueue-window jobs enqueue",
                sorted(fn for fn, _, _ in eqs) == sorted(CALLERS + WINDOWS)
                and all(docs[fn]["jobs"].get("enqueue-window" if fn in WINDOWS else "enqueue-bump") is job
                        for fn, job, _ in eqs)))
    for fn, job, s in eqs:
        env = s.get("env") or {}
        tok = str(env.get("GH_TOKEN", ""))
        m = re.fullmatch(r"\$\{\{ steps\.([A-Za-z0-9_-]+)\.outputs\.token \}\}", tok)
        out.append((f"{fn}: the enqueue's GH_TOKEN is an App installation token",
                    m is not None and m.group(1) in app_token_step_ids(job)))
        out.append((f"{fn}: the enqueue step never names GITHUB_TOKEN or github.token",
                    not re.search(r"GITHUB_TOKEN|github\.token", str(env) + str(s.get("run", "")))))
    # Repo-wide: the App key is only read by a plain job in app-gitops-pr, in a
    # workflow that is not itself a workflow_call file. In a reusable workflow
    # the environment secret arrived empty (#2798).
    minters = [(fn, jn, job) for fn, doc in docs.items() for jn, job in (doc.get("jobs") or {}).items()
               if "GITOPS_PR_APP_PRIVATE_KEY" in str(job)]
    out.append(("both enqueue-bump jobs are among the jobs that read the App key",
                all((fn, "enqueue-bump") in {(f, j) for f, j, _ in minters} for fn in CALLERS)))
    for fn, jn, job in minters:
        out.append((f"{fn}/{jn}: the job reading the App key is a plain job in app-gitops-pr, not in a workflow_call file",
                    "uses" not in job and job.get("environment") == "app-gitops-pr"
                    and "workflow_call" not in on_triggers(docs[fn]) and "secrets" not in job))
    out.append(("no workflow passes secrets: inherit", not any(
        isinstance(j, dict) and j.get("secrets") == "inherit" for d in docs.values() for j in (d.get("jobs") or {}).values())))
    # The job itself, identical in both workflows.
    jobs = [docs[fn]["jobs"].get("enqueue-bump") for fn in CALLERS]
    out.append(("enqueue-bump is the same job in both release workflows", jobs[0] is not None and jobs[0] == jobs[1]))
    for fn in CALLERS:
        doc = docs[fn]
        job = doc["jobs"].get("enqueue-bump") or {}
        out.append((f"{fn}: enqueue-bump follows publish-pr in the main-only app-gitops-pr environment",
                    job.get("needs") == "publish-pr" and job.get("if") == "needs.publish-pr.result == 'success'"
                    and job.get("environment") == "app-gitops-pr" and "uses" not in job
                    and on_triggers(doc) == {"workflow_dispatch"}))
        out.append((f"{fn}: the job's GITHUB_TOKEN is read-only",
                    job.get("permissions") == {"contents": "read", "pull-requests": "read", "checks": "read"}))
        if "steps" not in job:
            out.append((f"{fn}: enqueue-bump has steps", False))
            continue
        co = step(job, uses="actions/checkout@") or {}
        out.append((f"{fn}: the scripts come from main, without persisted credentials",
                    (co.get("with") or {}).get("ref") == "main" and (co.get("with") or {}).get("persist-credentials") is False))
        wait = step(job, sid="ready") or {}
        out.append((f"{fn}: the wait runs the script with the read-only GITHUB_TOKEN and no secret",
                    wait.get("run", "").strip() == "bash scripts/release-bump-enqueue-wait.sh"
                    and (wait.get("env") or {}).get("GH_TOKEN") == "${{ github.token }}"
                    and "secrets." not in str(wait) and (wait.get("env") or {}).get("PR") == "${{ needs.publish-pr.outputs.pr }}"))
        tok = step(job, sid="token") or {}
        w = tok.get("with") or {}
        out.append((f"{fn}: the App token is minted only after a ready verdict",
                    bool(tok and wait) and tok.get("if") == "steps.ready.outputs.ready == 'true'"
                    and job["steps"].index(tok) > job["steps"].index(wait)))
        out.append((f"{fn}: the App token is scoped to mctl-gitops, contents and pull-requests write",
                    str(tok.get("uses", "")).startswith("actions/create-github-app-token@")
                    and w.get("owner") == "mctlhq" and w.get("repositories") == "mctl-gitops"
                    and {k: v for k, v in w.items() if k.startswith("permission-")} == {"permission-contents": "write", "permission-pull-requests": "write"}
                    and w.get("private-key") == "${{ secrets.GITOPS_PR_APP_PRIVATE_KEY }}"
                    and w.get("client-id") == "${{ vars.GITOPS_PR_APP_CLIENT_ID }}"))
        enq = step(job, name="Enqueue") or {}
        env = enq.get("env") or {}
        run = enq.get("run", "")
        out.append((f"{fn}: the enqueue is gated on the ready verdict and pinned to the judged head",
                    enq.get("if") == "steps.ready.outputs.ready == 'true'"
                    and "expectedHeadOid:$h" in run and '-f h="$HEAD_SHA"' in run and '-f id="$PR_ID"' in run
                    and env.get("HEAD_SHA") == "${{ steps.ready.outputs.head_sha }}"
                    and env.get("PR_ID") == "${{ steps.ready.outputs.pr_id }}"))
        out.append((f"{fn}: a refused enqueue fails the job", re.search(r'was refused: \$\{out\}"\n\s*exit 1', run) is not None))
        out.append((f"{fn}: no other step of the job holds a secret",
                    all("secrets." not in str(s) for s in job.get("steps", []) if s is not tok)))
        out.append((f"{fn}: enqueue-bump is in no concurrency group", "concurrency" not in job))
    out.append(("auto-merge.yml enqueues nothing", "enqueuePullRequest" not in texts["auto-merge.yml"]))
    return out


RD, GB = CALLERS
REUSABLE = """name: x
on:
  workflow_call:
jobs:
  enqueue:
    runs-on: ubuntu-latest
    environment: app-gitops-pr
    steps:
      - id: token
        uses: actions/create-github-app-token@64ab729a6294000f5aa4a4bc0b73d1f32bc45510 # v3.3.0
        with:
          private-key: ${{ secrets.GITOPS_PR_APP_PRIVATE_KEY }}
"""
WIRING_MUTANTS = [
    # (name, file, old, new); old None adds `new` as a whole new file.
    ("GITHUB_TOKEN back on the enqueue", RD,
     "          GH_TOKEN: ${{ steps.token.outputs.token }}\n          PR: ${{ needs.publish-pr.outputs.pr }}", "          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n          PR: ${{ needs.publish-pr.outputs.pr }}"),
    ("github.token on the enqueue", GB,
     "          GH_TOKEN: ${{ steps.token.outputs.token }}\n          PR: ${{ needs.publish-pr.outputs.pr }}", "          GH_TOKEN: ${{ github.token }}\n          PR: ${{ needs.publish-pr.outputs.pr }}"),
    ("the enqueue reads a non-App step output", RD,
     "          GH_TOKEN: ${{ steps.token.outputs.token }}\n          PR: ${{ needs.publish-pr.outputs.pr }}", "          GH_TOKEN: ${{ steps.ready.outputs.token }}\n          PR: ${{ needs.publish-pr.outputs.pr }}"),
    ("enqueue back in auto-merge.yml with GITHUB_TOKEN", "auto-merge.yml",
     "      - name: Report that the merge is left to the queue\n",
     "      - name: Enqueue\n        run: gh api graphql -f query='mutation{enqueuePullRequest(input:{pullRequestId:\"x\"}){clientMutationId}}'\n"
     "        env:\n          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n      - name: Report that the merge is left to the queue\n"),
    ("App key minted in a workflow_call file", "release-bump-enqueue.yml", None, REUSABLE),
    ("release workflow made callable", RD, "on:\n  workflow_dispatch:\n", "on:\n  workflow_call:\n  workflow_dispatch:\n"),
    ("enqueue-bump turned back into a reusable-workflow call", GB,
     "    runs-on: ubuntu-latest\n    environment: app-gitops-pr\n    # The wait gives up",
     "    uses: ./.github/workflows/release-bump-enqueue.yml\n    environment: app-gitops-pr\n    # The wait gives up"),
    ("secrets: inherit", RD, "    timeout-minutes: 50\n    permissions:\n      contents: read\n      pull-requests: read\n      checks: read\n",
     "    timeout-minutes: 50\n    secrets: inherit\n    permissions:\n      contents: read\n      pull-requests: read\n      checks: read\n"),
    ("App token minted before the wait verdict", RD,
     "        id: token\n        if: steps.ready.outputs.ready == 'true'\n", "        id: token\n"),
    ("enqueue not pinned", GB, '-f h="$HEAD_SHA"', '-f h=""'),
    ("enqueue not gated", RD,
     "      - name: Enqueue the judged head with the App token\n        if: steps.ready.outputs.ready == 'true'\n",
     "      - name: Enqueue the judged head with the App token\n"),
    ("wait step gets the App key", GB,
     "        id: ready\n        env:\n          GH_TOKEN: ${{ github.token }}\n",
     "        id: ready\n        env:\n          GH_TOKEN: ${{ github.token }}\n          KEY: ${{ secrets.GITOPS_PR_APP_PRIVATE_KEY }}\n"),
    ("environment dropped", RD, "    if: needs.publish-pr.result == 'success'\n    runs-on: ubuntu-latest\n    environment: app-gitops-pr\n",
     "    if: needs.publish-pr.result == 'success'\n    runs-on: ubuntu-latest\n"),
    ("job token gets write", GB,
     "    timeout-minutes: 50\n    permissions:\n      contents: read\n      pull-requests: read\n",
     "    timeout-minutes: 50\n    permissions:\n      contents: write\n      pull-requests: write\n"),
    ("scripts from the caller's ref", RD, "          ref: main\n          persist-credentials: false\n\n      - name: Wait for the approval",
     "          ref: ${{ github.sha }}\n          persist-credentials: false\n\n      - name: Wait for the approval"),
    ("refused enqueue ignored", GB, 'was refused: ${out}"\n            exit 1', 'was refused: ${out}"\n            exit 0'),
    ("the two jobs drift apart", RD, "    timeout-minutes: 50\n", "    timeout-minutes: 55\n"),
]


def main():
    cases = script_cases()
    bad = [n for n, f, w in cases if f() != w]
    assert not bad, f"wrong verdicts: {bad}"
    print(f"ok   {len(cases)} script cases")
    src = SCRIPT.read_text()
    for name, (old, new) in SCRIPT_MUTANTS.items():
        assert src.count(old) == 1, f"mutant anchor {name}: {src.count(old)}"
        red = next((n for n, f, w in script_cases(script_text=src.replace(old, new)) if f() != w), None)
        assert red, f"script mutant survives: {name}"
        print(f"mutant killed: {name} (by: {red})")

    texts = {p.name: p.read_text() for p in sorted(WF_DIR.glob("*.y*ml"))}
    res = wiring_cases(texts)
    failed = [n for n, ok in res if not ok]
    assert not failed, f"wiring: {failed}"
    print(f"ok   {len(res)} wiring checks")
    for name, fn, old, new in WIRING_MUTANTS:
        if old is None:
            assert fn not in texts, f"mutant {name}: {fn} already exists"
            mutated = new
        else:
            assert texts[fn].count(old) == 1, f"mutant anchor {name}: {texts[fn].count(old)}"
            mutated = texts[fn].replace(old, new)
        try:
            killed = any(not ok for _, ok in wiring_cases({**texts, fn: mutated}))
        except Exception:
            killed = True
        assert killed, f"wiring mutant survives: {name}"
        print(f"mutant killed: {name}")

    # The script's required checks are the ruleset's, and each is a real job id
    # (tests/test_required_check_job_ids.py pins check name == job id).
    m = re.search(r"^REQUIRED_CHECKS=([a-z,-]+)$", src, re.M)
    assert m and m.group(1) == REQ, "REQUIRED_CHECKS drifted from the ruleset list"
    window = (ROOT / "scripts/release-window-enqueue-wait.sh").read_text()
    assert re.findall(r"^REQUIRED_CHECKS=([a-z,-]+)$", window, re.M) == [REQ], "the two wait scripts disagree"
    for wf, jobs in (("validate-manifests.yml", ["validate", "reserved-hosts"]), ("cloudflare-plan.yml", ["cloudflare-plan"])):
        have = yaml.safe_load(texts[wf])["jobs"]
        for j in jobs:
            assert j in have and have[j].get("name", j) == j, f"required check {j} is not a job id of {wf}"
    # CI runs this test.
    assert "python3 tests/test_release_bump_enqueue.py" in texts["validate-manifests.yml"]
    print("ok")


if __name__ == "__main__":
    sys.exit(main())
