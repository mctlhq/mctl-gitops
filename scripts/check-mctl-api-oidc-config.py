#!/usr/bin/env python3
"""Run the DEPLOYED mctl-api image's own startup validation on the values the
zitadel-iac Job renders for it.

Why (2026-11-17): gitops#2737 put service_subjects on the MCTL_OIDC_PROVIDERS
entry that also has customers_org_id. mctl-api (internal/auth/federation_config.go)
refuses to boot on that combination, the 4.166.0 rollout crash-looped, and no CI
step here could have seen it: the rule lives in mctl-api.

This script re-implements NO rule. It assembles the environment mctl-api would
see and runs `mctl-api --check-config` from the image pinned in
platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml:

  * non-secret env: the `env:` map of that Application's Helm values;
  * the keys zitadel-iac writes into the Secrets mctl-api reads
    (MCTL_OIDC_PROVIDERS, ZITADEL_HOOK_*): from
    platform-gitops/helm-charts/zitadel-iac/iac/tests/fixtures/mctl-api-config-check.json,
    which `tofu test` proves equal to what the root renders
    (tests/mctl_api_config_check.tftest.hcl), so the two cannot drift;
  * placeholders for keys that only need to be present (OAUTH_JWT_SECRET from
    Vault, the OAUTH_ZITADEL_CLIENT_* pair). Their presence in the live Secrets
    is NOT verified here.

Fail closed. Success means the image printed the exact ok line. Everything else
fails: no docker, a pull that never succeeds, a non-zero exit, an exit 0 without
the ok line (an image that predates the flag ignores it and boots the server;
it runs here with no network and is killed), a timeout, an unparsable tag, a
changed Secret wiring.

The ONE skip is the documented transition: a pinned tag older than
MIN_CHECKER_VERSION (the first mctl-api release containing --check-config,
mctlhq/mctl-api#1108) is skipped with a visible ::warning. The decision comes
only from the version string, never from probing, so "could not run" is never
"skipped". Raise nothing, lower nothing, without the release: once the pin is
at or above MIN_CHECKER_VERSION the check is unconditional.

Usage: check-mctl-api-oidc-config.py [--selftest]
       [--image-tag TAG] [--min-version X.Y.Z]   (local proofs only)
"""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT / "platform-gitops/bootstrap"  # renders templates/mctl-platform/mctl-api.yaml
FIXTURE = ROOT / "platform-gitops/helm-charts/zitadel-iac/iac/tests/fixtures/mctl-api-config-check.json"
IMAGE_REPO = "ghcr.io/mctlhq/mctl-api"

# First mctl-api release with `--check-config` (mctlhq/mctl-api#1108). Set to
# the real tag when that release exists; until the pin reaches it the check is
# skipped, loudly. A value above the true first release only delays enforcement;
# one below it makes every pin in between fail closed (no ok line).
MIN_CHECKER_VERSION = "4.167.0"

OK_LINE = "mctl-api check-config: ok"
RUN_TIMEOUT = 90
PULL_ATTEMPTS = 3

# The Secrets the Application reads these keys from, and the writer in
# zitadel-iac. If the wiring changes, the fixture no longer stands for what
# mctl-api sees, and the guard must be revisited rather than pass.
WIRING = {
    "oidcProvidersSecret": "mctl-api-oidc-zitadel",
    "zitadelLinkSecret": "mctl-api-oidc-zitadel",
    "oauthZitadelSecret": "mctl-api-oidc-zitadel",
}
HOOK_SECRET = "mctl-api-zitadel-hook"
# Keys that only need to be non-empty for validation; the real ones are
# Vault/ZITADEL generated and never in git.
PLACEHOLDERS = {
    "OAUTH_JWT_SECRET": "placeholder-not-a-secret",
    "OAUTH_ZITADEL_CLIENT_ID": "placeholder-client-id",
    "OAUTH_ZITADEL_CLIENT_SECRET": "placeholder-not-a-secret",
}
FIXTURE_ENV_KEYS = (
    "ZITADEL_HOOK_CUSTOMERS_ORG_ID",
    "ZITADEL_HOOK_GITHUB_IDP_ID",
    "ZITADEL_HOOK_GOOGLE_IDP_ID",
)


class Refuse(Exception):
    """A reason to fail the check. Never caught except to print and exit 1."""


def semver(text, what):
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(text))
    if not m:
        raise Refuse(f"{what} {text!r} is not MAJOR.MINOR.PATCH; cannot decide whether the image has --check-config")
    return tuple(int(g) for g in m.groups())


def load_values():
    """The Helm values of the mctl-api source of the admins-mctl-api
    Application, as Argo CD gets them: the file is a template of the bootstrap
    chart (`{{- if }}` inside the values block), so it is rendered with the
    committed bootstrap values, as validate-manifests.yml does elsewhere."""
    if shutil.which("helm") is None:
        raise Refuse("helm not found: cannot render the Application whose values pin the image")
    res = run(["helm", "template", "test", str(BOOTSTRAP), "-f", str(BOOTSTRAP / "values.yaml")])
    if res.returncode != 0:
        raise Refuse(f"helm template of the bootstrap chart failed: {res.stderr.strip()[-500:]}")
    found = []
    for doc in yaml.safe_load_all(res.stdout):
        if isinstance(doc, dict) and doc.get("kind") == "Application" and doc["metadata"]["name"] == "admins-mctl-api":
            for src in doc["spec"]["sources"]:
                h = src.get("helm") or {}
                if h.get("releaseName") == "mctl-api" and "values" in h:
                    found.append(yaml.safe_load(h["values"]))
    if len(found) != 1:
        raise Refuse(f"expected exactly one mctl-api values block in Application admins-mctl-api, found {len(found)}")
    return found[0]


def env_text(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (str, int, float)):
        s = str(v)
        if "\n" in s or "\r" in s:
            raise Refuse("an env value contains a newline; --env-file cannot carry it")
        return s
    raise Refuse(f"env value {v!r} is not a scalar")


def build_env(values, fixture):
    for key, want in WIRING.items():
        if values.get(key) != want:
            raise Refuse(f"{key} is {values.get(key)!r}, the guard assumes {want!r}: the fixture no longer stands for the Secret mctl-api reads")
    if HOOK_SECRET not in (values.get("envFromOptionalSecrets") or []):
        raise Refuse(f"envFromOptionalSecrets no longer lists {HOOK_SECRET}")
    # A null is Helm for "unset" (the chart renders no entry).
    env = {k: env_text(v) for k, v in (values.get("env") or {}).items() if v is not None}
    # Compact JSON: byte-for-byte what mctl-api parses.
    providers = json.dumps(fixture["MCTL_OIDC_PROVIDERS"], separators=(",", ":"))
    secret_keys = {"MCTL_OIDC_PROVIDERS": providers}
    for k in FIXTURE_ENV_KEYS:
        if k in fixture:
            secret_keys[k] = env_text(fixture[k])
    for k, v in {**secret_keys, **PLACEHOLDERS}.items():
        if k in env:
            raise Refuse(f"{k} is set both in the chart env and by a Secret; the chart refuses that, and so does the guard")
        env[k] = v
    return env


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def check_image(image, env, docker="docker"):
    if shutil.which(docker) is None:
        raise Refuse(f"{docker} not found: cannot run {image}")
    have = run([docker, "image", "inspect", image])
    if have.returncode != 0:
        for attempt in range(1, PULL_ATTEMPTS + 1):
            pulled = run([docker, "pull", image])
            if pulled.returncode == 0:
                break
            print(f"docker pull {image} failed (attempt {attempt}/{PULL_ATTEMPTS}): {pulled.stderr.strip()[-300:]}", file=sys.stderr)
            if attempt == PULL_ATTEMPTS:
                raise Refuse(f"could not pull {image}; unknown is not ok")
            import time
            time.sleep(float(os.environ.get("CHECK_PULL_DELAY", "10")) * attempt)
    name = f"mctl-api-config-check-{os.getpid()}"
    with tempfile.TemporaryDirectory() as d:
        envfile = Path(d) / "env"
        envfile.write_text("".join(f"{k}={v}\n" for k, v in sorted(env.items())))
        cmd = [docker, "run", "--rm", "--name", name, "--network", "none", "--read-only",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--env-file", str(envfile), image, "--check-config"]
        try:
            res = run(cmd, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise Refuse(f"{image} did not finish --check-config in {RUN_TIMEOUT}s: an image without the flag boots the server instead")
        finally:
            run([docker, "rm", "-f", name])
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    if res.returncode != 0:
        out = (res.stderr.strip() + "\n" + res.stdout.strip()).strip()
        raise Refuse(f"mctl-api refused this configuration, or does not implement --check-config (exit {res.returncode}):\n{out[-1500:]}")
    if not lines or lines[-1].strip() != OK_LINE:
        raise Refuse(f"{image} exited 0 without the line {OK_LINE!r}: it does not implement --check-config, so nothing was validated")


def guard(values, fixture_path, tag_override=None, min_version=MIN_CHECKER_VERSION, docker="docker"):
    tag = tag_override or (values.get("image") or {}).get("tag")
    if (values.get("image") or {}).get("repository") != IMAGE_REPO:
        raise Refuse(f"image.repository is not {IMAGE_REPO}")
    if semver(tag, "image.tag") < semver(min_version, "MIN_CHECKER_VERSION"):
        print(f"::warning title=mctl-api config guard SKIPPED::pinned mctl-api {tag} predates "
              f"--check-config (first in {min_version}). The rendered MCTL_OIDC_PROVIDERS was NOT run through "
              f"mctl-api's validator. This skip ends when the pin reaches {min_version}.")
        return "skipped"
    fixture = json.loads(fixture_path.read_text())
    env = build_env(values, fixture)
    check_image(f"{IMAGE_REPO}:{tag}", env, docker)
    print(f"{IMAGE_REPO}:{tag} accepted the rendered configuration ({OK_LINE})")
    return "ok"


# ---------------------------------------------------------------- selftest
FAKE_DOCKER = r"""#!/bin/sh
# Stub docker: behaviour chosen by $FAKE_MODE; logs calls to $FAKE_LOG.
echo "$*" >> "$FAKE_LOG"
case "$1" in
  image) [ "$FAKE_MODE" != pull_fails ] && [ "$FAKE_MODE" != pull_fails_inspect ] ; exit $? ;;
  pull) exit 1 ;;
  rm) exit 0 ;;
  run)
    case "$FAKE_MODE" in
      ok) echo "mctl-api check-config: ok"; exit 0 ;;
      refuse) echo "mctl-api check-config: invalid configuration: boom" >&2; exit 1 ;;
      old_image) echo '{"msg":"server started"}'; exit 0 ;;
      ok_text_in_middle) echo "mctl-api check-config: ok"; echo "later"; exit 0 ;;
    esac ;;
esac
exit 99
"""


def selftest():
    failures = []

    def expect(name, fn, want):
        try:
            got = fn()
        except Refuse as e:
            got = f"refuse:{e}"
        ok = got == want if want in ("ok", "skipped") else str(got).startswith("refuse:") and want in str(got)
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" (got {got!r}, want {want!r})"))
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        bindir = d / "bin"
        bindir.mkdir()
        fake = bindir / "docker"
        fake.write_text(FAKE_DOCKER)
        fake.chmod(0o755)
        log = d / "calls.log"
        os.environ["FAKE_LOG"] = str(log)
        os.environ["CHECK_PULL_DELAY"] = "0"
        # An absolute docker path keeps the selftest independent of PATH.
        dk = str(fake)

        base = load_values()

        def g(mode, values=None, tag=None, minv="4.0.0"):
            os.environ["FAKE_MODE"] = mode
            return lambda: guard(copy.deepcopy(values or base), FIXTURE, tag_override=tag, min_version=minv, docker=dk)

        def mut(fn):
            v = copy.deepcopy(base)
            fn(v)
            return v

        # The real rendered Application and fixture, a stubbed docker.
        env = build_env(base, json.loads(FIXTURE.read_text()))
        assert env["OAUTH_UPSTREAM"] == "zitadel", "the guard must see the Application's own env"
        assert json.loads(env["MCTL_OIDC_PROVIDERS"]) == json.loads(FIXTURE.read_text())["MCTL_OIDC_PROVIDERS"]

        expect("good input, image prints the ok line", g("ok"), "ok")
        expect("image refuses the configuration", g("refuse"), "refused this configuration")
        expect("image without the flag (boots, exit 0, no ok line)", g("old_image"), "does not implement --check-config")
        expect("ok line not last (output not trusted)", g("ok_text_in_middle"), "does not implement --check-config")
        expect("pull fails every attempt", g("pull_fails"), "could not pull")
        expect("docker missing", lambda: check_image("x:1", {}, docker="/nonexistent/docker"), "not found")
        expect("tag unparsable", g("ok", tag="latest"), "is not MAJOR.MINOR.PATCH")
        expect("tag with v prefix", g("ok", tag="v4.167.0"), "is not MAJOR.MINOR.PATCH")

        log.write_text("")
        expect("tag below the first release is skipped (documented transition)", g("ok", tag="4.166.0", minv="4.167.0"), "skipped")
        if "run" in log.read_text():
            print("FAIL a skip must not run docker")
            failures.append("skip ran docker")

        expect("Secret wiring changed (oidcProvidersSecret)",
               g("ok", values=mut(lambda v: v.update(oidcProvidersSecret="other"))), "oidcProvidersSecret")
        expect("hook Secret no longer mounted",
               g("ok", values=mut(lambda v: v.update(envFromOptionalSecrets=[]))), "envFromOptionalSecrets")
        expect("a Secret key also set in the chart env",
               g("ok", values=mut(lambda v: v["env"].update(ZITADEL_HOOK_CUSTOMERS_ORG_ID="1"))), "set both")
        expect("wrong image repository",
               g("ok", values=mut(lambda v: v["image"].update(repository="ghcr.io/other/x"))), "image.repository")
    if failures:
        print(f"\nselftest FAILED: {failures}", file=sys.stderr)
        return 1
    print("\nselftest ok")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--image-tag", help="local proofs only: use this tag instead of the pinned one")
    ap.add_argument("--min-version", default=MIN_CHECKER_VERSION, help="local proofs only")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    try:
        guard(load_values(), FIXTURE, a.image_tag, a.min_version)
    except Refuse as e:
        print(f"::error title=mctl-api config guard::{e}")
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
