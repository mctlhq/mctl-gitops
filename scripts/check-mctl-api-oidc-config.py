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
mctlhq/mctl-api#1108) is skipped with a visible ::warning, after one static
legacy rule: such a tag is refused if the rendered config has service_subjects. The decision comes
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
import urllib.parse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT / "platform-gitops/bootstrap"  # renders templates/mctl-platform/mctl-api.yaml
FIXTURE = ROOT / "platform-gitops/helm-charts/zitadel-iac/iac/tests/fixtures/mctl-api-config-check.json"
IMAGE_REPO = "ghcr.io/mctlhq/mctl-api"

# First mctl-api release with `--check-config` (mctlhq/mctl-api#1108, released
# in 4.169.0 together with #1111 and #1110). Until the pin reaches it the check
# is skipped, loudly, after the static legacy rule. 4.167.0 and 4.168.0 shipped
# without the flag (no cmd/api/check_config.go at either tag), so MIN must stay
# above 4.168.0: tests/test_mctl_api_guard_branches.py pins that and runs both
# branches at this value. A MIN at or below a deployed flagless build makes
# validate red repo-wide (fail-closed deadlock). If 4.169.0 were ever burned by a
# release without the flag, raise MIN here before relying on it.
MIN_CHECKER_VERSION = "4.169.0"

OK_LINE = "mctl-api check-config: ok"
RUN_TIMEOUT = 90
# Stage 2 (--readyz): boot the candidate against a throwaway Postgres and read
# /readyz. Images are pinned by tag; the stage needs a Linux docker daemon.
PG_IMAGE = "postgres:16-alpine"
PROBE_IMAGE = "curlimages/curl:8.11.1"
READYZ_DEADLINE = 120  # seconds until /readyz must have answered
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
CONSENT_SECRET = "mctl-api-glovo-consent"
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
    # The consent reader identity comes from the optional Secret
    # mctl-api-glovo-consent (Vault), never from the chart env. When the chart
    # lights the consent routes, stand that Secret in with the one service
    # identity the fixture lists (the reader, F12): provider = its entry,
    # subject = its subject. No service identity in the fixture is a refusal,
    # never a skip: the image would reject the config in production too.
    if env.get("GLOVO_CONSENT_ENABLED") is not None:
        if CONSENT_SECRET not in (values.get("envFromOptionalSecrets") or []):
            raise Refuse(f"GLOVO_CONSENT_ENABLED is set but envFromOptionalSecrets does not list {CONSENT_SECRET}")
        readers = [(e.get("name"), subj) for e in fixture["MCTL_OIDC_PROVIDERS"] for subj in (e.get("service_subjects") or {})]
        if len(readers) != 1:
            raise Refuse(f"the fixture must list exactly one service identity for the consent reader, found {len(readers)}")
        secret_keys["GLOVO_CONSENT_SERVICE_PROVIDER"], secret_keys["GLOVO_CONSENT_SERVICE_SUBJECT"] = readers[0]
    for k, v in {**secret_keys, **PLACEHOLDERS}.items():
        if k in env:
            raise Refuse(f"{k} is set both in the chart env and by a Secret; the chart refuses that, and so does the guard")
        env[k] = v
    return env


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def check_image(image, env, docker="docker"):
    if shutil.which(docker) is None:
        raise Refuse(f"RUNNER PROBLEM, not a config rejection: {docker} not found, cannot run {image}")
    have = run([docker, "image", "inspect", image])
    if have.returncode != 0:
        for attempt in range(1, PULL_ATTEMPTS + 1):
            pulled = run([docker, "pull", image])
            if pulled.returncode == 0:
                break
            print(f"docker pull {image} failed (attempt {attempt}/{PULL_ATTEMPTS}): {pulled.stderr.strip()[-300:]}", file=sys.stderr)
            if attempt == PULL_ATTEMPTS:
                raise Refuse(f"REGISTRY/PULL PROBLEM, not a config rejection: could not pull {image} after {PULL_ATTEMPTS} attempts; the configuration was NOT evaluated and unknown is not ok. Rerun the job; there is no skip switch")
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
        raise Refuse(f"CONFIG REJECTED by the image (not a registry problem), or the image does not implement --check-config (exit {res.returncode}):\n{out[-1500:]}")
    if not lines or lines[-1].strip() != OK_LINE:
        raise Refuse(f"{image} exited 0 without the line {OK_LINE!r}: it does not implement --check-config, so nothing was validated")


def parse_readyz(code, body):
    """Classify one /readyz answer. ("ok", why) only when the body parses and
    checks.stores is "ok" with no failed_stores; ("fail", why) for a store that
    did not init or a stores check that is not reporting; ("retry", why) for
    anything that is not yet an answer (refused, non-JSON, other status). Other
    probes (gitops_sync, vault, temporal) are deliberately not judged: the
    throwaway has none of them. HTTP serves only after every store init has
    finished (cmd/api/main.go), so the first parsed answer is final."""
    if code not in ("200", "503"):
        return "retry", f"HTTP {code or 'none'}"
    try:
        doc = json.loads(body)
    except ValueError:
        return "retry", "body is not JSON"
    checks = doc.get("checks") if isinstance(doc, dict) else None
    if not isinstance(checks, dict):
        return "retry", "body has no checks object"
    failed = doc.get("failed_stores")
    if failed:
        return "fail", f"stores failed to init: {failed}"
    stores = checks.get("stores")
    if stores == "ok":
        return "ok", "stores ok"
    return "fail", f"checks.stores is {stores!r}, not 'ok' (store init not observable is not ok)"


def check_stores(image, env, docker="docker", deadline=READYZ_DEADLINE):
    """Stage 2: the config check never opens a store, so a boot-time store-init
    failure (mctl-api#1136: a cancelled init context failed the consent store
    only when the chart lit it) passed it and showed in production only
    (mctl-gitops#2827 / #2830). Start the image with the same rendered env plus
    a throwaway Postgres on an internal network (no route out), and require
    /readyz to report stores ok. Could not observe is a failure of the check."""
    if shutil.which(docker) is None:
        raise Refuse(f"RUNNER PROBLEM, not a config rejection: {docker} not found, cannot boot {image}")
    import time
    tag = f"{os.getpid()}"
    net, pg, api = f"mctl-api-readyz-net-{tag}", f"mctl-api-readyz-pg-{tag}", f"mctl-api-readyz-{tag}"
    port = env.get("PORT", "8080")
    pw = "throwaway-not-a-secret"
    for img in (PG_IMAGE, PROBE_IMAGE):
        if run([docker, "image", "inspect", img]).returncode != 0:
            for attempt in range(1, PULL_ATTEMPTS + 1):
                if run([docker, "pull", img]).returncode == 0:
                    break
                if attempt == PULL_ATTEMPTS:
                    raise Refuse(f"REGISTRY/PULL PROBLEM, not a config rejection: could not pull {img}; /readyz was NOT observed and unknown is not ok. Rerun the job")
                time.sleep(float(os.environ.get("CHECK_PULL_DELAY", "10")) * attempt)
    # Every *_DB_URL of the rendered env (they carry $(DB_USER)-style Secret
    # references and point at shared-pg) is redirected to the throwaway server,
    # keeping each database name; the superuser stands in for every role. A
    # chart without AUDIT_DB_URL would leave the stores unconfigured, which is
    # not the same as healthy, so that is a refusal.
    if "ALLOW_INSECURE_DB" in env:
        raise Refuse("ALLOW_INSECURE_DB is set in the chart env; the readyz stage sets it only for its own throwaway database")
    if not str(env.get("AUDIT_DB_URL", "")).startswith(("postgres://", "postgresql://")):
        raise Refuse("AUDIT_DB_URL is missing or not a postgres URL in the rendered env: the stores would be unconfigured and /readyz would say nothing")
    renv, dbnames = dict(env), set()
    for k, v in env.items():
        if k.endswith("_DB_URL") and str(v).startswith(("postgres://", "postgresql://")):
            name = urllib.parse.unquote(urllib.parse.urlsplit(v).path.lstrip("/"))
            if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise Refuse(f"{k} names a database {name!r} the stage cannot create safely")
            dbnames.add(name)
            renv[k] = f"postgres://postgres:{pw}@{pg}:5432/{name}?sslmode=disable"
    renv["ALLOW_INSECURE_DB"] = "true"  # EnforceTLS would demand TLS from the throwaway
    try:
        with tempfile.TemporaryDirectory() as d:
            envfile = Path(d) / "env"
            envfile.write_text("".join(f"{k}={v}\n" for k, v in sorted(renv.items())))
            if run([docker, "network", "create", "--internal", net]).returncode != 0:
                raise Refuse("RUNNER PROBLEM: could not create the internal docker network; /readyz was NOT observed")
            r = run([docker, "run", "-d", "--name", pg, "--network", net, "-e", f"POSTGRES_PASSWORD={pw}", PG_IMAGE])
            if r.returncode != 0:
                raise Refuse(f"RUNNER PROBLEM: throwaway Postgres did not start: {r.stderr.strip()[-300:]}")
            t0 = time.time()
            while run([docker, "exec", pg, "pg_isready", "-U", "postgres"]).returncode != 0:
                if time.time() - t0 > 60:
                    raise Refuse("RUNNER PROBLEM: throwaway Postgres never became ready; /readyz was NOT observed")
                time.sleep(1)
            for name in sorted(dbnames - {"postgres"}):
                if run([docker, "exec", pg, "psql", "-U", "postgres", "-c", f'CREATE DATABASE "{name}"']).returncode != 0:
                    raise Refuse(f"RUNNER PROBLEM: could not create database {name!r} in the throwaway Postgres")
            r = run([docker, "run", "-d", "--name", api, "--network", net, "--read-only", "--tmpfs", "/tmp:rw,mode=1777", "--tmpfs", "/data:rw,mode=1777",
                     "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--env-file", str(envfile), image])
            if r.returncode != 0:
                raise Refuse(f"RUNNER PROBLEM: {image} did not start: {r.stderr.strip()[-300:]}")
            t0, last = time.time(), "no answer yet"
            while time.time() - t0 < deadline:
                st = run([docker, "inspect", "-f", "{{.State.Running}}", api])
                if st.stdout.strip() != "true":
                    logs = run([docker, "logs", "--tail", "40", api])
                    raise Refuse(f"READYZ STAGE: {image} exited before answering /readyz (a boot failure with the rendered env):\n"
                                 f"{(logs.stdout + logs.stderr).strip()[-1500:]}")
                res = run([docker, "run", "--rm", "--network", net, PROBE_IMAGE, "-s", "-m", "3", "-w", "\n%{http_code}",
                           f"http://{api}:{port}/readyz"])
                body, _, code = res.stdout.rpartition("\n")
                verdict, why = parse_readyz(code.strip(), body)
                if verdict == "ok":
                    return
                if verdict == "fail":
                    logs = run([docker, "logs", "--tail", "40", api])
                    raise Refuse(f"READYZ STAGE: {image} reports {why}. This is what production would show. Boot log tail:\n{(logs.stdout + logs.stderr).strip()[-1500:]}")
                last = why
                time.sleep(1)
            raise Refuse(f"READYZ STAGE: no usable /readyz answer from {image} in {deadline}s (last: {last}); not observed is not ok")
    finally:
        for c in (api, pg):
            run([docker, "rm", "-f", c])
        run([docker, "network", "rm", net])


def legacy_rule(fixture_path, tag, min_version):
    """Static rule for tags below MIN_CHECKER_VERSION: refuse any
    MCTL_OIDC_PROVIDERS entry that carries service_subjects. An unreadable or
    malformed fixture is a refusal, never a pass: unknown is not ok. Delete this
    (and its tests) once MIN_CHECKER_VERSION is two releases old."""
    try:
        providers = json.loads(Path(fixture_path).read_text())["MCTL_OIDC_PROVIDERS"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Refuse(f"LEGACY RULE: cannot read MCTL_OIDC_PROVIDERS from the fixture ({type(e).__name__}); "
                     f"mctl-api {tag} is below {min_version} and cannot validate it itself, so nothing was checked")
    if not isinstance(providers, list) or not all(isinstance(p, dict) for p in providers):
        raise Refuse(f"LEGACY RULE: MCTL_OIDC_PROVIDERS in the fixture is not a list of objects; nothing was checked for mctl-api {tag}")
    for p in providers:
        if "service_subjects" in p:
            raise Refuse(f"LEGACY RULE: provider {p.get('name')!r} has service_subjects, and mctl-api {tag} is below "
                         f"{min_version} (releases from 4.165.0 refuse it next to customers_org_id and crash-loop at start; "
                         f"older ones are unproven). Roll the config back first, or move the pin to {min_version} or later")


def guard(values, fixture_path, tag_override=None, min_version=MIN_CHECKER_VERSION, docker="docker", readyz=False):
    tag = tag_override or (values.get("image") or {}).get("tag")
    if (values.get("image") or {}).get("repository") != IMAGE_REPO:
        raise Refuse(f"image.repository is not {IMAGE_REPO}")
    if semver(tag, "image.tag") < semver(min_version, "MIN_CHECKER_VERSION"):
        # The image cannot run --check-config, but one rule is known statically:
        # every release from 4.165.0 refuses service_subjects next to
        # customers_org_id (the 4.166.0 incident), and older ones are unproven.
        # So a tag below MIN may never be paired with a config that has
        # service_subjects. Without this, the skip lets an old pin (or a
        # rollback bump) meet the very config that crash-loops it.
        legacy_rule(fixture_path, tag, min_version)
        print(f"::warning title=mctl-api config guard SKIPPED::pinned mctl-api {tag} predates "
              f"--check-config (first in {min_version}). The rendered MCTL_OIDC_PROVIDERS was NOT run through "
              f"mctl-api's validator; only the static legacy rule (no service_subjects below {min_version}) "
              f"was applied and passed. This skip ends when the pin reaches {min_version}.")
        return "skipped"
    fixture = json.loads(fixture_path.read_text())
    env = build_env(values, fixture)
    check_image(f"{IMAGE_REPO}:{tag}", env, docker)
    print(f"{IMAGE_REPO}:{tag} accepted the rendered configuration ({OK_LINE})")
    if readyz:
        check_stores(f"{IMAGE_REPO}:{tag}", env, docker)
        print(f"{IMAGE_REPO}:{tag} booted on the rendered configuration and /readyz reports stores ok")
    return "ok"


# ---------------------------------------------------------------- selftest
FAKE_DOCKER = r"""#!/bin/sh
# Stub docker: behaviour chosen by $FAKE_MODE (config stage) and $FAKE_READYZ
# (readyz stage); logs calls to $FAKE_LOG.
echo "$*" >> "$FAKE_LOG"
case "$1" in
  image) [ "$FAKE_MODE" != pull_fails ] && [ "$FAKE_MODE" != pull_fails_inspect ] ; exit $? ;;
  pull) exit 1 ;;
  rm|network) exit 0 ;;
  exec) [ "$FAKE_READYZ" != pg_down ]; exit $? ;;
  logs) echo "boot log line"; exit 0 ;;
  inspect) if [ "$FAKE_READYZ" = exited ]; then echo false; else echo true; fi; exit 0 ;;
  run)
    case "$*" in
      *curlimages*)
        case "$FAKE_READYZ" in
          ok) printf '{"status":"ready","checks":{"stores":"ok"}}\n200' ;;
          ok503) printf '{"status":"not ready","checks":{"stores":"ok","gitops_sync":"never_synced"}}\n503' ;;
          store_failed) printf '{"status":"not ready","checks":{"stores":"init_failed"},"failed_stores":["glovo link consent"]}\n503' ;;
          failed_no_marker) printf '{"status":"not ready","checks":{"stores":"ok"},"failed_stores":["x"]}\n503' ;;
          not_configured) printf '{"status":"ready","checks":{"stores":"not_configured"}}\n200' ;;
          malformed) printf 'not json\n200' ;;
          refused) printf '\n000'; exit 7 ;;
          late_ok) n=$(cat "$FAKE_LOG.n" 2>/dev/null || echo 0); echo $((n+1)) > "$FAKE_LOG.n"
                   if [ "$n" -lt 2 ]; then printf '\n000'; exit 7; fi
                   printf '{"status":"ready","checks":{"stores":"ok"}}\n200' ;;
        esac; exit 0 ;;
      *postgres:*) exit 0 ;;
      *--check-config*)
        case "$FAKE_MODE" in
          ok) echo "mctl-api check-config: ok"; exit 0 ;;
          refuse) echo "mctl-api check-config: invalid configuration: boom" >&2; exit 1 ;;
          old_image) echo '{"msg":"server started"}'; exit 0 ;;
          ok_text_in_middle) echo "mctl-api check-config: ok"; echo "later"; exit 0 ;;
        esac ;;
      *) exit 0 ;;
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
        expect("image refuses the configuration", g("refuse"), "CONFIG REJECTED by the image")
        expect("image without the flag (boots, exit 0, no ok line)", g("old_image"), "does not implement --check-config")
        expect("ok line not last (output not trusted)", g("ok_text_in_middle"), "does not implement --check-config")
        expect("pull fails every attempt (named as a registry/pull problem)", g("pull_fails"), "REGISTRY/PULL PROBLEM, not a config rejection")
        expect("docker missing", lambda: check_image("x:1", {}, docker="/nonexistent/docker"), "not found")
        expect("tag unparsable", g("ok", tag="latest"), "is not MAJOR.MINOR.PATCH")
        expect("tag with v prefix", g("ok", tag="v4.167.0"), "is not MAJOR.MINOR.PATCH")

        # The real fixture lists the consent reader under service_subjects, so the skip
        # branch is proven on a copy without it, and the real one must be refused.
        stripped = json.loads(FIXTURE.read_text())
        for p_ in stripped["MCTL_OIDC_PROVIDERS"]:
            p_.pop("service_subjects", None)
        clean = d / "clean.json"
        clean.write_text(json.dumps(stripped))
        os.environ["FAKE_MODE"] = "ok"
        log.write_text("")
        expect("tag below the first release is skipped (documented transition)",
               lambda: guard(copy.deepcopy(base), clean, tag_override="4.166.0", min_version="4.167.0", docker=dk), "skipped")
        if "run" in log.read_text():
            print("FAIL a skip must not run docker")
            failures.append("skip ran docker")

        expect("tag below the first release with the REAL fixture (service_subjects): refused by the legacy rule",
               lambda: guard(copy.deepcopy(base), FIXTURE, tag_override="4.166.0", min_version="4.167.0", docker=dk), "LEGACY RULE")

        bad = d / "bad.json"
        bad.write_text(json.dumps({"MCTL_OIDC_PROVIDERS": [{"name": "zitadel", "customers_org_id": "3", "service_subjects": {"1": "2"}}]}))
        junk = d / "junk.json"
        junk.write_text("{not json")
        below = lambda fx, tag="4.166.0": (lambda: guard(copy.deepcopy(base), fx, tag_override=tag, min_version="4.167.0", docker=dk))
        os.environ["FAKE_MODE"] = "ok"
        expect("below MIN + service_subjects: refused by the legacy rule", below(bad), "LEGACY RULE")
        expect("below MIN (3.0.0) + service_subjects: refused", below(bad, "3.0.0"), "LEGACY RULE")
        expect("below MIN + unreadable fixture: refused, not skipped", below(junk), "LEGACY RULE")
        expect("below MIN + missing fixture: refused, not skipped", below(d / "absent.json"), "LEGACY RULE")
        expect("at MIN + service_subjects: reaches the image (legacy rule does not apply)",
               below(bad, "4.167.0"), "ok")

        expect("Secret wiring changed (oidcProvidersSecret)",
               g("ok", values=mut(lambda v: v.update(oidcProvidersSecret="other"))), "oidcProvidersSecret")
        expect("hook Secret no longer mounted",
               g("ok", values=mut(lambda v: v.update(envFromOptionalSecrets=[]))), "envFromOptionalSecrets")
        expect("a Secret key also set in the chart env",
               g("ok", values=mut(lambda v: v["env"].update(ZITADEL_HOOK_CUSTOMERS_ORG_ID="1"))), "set both")
        # Consent reader stand-in (apiConsent on): the real rendered env gets the
        # fixture's service identity; each way to lose it is a refusal.
        def consent_on(v):
            v["env"].update(GLOVO_CONSENT_ENABLED="true", GLOVO_C2_CAPACITY="1")
            v["envFromOptionalSecrets"] = list(v.get("envFromOptionalSecrets") or []) + [CONSENT_SECRET]
        fx = json.loads(FIXTURE.read_text())
        cenv = build_env(mut(consent_on), fx)
        assert cenv["GLOVO_CONSENT_SERVICE_PROVIDER"] == "zitadel" and cenv["GLOVO_CONSENT_SERVICE_SUBJECT"] in fx["MCTL_OIDC_PROVIDERS"][0]["service_subjects"], "reader not taken from the fixture"
        off = build_env(mut(lambda v: (v["env"].pop("GLOVO_CONSENT_ENABLED", None), v["env"].pop("GLOVO_C2_CAPACITY", None))), fx)
        assert "GLOVO_CONSENT_SERVICE_PROVIDER" not in off, "reader keys must not appear while the consent routes are off"
        expect("consent on: reader taken from the fixture", g("ok", values=mut(consent_on)), "ok")
        expect("consent on, Secret not mounted",
               g("ok", values=mut(lambda v: (consent_on(v), v.update(envFromOptionalSecrets=[HOOK_SECRET])))), "does not list")
        expect("consent on, reader also set in the chart env",
               g("ok", values=mut(lambda v: (consent_on(v), v["env"].update(GLOVO_CONSENT_SERVICE_SUBJECT="1")))), "set both")
        nofx = d / "nofx.json"
        nofx.write_text(json.dumps({"MCTL_OIDC_PROVIDERS": [{"name": "zitadel"}]}))
        expect("consent on, fixture has no service identity",
               lambda: guard(mut(consent_on), nofx, tag_override="4.167.0", min_version="4.0.0", docker=dk), "exactly one service identity")
        # Stage 2: boot on a throwaway Postgres and read /readyz. Each way of not
        # seeing stores ok is a failure; only an observed ok passes.
        def gz(mode, deadline=3, values=None):
            os.environ["FAKE_MODE"] = "ok"
            os.environ["FAKE_READYZ"] = mode
            (Path(str(log) + ".n")).unlink(missing_ok=True)
            return lambda: check_stores("img:1", build_env(copy.deepcopy(values or base), json.loads(FIXTURE.read_text())), dk, deadline)

        def ok_(fn):
            return lambda: (fn(), "ok")[1]
        expect("readyz: stores ok", ok_(gz("ok")), "ok")
        expect("readyz: 503 for gitops_sync only is still stores ok (not judged here)", ok_(gz("ok503")), "ok")
        expect("readyz: slow start, refused then ok", ok_(gz("late_ok", deadline=30)), "ok")
        expect("readyz: a store failed init", gz("store_failed"), "reports stores failed to init")
        expect("readyz: failed_stores listed while stores says ok", gz("failed_no_marker"), "reports stores failed to init")
        expect("readyz: stores check not reporting", gz("not_configured"), "reports checks.stores")
        expect("readyz: never answers (refused) is a failure, not a pass", gz("refused", deadline=2), "not observed is not ok")
        expect("readyz: malformed body is a failure", gz("malformed", deadline=2), "not observed is not ok")
        expect("readyz: image exits before answering", gz("exited"), "exited before answering")
        expect("readyz: chart env sets ALLOW_INSECURE_DB itself",
               lambda: check_stores("img:1", {"ALLOW_INSECURE_DB": "true"}, dk, 2), "sets it only for its own")
        expect("readyz: rendered env has no AUDIT_DB_URL (stores would be unconfigured)",
               lambda: check_stores("img:1", {}, dk, 2), "AUDIT_DB_URL is missing")
        expect("readyz: docker missing", lambda: check_stores("x:1", {}, docker="/nonexistent/docker"), "not found")
        os.environ["FAKE_READYZ"] = "ok"
        os.environ["FAKE_MODE"] = "ok"
        expect("guard with readyz on a good input", lambda: guard(copy.deepcopy(base), FIXTURE, tag_override="4.167.0", min_version="4.0.0", docker=dk, readyz=True), "ok")
        os.environ["FAKE_READYZ"] = "store_failed"
        expect("guard with readyz: config accepted but a store failed init",
               lambda: guard(copy.deepcopy(base), FIXTURE, tag_override="4.167.0", min_version="4.0.0", docker=dk, readyz=True), "reports stores failed to init")
        os.environ["FAKE_READYZ"] = "ok"
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
    ap.add_argument("--readyz", action="store_true", help="also boot the image on a throwaway Postgres and require /readyz stores ok")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    try:
        guard(load_values(), FIXTURE, a.image_tag, a.min_version, readyz=a.readyz)
    except Refuse as e:
        print(f"::error title=mctl-api config guard::{e}")
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
