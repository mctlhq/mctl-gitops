"""scripts/release-window-enqueue-wait.sh: what may enter the merge queue.

Plain script: `python3 tests/test_release_window_enqueue.py`.

The MFA approval of a release window is the only human review, so this script
is the whole machine-side gate (docs/plans/sync-window-write-path.md, section
5, item 6). It is run for real with a fake gh. Every guard has a case that must
refuse, and every guard has a mutant (the line removed) that must turn a case
red: a check that cannot fail proves nothing.
"""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release-window-enqueue-wait.sh"
REQ = "agy-formal-review,cloudflare-plan,reserved-hosts,validate"
HEAD = "a" * 40
APP = "mctl-gitops-pr[bot]"
TARGET = "platform-gitops/bootstrap/templates/projects/project-apps.yaml"


def run_for(name, status="completed", conclusion="success", i=[0]):
    i[0] += 1
    return {"id": i[0], "name": name, "status": status, "conclusion": conclusion}


def green():
    return [run_for(n) for n in REQ.split(",")] + [run_for("claude-review / review")]


def run_script(*, script_text=None, kind=None, additions=1, deletions=0, author=APP, head_repo="o/r", head_ref=None,
               state="open",
               merged="false", pr_ok=True, files=(TARGET,), changed=None, prev="", files_ok=True, cur=HEAD,
               pr_head=HEAD, expect=HEAD, target=TARGET, gstate="OPEN", decision="APPROVED", on_head=1,
               review_ok=True, runs=None, total=None, runs_ok=True, wait_seconds=100000, stage=None):
    """Run the wait script with a fake gh. Returns (rc, outputs, log)."""
    runs = green() if runs is None else runs
    if head_ref is None:
        head_ref = "release-window-removal/w-1" if kind == "remove" else "release-window/w-1"
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "scripts").mkdir()
        (d / "scripts/release-window-enqueue-wait.sh").write_text(script_text or SCRIPT.read_text())
        (d / "scripts/release-bump-checks-ready.py").symlink_to(ROOT / "scripts/release-bump-checks-ready.py")
        (d / "info").write_text(json.dumps({
            "head": {"sha": pr_head, "ref": head_ref, "repo": {"full_name": head_repo} if head_repo else None},
            "changed_files": len(files) if changed is None else changed, "user": {"login": author},
            "state": state, "merged": merged == "true", "node_id": "PRID",
            "additions": additions, "deletions": deletions}))
        (d / "listing").write_text("".join(f"{f}\t{prev}\n" for f in files))
        (d / "review").write_text(f"{cur} {gstate} {decision} {on_head}\n")
        (d / "runs").write_text("\n".join(json.dumps(r) for r in runs))
        (d / "total").write_text(str(len(runs) if total is None else total))
        bin_ = d / "bin"
        bin_.mkdir()
        gh = bin_ / "gh"
        pr_cmd = f'jq -r "$jqf" "{d}/info"' if pr_ok else "exit 1"
        gh.write_text(
            "#!/bin/bash\n"
            'jqf=; prev=; for a in "$@"; do [ "$prev" = --jq ] && jqf=$a; prev=$a; done\n'
            'case "$*" in\n'
            f'  *enqueuePullRequest*) echo "$*" >> "{d}/enqueue"; exit 0 ;;\n'
            f'  *graphql*) {"cat " + str(d / "review") if review_ok else "exit 1"} ;;\n'
            f'  *"/files?"*) {"cat " + str(d / "listing") if files_ok else "exit 1"} ;;\n'
            f'  *"per_page=1 "*) cat "{d}/total" ;;\n'
            f'  *check-runs*) {"cat " + str(d / "runs") if runs_ok else "exit 1"} ;;\n'
            f'  *"pulls/7 "*) {pr_cmd} ;;\n'
            '  *) echo "unexpected gh call: $*" >&2; exit 1 ;;\n'
            "esac\n")
        sleep = bin_ / "sleep"
        sleep.write_text(f'#!/bin/sh\necho x >> "{d}/sleeps"\n[ "$(wc -l < "{d}/sleeps")" -ge 3 ] && kill -9 $PPID\nexit 0\n')
        for f in (gh, sleep):
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        out = d / "out"
        out.write_text("")
        env = {"PATH": f"{bin_}:{os.environ['PATH']}", "GH_TOKEN": "x", "REPO": "o/r", "PR": "7", "EXPECT_HEAD": expect,
               "TARGET": target, "GITHUB_OUTPUT": str(out), "RUNNER_TEMP": str(d), "WAIT_SECONDS": str(wait_seconds)}
        if kind is not None:
            env["WINDOW_KIND"] = kind
        if stage is not None:
            env["STAGE"] = stage
        r = subprocess.run(["bash", str(d / "scripts/release-window-enqueue-wait.sh")], env=env,
                           capture_output=True, text=True, timeout=60, cwd=d)
        assert not (d / "enqueue").exists(), "the wait script must never enqueue itself"
        return r.returncode, out.read_text(), r.stdout + r.stderr


def cases(script_text=None):
    def ready(**kw):
        rc, out, _ = run_script(script_text=script_text, **kw)
        return rc == 0 and "ready=true" in out and f"head_sha={HEAD}" in out and "pr_id=PRID" in out

    def refused(**kw):
        rc, out, log = run_script(script_text=script_text, **kw)
        return rc not in (0, -9) and "::error::" in log and "ready=true" not in out

    def idle(**kw):
        rc, out, log = run_script(script_text=script_text, **kw)
        return "ready=true" not in out and "waiting" in log

    def hints(**kw):
        _, _, log = run_script(script_text=script_text, **kw)
        return log.count("::notice::no agy-formal-review")

    def hinted(**kw):
        _, _, log = run_script(script_text=script_text, **kw)
        return ("gh workflow run agy-formal-dispatch.yml --repo mctlhq/.github --ref main "
                f"-f repository=o/r -f pr_number=7 -f head_sha={HEAD}") in log

    def asks(want, **kw):  # STAGE=dispatch: the verdict, and never an enqueue verdict
        rc, out, _ = run_script(script_text=script_text, stage="dispatch", **kw)
        head = f"head_sha={HEAD}" in out
        return rc == 0 and f"dispatch={want}" in out and "ready=true" not in out and head == (want == "true")

    def no_ask(**kw):
        rc, out, log = run_script(script_text=script_text, stage="dispatch", **kw)
        return "dispatch=true" not in out and (("::error::" in log and rc != -9) or "waiting" in log or "ready=false" in out)

    def done(**kw):
        rc, out, _ = run_script(script_text=script_text, **kw)
        return rc == 0 and "ready=false" in out and "ready=true" not in out

    pending = green() + [run_for("trivy", "in_progress", None)]
    other = "platform-gitops/bootstrap/templates/projects/project-default.yaml"
    return [
        ("approved, green, App author, the pushed head, one template -> ready", lambda: ready(), True),
        ("the platform template is allowed too",
         lambda: ready(files=("platform-gitops/bootstrap/templates/projects/project-platform.yaml",),
                       target="platform-gitops/bootstrap/templates/projects/project-platform.yaml"), True),
        ("a head that is not the pushed commit is refused", lambda: refused(pr_head="b" * 40, cur="b" * 40), True),
        ("a human author is refused", lambda: refused(author="mashkovd"), True),
        ("another bot is refused", lambda: refused(author="mctl-agents[bot]"), True),
        ("a head in a fork is refused", lambda: refused(head_repo="evil/r"), True),
        ("a branch outside release-window/ is refused", lambda: refused(head_ref="release-bump/x"), True),
        ("an unreadable PR is refused", lambda: refused(pr_ok=False), True),
        ("the default project template as target is refused", lambda: refused(files=(other,), target=other), True),
        ("a target that is not a project template is refused",
         lambda: refused(files=("scripts/release-gate.py",), target="scripts/release-gate.py"), True),
        ("a different file than the target is refused", lambda: refused(files=("platform-gitops/argocd/values.yaml",)), True),
        ("a second file is refused", lambda: refused(files=(TARGET, "README.md")), True),
        ("a short file list is refused", lambda: refused(changed=2), True),
        ("a rename onto the target is refused", lambda: refused(prev="platform-gitops/old.yaml"), True),
        ("an unreadable file list is refused", lambda: refused(files_ok=False), True),
        ("a merged PR is a no-op", lambda: done(merged="true", state="closed"), True),
        ("a closed PR is a no-op", lambda: done(state="closed"), True),
        ("a head moved during the wait is refused", lambda: refused(cur="b" * 40), True),
        ("an unreadable review state is refused", lambda: refused(review_ok=False), True),
        ("changes requested is refused", lambda: refused(decision="CHANGES_REQUESTED"), True),
        ("an unknown review decision is refused", lambda: refused(decision="SOMETHING"), True),
        ("no review yet waits", lambda: idle(decision="REVIEW_REQUIRED", on_head=0), True),
        ("APPROVED with no approval on this head waits", lambda: idle(on_head=0), True),
        ("a pending check waits", lambda: idle(runs=pending), True),
        ("a missing required check waits", lambda: idle(runs=[r for r in green() if r["name"] != "validate"]), True),
        ("dispatch: approved with no formal review -> ask, even with CI pending",
         lambda: asks("true", runs=[run_for("validate", "in_progress", None)]), True),
        ("dispatch: a failed formal review is asked again",
         lambda: asks("true", runs=[run_for("agy-formal-review", conclusion="failure")]), True),
        ("dispatch: a passed formal review is not asked again", lambda: asks("false", runs=green()), True),
        ("dispatch: a running formal review is not asked again",
         lambda: asks("false", runs=[run_for("agy-formal-review", "in_progress", None)]), True),
        ("dispatch: the newest formal review decides",
         lambda: asks("false", runs=[run_for("agy-formal-review", conclusion="failure"), run_for("agy-formal-review")]), True),
        ("dispatch: no approval, no request", lambda: no_ask(decision="REVIEW_REQUIRED", on_head=0), True),
        ("dispatch: an approval on another head, no request", lambda: no_ask(on_head=0), True),
        ("dispatch: changes requested, no request", lambda: no_ask(decision="CHANGES_REQUESTED", runs=[]), True),
        ("dispatch: a moved head, no request", lambda: no_ask(cur="b" * 40, runs=[]), True),
        ("dispatch: a human author, no request", lambda: no_ask(author="mashkovd", runs=[]), True),
        ("dispatch: an unreadable check list, no request", lambda: no_ask(runs_ok=False), True),
        ("dispatch: a truncated check list, no request", lambda: no_ask(runs=[], total=3), True),
        ("an unknown stage is refused", lambda: refused(stage="merge"), True),
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
        # Removal: the same gate with its own branch prefix and a deletions-only diff.
        ("removal: approved, green, pure deletion on its own branch -> ready",
         lambda: ready(kind="remove", additions=0, deletions=8), True),
        ("removal: one deleted line is enough", lambda: ready(kind="remove", additions=0, deletions=1), True),
        ("removal: a diff with an added line is refused", lambda: refused(kind="remove", additions=1, deletions=8), True),
        ("removal: a diff with no deleted line is refused", lambda: refused(kind="remove", additions=0, deletions=0), True),
        ("removal: unreadable line counts are refused", lambda: refused(kind="remove", additions="null", deletions="null"), True),
        ("removal: an addition branch is refused", lambda: refused(kind="remove", additions=0, deletions=8,
                                                                   head_ref="release-window/w-1"), True),
        ("addition: a removal branch is refused", lambda: refused(head_ref="release-window-removal/w-1"), True),
        ("removal: a human author is refused", lambda: refused(kind="remove", additions=0, deletions=8, author="mashkovd"), True),
        ("removal: a second file is refused", lambda: refused(kind="remove", additions=0, deletions=8, files=(TARGET, "README.md")), True),
        ("removal: the default project template is refused",
         lambda: refused(kind="remove", additions=0, deletions=8, files=(other,), target=other), True),
        ("an unknown kind is refused", lambda: refused(kind="both", additions=0, deletions=8), True),
        ("a kind with a different case is refused", lambda: refused(kind="Remove", additions=0, deletions=8), True),
        ("no approval by the deadline is a refusal", lambda: refused(on_head=0, wait_seconds=0), True),
    ]


MUTANTS = {
    "dispatch repeated over a pass": ('if [ "$formal" = "completed success" ]; then', 'if false; then'),
    "dispatch over a running review": ('absent|"completed "*) ;;', '*) ;;'),
    "truncated list dispatches": ('[ "$(jq -s length <<<"$runs")" = "$total" ]', 'true'),
    "unknown stage accepted": ('case "$STAGE" in enqueue|dispatch) ;;', 'case "$STAGE" in *) ;;'),
    "formal review not required": ("REQUIRED_CHECKS=agy-formal-review,", "REQUIRED_CHECKS="),
    "no dispatch hint": ('echo "::notice::no agy-formal-review', 'true "'),
    "dispatch hint repeated": ("          hinted=1\n", ""),
    "pushed head not compared": ('[ "$head_sha" = "$EXPECT_HEAD" ] ||', 'true ||'),
    "author check dropped": ('[ "$author" = "$APP_LOGIN" ] ||', 'true ||'),
    "fork check dropped": ('[ "$head_repo" = "$REPO" ] ||', 'true ||'),
    "branch check dropped": ('case "$head_ref" in "${BRANCH_PREFIX}"?*) ;; *)', 'case "$head_ref" in *) ;; *)'),
    "target shape unchecked": ('|| die "\'${TARGET}\' is not the apps or platform project template; not enqueueing."', '|| true'),
    "file count ignored": ('[ "$expected" = 1 ] ||', 'true ||'),
    "file list not compared to the target": ('[ "$files" = "${TARGET}"$\'\\t\' ] ||', 'true ||'),
    "moved head accepted": ('[ "$cur" = "$head_sha" ] ||', 'true ||'),
    "approval on another head accepted": ('APPROVED) [[ "$on_head" =~ ^[1-9][0-9]*$ ]] && approved=1 ;;', 'APPROVED) approved=1 ;;'),
    "review not required": ('REVIEW_REQUIRED|null) ;;', 'REVIEW_REQUIRED|null) approved=1 ;;'),
    "changes requested waits": ('CHANGES_REQUESTED) die', 'CHANGES_REQUESTED) : die'),
    "not-ready verdict accepted": ("    case \"$rc\" in\n      0)", "    case \"$rc\" in\n      0|10|11|12)"),
    "a failed check waits": ('*) die "#${PR} is not mergeable: ${verdict}" ;;', '*) echo waiting ;;'),
    "deadline ignored": ('if [ "$SECONDS" -ge "$deadline" ]; then', 'if false; then'),
    "branch prefix not kind-bound": ('case "$head_ref" in "${BRANCH_PREFIX}"?*) ;; *)', 'case "$head_ref" in release-window*) ;; *)'),
    "added lines allowed in a removal": ('[ "$additions" = 0 ] && [ "$deletions" -ge 1 ] ||', '[ "$deletions" -ge 0 ] ||'),
    "removal may delete nothing": ('[ "$additions" = 0 ] && [ "$deletions" -ge 1 ] ||', '[ "$additions" = 0 ] ||'),
    "unknown kind falls through": ("*) die \"WINDOW_KIND must be add or remove", "*) BRANCH_PREFIX='release-window' ; : die \"WINDOW_KIND must be add or remove"),
}


def main():
    text = SCRIPT.read_text()
    for name, thunk, want in cases():
        got = thunk()
        assert got == want, f"case failed: {name}"
    for name, (old, new) in MUTANTS.items():
        assert old in text, f"mutant anchor missing: {name}"
        mutated = text.replace(old, new, 1)
        failed = [n for n, thunk, want in cases(mutated) if thunk() != want]
        assert failed, f"mutant not caught: {name}"
    print("ok")


if __name__ == "__main__":
    main()
