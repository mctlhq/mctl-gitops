"""Exercise the optional work-context env binding, taken from the templates.

`cwft-mctl-agents-implement.yaml` and `cwft-mctl-agents-shepherd.yaml` accept
five optional, empty-by-default parameters — `work_item_id`, `execution_id`,
`temporal_workflow_id`, `temporal_run_id`, `execution_request_id` — mirroring
gitops#1279 on `cwft-mctl-agents-investigate.yaml` (owner decision 4 of
mctlhq/.github#50), with one deliberate difference: `run_implementer.py` and
`run_shepherd.py` have no `--work-item-id`-style flags, so the values travel
through `env` ONLY and must never reach argv. Appending an unknown flag would
make argparse exit non-zero on every run, including the cron sweep.

The acceptance criterion that matters most is that a submit omitting all five
(or passing them as empty strings, or setting them to hostile values) produces
argv byte-identical to what each template built before these parameters
existed — the env-only channel must be provably incapable of leaking into the
command line.

The blocks under test are EXTRACTED from the CWFTs rather than restated — a
copy would keep passing after the template changed, which is the failure mode
this file exists to avoid (same reasoning as test_tpl_git_commit_yq.py and
test_cwft_investigate_work_context_argv.py). Neither slice invokes python or
git — the real call happens later in the body, after `set +e` — so both are
safe to run directly under /bin/sh.

Run: python3 tests/test_cwft_implement_shepherd_work_context_env.py
"""
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "platform-gitops/argo-workflows/cluster-templates"

ARROW = "→"  # the literal character `printf '→'` writes

FIVE_PARAMS = [
    "work_item_id", "execution_id", "temporal_workflow_id",
    "temporal_run_id", "execution_request_id",
]
FIVE_ENV = [
    "WORKFLOW_WORK_ITEM_ID", "WORKFLOW_EXECUTION_ID",
    "WORKFLOW_TEMPORAL_WORKFLOW_ID", "WORKFLOW_TEMPORAL_RUN_ID",
    "WORKFLOW_EXECUTION_REQUEST_ID",
]

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name}: {detail}")


def iter_interpreted_blocks(template):
    """Every interpreted-block string in one template dict: container
    args/command, script.source, initContainers commands."""
    blocks = []
    container = template.get("container")
    if container:
        args = container.get("args") or []
        blocks.extend(args)
        command = container.get("command")
        if command:
            blocks.extend(command if isinstance(command, list) else [command])
    script = template.get("script")
    if script and script.get("source"):
        blocks.append(script["source"])
    for ic in template.get("initContainers") or []:
        command = ic.get("command")
        if command:
            blocks.extend(command if isinstance(command, list) else [command])
    return blocks


class TemplateFixture:
    """One CWFT under test: its runner name, argv slice markers, and the
    module name run_implementer/run_shepherd builds argv for."""

    def __init__(self, filename, runner_name, module, start_marker, end_marker,
                 pre_existing_params, control_env_defaults):
        self.filename = filename
        self.path = TEMPLATES_DIR / filename
        self.runner_name = runner_name
        self.module = module
        self.start_marker = start_marker
        self.end_marker = end_marker
        self.pre_existing_params = pre_existing_params
        # Every WORKFLOW_* var the slice itself reads (service/slug/... ),
        # defaulted here rather than left to whatever happens to be in
        # os.environ — this process's OWN env carries WORKFLOW_SERVICE /
        # WORKFLOW_SLUG (set by the orchestrator that ran this implementer),
        # which would otherwise silently leak into the "base" argv below and
        # mask a real regression.
        self.control_env_defaults = control_env_defaults
        self.doc = yaml.safe_load(self.path.read_text())
        self.templates = self.doc["spec"]["templates"]
        self.runner = next(t for t in self.templates if t["name"] == runner_name)
        self.slice = self._argv_slice()

    def _argv_slice(self):
        source = self.runner["container"]["args"][2]
        start = source.find(self.start_marker)
        if start == -1:
            raise AssertionError(
                f"{self.filename}: could not find start marker "
                f"{self.start_marker!r} in {self.runner_name}'s container.args "
                "— the template changed shape and this test is now checking "
                "nothing")
        end = source.find(self.end_marker, start)
        if end == -1:
            raise AssertionError(
                f"{self.filename}: could not find end marker "
                f"{self.end_marker!r} after the start marker — the template "
                "changed shape and this test is now checking nothing")
        return source[start:end + len(self.end_marker)]

    def run(self, env_overrides):
        env = dict(os.environ)
        for name in FIVE_ENV:
            env[name] = ""
        env.update(self.control_env_defaults)
        env.update(env_overrides)
        script = "set -e\n" + self.slice
        return subprocess.run(
            ["sh", "-c", script],
            capture_output=True, text=True, env=env,
        )


IMPLEMENT = TemplateFixture(
    filename="cwft-mctl-agents-implement.yaml",
    runner_name="run-implementer",
    module="run_implementer",
    start_marker="set -- python -m orchestrator.run_implementer",
    end_marker="printf '\\n'",
    pre_existing_params=["service", "slug", "force", "max_proposals",
                          "agent_image", "agent_version"],
    control_env_defaults={
        "WORKFLOW_SERVICE": "", "WORKFLOW_SLUG": "",
        "WORKFLOW_MAX_PROPOSALS": "1",
    },
)

SHEPHERD = TemplateFixture(
    filename="cwft-mctl-agents-shepherd.yaml",
    runner_name="run-shepherd",
    module="run_shepherd",
    start_marker="set -- python -m orchestrator.run_shepherd",
    end_marker="printf '\\n'",
    pre_existing_params=["service", "slug", "dry_run", "agent_image",
                          "agent_version"],
    control_env_defaults={
        "WORKFLOW_SERVICE": "", "WORKFLOW_SLUG": "",
        "WORKFLOW_DRY_RUN": "false",
    },
)

FIXTURES = [IMPLEMENT, SHEPHERD]

# ── Static half ──────────────────────────────────────────────────────────

for fx in FIXTURES:
    param_names = [p["name"] for p in fx.doc["spec"]["arguments"]["parameters"]]
    for name in fx.pre_existing_params:
        check(f"{fx.filename}: pre-existing parameter {name} still declared",
              name in param_names, f"params={param_names}")
    for name in FIVE_PARAMS:
        matching = [p for p in fx.doc["spec"]["arguments"]["parameters"]
                    if p["name"] == name]
        check(f"{fx.filename}: parameter {name} declared exactly once "
              "with empty default",
              len(matching) == 1 and matching[0].get("value") == "",
              f"matching={matching}")

    env_names = [e["name"] for e in fx.runner["container"]["env"]]
    for name in FIVE_ENV:
        expected_param = {
            "WORKFLOW_WORK_ITEM_ID": "work_item_id",
            "WORKFLOW_EXECUTION_ID": "execution_id",
            "WORKFLOW_TEMPORAL_WORKFLOW_ID": "temporal_workflow_id",
            "WORKFLOW_TEMPORAL_RUN_ID": "temporal_run_id",
            "WORKFLOW_EXECUTION_REQUEST_ID": "execution_request_id",
        }[name]
        matching = [e for e in fx.runner["container"]["env"] if e["name"] == name]
        want_value = "{{workflow.parameters.%s}}" % expected_param
        check(f"{fx.filename}: env {name} bound exactly once to {want_value}",
              len(matching) == 1 and matching[0].get("value") == want_value,
              f"count={env_names.count(name)} matching={matching}")

    for template in fx.templates:
        for block in iter_interpreted_blocks(template):
            for name in FIVE_PARAMS:
                placeholder = "{{workflow.parameters.%s}}" % name
                check(f"{fx.filename}: template {template['name']} does not "
                      f"interpolate {placeholder} in an interpreted block",
                      placeholder not in block,
                      f"found in: {block!r}")

# ── Executable half ──────────────────────────────────────────────────────

# T1 / T2. Omit-all (unset, and explicit empty string) reproduces today's
# exact argv — the most important assertion in this file.
IMPLEMENT_BASE_ARGV = (
    f"{ARROW} python -m orchestrator.run_implementer --max-proposals 1\n")
SHEPHERD_BASE_ARGV = f"{ARROW} python -m orchestrator.run_shepherd\n"

for fx, base_argv, base_env in (
    (IMPLEMENT, IMPLEMENT_BASE_ARGV, {"WORKFLOW_MAX_PROPOSALS": "1"}),
    (SHEPHERD, SHEPHERD_BASE_ARGV, {}),
):
    proc = fx.run(base_env)
    check(f"{fx.filename}: omit-all (unset) reproduces today's exact argv",
          proc.returncode == 0 and proc.stdout == base_argv,
          f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

    env_explicit_empty = dict(base_env)
    env_explicit_empty.update({name: "" for name in FIVE_ENV})
    proc = fx.run(env_explicit_empty)
    check(f"{fx.filename}: omit-all-explicit (empty string) reproduces "
          "today's exact argv",
          proc.returncode == 0 and proc.stdout == base_argv,
          f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

    # T3. Set-all with benign values — output byte-identical to the base
    # case: the env-only channel must not be able to leak into argv.
    env_set_all = dict(base_env)
    env_set_all.update({
        "WORKFLOW_WORK_ITEM_ID": "wi-abc",
        "WORKFLOW_EXECUTION_ID": "we-123",
        "WORKFLOW_TEMPORAL_WORKFLOW_ID": "dev-loop-xr_1",
        "WORKFLOW_TEMPORAL_RUN_ID": "run-9",
        "WORKFLOW_EXECUTION_REQUEST_ID": "xr_1",
    })
    proc = fx.run(env_set_all)
    check(f"{fx.filename}: set-all (benign values) does not change argv",
          proc.returncode == 0 and proc.stdout == base_argv,
          f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

    # T4. Injection — hostile values must not execute, and argv must still be
    # byte-identical to the base case (absence is the contract here: unlike
    # the investigate test, there is no surviving-token assertion, because
    # these values never reach argv at all).
    with tempfile.TemporaryDirectory() as d:
        sentinel = pathlib.Path(d) / "pwned"
        hostile_a = f"; touch {sentinel} ; "
        hostile_b = 'a" ; id ; "b'
        env_injection = dict(base_env)
        env_injection.update({
            "WORKFLOW_WORK_ITEM_ID": hostile_a,
            "WORKFLOW_EXECUTION_ID": hostile_b,
            "WORKFLOW_TEMPORAL_WORKFLOW_ID": hostile_a,
            "WORKFLOW_TEMPORAL_RUN_ID": hostile_b,
            "WORKFLOW_EXECUTION_REQUEST_ID": hostile_a,
        })
        proc = fx.run(env_injection)
        check(f"{fx.filename}: an injecting correlation value does not execute",
              not sentinel.exists(), f"sentinel created: {sentinel}")
        check(f"{fx.filename}: injection case argv is byte-identical to "
              "the base case",
              proc.returncode == 0 and proc.stdout == base_argv,
              f"rc={proc.returncode} stdout={proc.stdout!r} "
              f"stderr={proc.stderr!r}")

# T5. Slice-is-live regression: with the five new vars unset, the template's
# own pre-existing parameters still work. Without this, a slice that
# silently matched an empty or wrong region would pass T1-T4 while checking
# nothing.
proc = IMPLEMENT.run({
    "WORKFLOW_SERVICE": "mctl-web",
    "WORKFLOW_SLUG": "issue-1-x",
    "WORKFLOW_MAX_PROPOSALS": "3",
})
want = (f"{ARROW} python -m orchestrator.run_implementer "
        "--service mctl-web --slug issue-1-x --max-proposals 3\n")
check("cwft-mctl-agents-implement.yaml: slice is live — "
      "service/slug/max-proposals still work",
      proc.returncode == 0 and proc.stdout == want,
      f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

proc = SHEPHERD.run({"WORKFLOW_DRY_RUN": "true"})
want = f"{ARROW} python -m orchestrator.run_shepherd --dry-run\n"
check("cwft-mctl-agents-shepherd.yaml: slice is live — --dry-run still works",
      proc.returncode == 0 and proc.stdout == want,
      f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

proc = SHEPHERD.run({"WORKFLOW_SERVICE": "mctl-web", "WORKFLOW_SLUG": "issue-1-x"})
want = (f"{ARROW} python -m orchestrator.run_shepherd "
        "--service mctl-web --slug issue-1-x\n")
check("cwft-mctl-agents-shepherd.yaml: slice is live — service/slug still work",
      proc.returncode == 0 and proc.stdout == want,
      f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")

if failures:
    print("\n".join(["", "FAILURES:"] + failures), file=sys.stderr)
    sys.exit(1)
print("\nwork-context env binding behaves as documented")
sys.exit(0)
