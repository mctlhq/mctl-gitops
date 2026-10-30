#!/usr/bin/env python3
"""Fail when a GitHub Actions `run:` step interpolates attacker-influenced input.

`${{ inputs.x }}` is substituted into the *text* of a step's script before the
shell parses it, so a value carrying `$(...)` or a quote runs as a command, in
jobs that may hold a deploy key. Binding the value through `env:` and reading
it as "$X" removes the exposure (gitops#1809).

Scanned: `run:` of every step, and `with.script` of actions/github-script, in
.github/workflows/*.y*ml and .github/actions/**/action.y*ml. Flagged contexts:
inputs.*, github.event.*, github.head_ref. `env:`, `with:`, `if:` and
`run-name:` are not script text and are not flagged.

Exit 1 on findings, 2 on unparseable YAML. Run with --selftest to prove the
detector still detects.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)
UNSAFE = re.compile(r"\b(inputs\.|github\.event\.|github\.head_ref\b)")


def step_texts(step: dict):
    run = step.get("run")
    if isinstance(run, str):
        yield run
    uses = step.get("uses")
    if isinstance(uses, str) and uses.startswith("actions/github-script"):
        script = (step.get("with") or {}).get("script")
        if isinstance(script, str):
            yield script


def scan_file(path: Path, root: Path) -> list[str]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        return []
    rel = path.relative_to(root)
    groups = []  # (job name, steps)
    for name, job in (data.get("jobs") or {}).items():
        if isinstance(job, dict):
            groups.append((name, job.get("steps")))
    runs = data.get("runs")
    if isinstance(runs, dict):
        groups.append(("(composite)", runs.get("steps")))
    out = []
    for job, steps in groups:
        for i, step in enumerate(steps or []):
            if not isinstance(step, dict):
                continue
            label = step.get("name") or step.get("id") or f"step[{i}]"
            for text in step_texts(step):
                for m in EXPR.finditer(text):
                    if UNSAFE.search(m.group(1)):
                        out.append(
                            f"{rel} / {job} / {label}: run interpolates "
                            f"${{{{{m.group(1)}}}}}; bind it via env:"
                        )
    return out


def files(root: Path) -> list[Path]:
    found: list[Path] = []
    wf = root / ".github/workflows"
    for pat in ("*.yml", "*.yaml"):
        found += sorted(wf.glob(pat))
    act = root / ".github/actions"
    for pat in ("action.yml", "action.yaml"):
        found += sorted(act.glob(f"**/{pat}"))
    return found


def scan(root: Path) -> int:
    findings: list[str] = []
    for f in files(root):
        try:
            findings += scan_file(f, root)
        except yaml.YAMLError as e:
            print(f"ERROR: cannot parse {f}: {e}", file=sys.stderr)
            return 2
    for line in findings:
        print(line)
    return 1 if findings else 0


def selftest() -> int:
    bad = {
        "multi": "jobs:\n  j:\n    steps:\n      - run: |\n          echo hi\n          echo ${{ inputs.x }}\n",
        "single": "jobs:\n  j:\n    steps:\n      - run: echo ${{inputs.x}}\n",
        "event": "jobs:\n  j:\n    steps:\n      - run: echo \"${{ github.event.pull_request.title }}\"\n",
        "script": "jobs:\n  j:\n    steps:\n      - uses: actions/github-script@v7\n        with:\n          script: |\n            core.info('${{ inputs.x }}')\n",
    }
    good = (
        "run-name: ${{ inputs.x }}\n"
        "jobs:\n  j:\n    if: ${{ inputs.x }}\n    steps:\n"
        "      - if: ${{ inputs.x }}\n        env:\n          X: ${{ inputs.x }}\n"
        "          Y: ${{ github.event.pull_request.title }}\n"
        "        run: echo \"$X\" ${{ secrets.T }}\n"
        "      - uses: actions/checkout@v4\n        with:\n          ref: ${{ inputs.x }}\n"
    )
    ok = True
    for name, text in bad.items():
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/w.yml").write_text(text)
            if scan(root) != 1:
                print(f"selftest FAIL: '{name}' not detected", file=sys.stderr)
                ok = False
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".github/workflows").mkdir(parents=True)
        (root / ".github/workflows/w.yml").write_text(good)
        if scan(root) != 0:
            print("selftest FAIL: false positive on env/with/if/run-name", file=sys.stderr)
            ok = False
    print("selftest ok" if ok else "selftest FAILED")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    return scan(ROOT)


if __name__ == "__main__":
    sys.exit(main())
