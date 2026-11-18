#!/usr/bin/env python3
"""The mctl-api control-caller wiring (C2 kill switch client), dark and lit.

Pins, on the bootstrap render:
  - dark (committed values): none of the wiring renders (no ExternalSecret,
    no C2 env, no sidecar, no extra volumes) and the Application values equal
    the same chart with the wiring templates stripped;
  - each inconsistent switch combination fails the render with its message;
  - lit: the Application values carry the URL, the token file, the sidecar with
    its secret refs, the 0444 key mount, a read-only token mount in the main
    container, and the ExternalSecret reads exactly user_id, key_id, key from
    one Vault path through the namespaced SecretStore mctl-api-control-vault
    (role eso-mctl-api-control, own ServiceAccount, automount off), never a
    ClusterSecretStore;
  - the kill switch flag appears only with killSwitch.

Run: python3 tests/test_api_c2_control_render.py   (needs helm)
"""
import importlib.util
import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHART = ROOT / "platform-gitops" / "bootstrap"
VALUES = CHART / "values.yaml"
LIT = ["--set", "apiC2Control.enabled=true", "--set", "apiC2Control.chartSlots=true",
       "--set", "apiC2Control.refresherImage.tag=1.2.3",
       "--set", "apiC2Control.refresherImage.command={/refresher,control}"]

failures: list[str] = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def helm(*extra):
    return subprocess.run(["helm", "template", "t", str(CHART), "-f", str(VALUES), *extra],
                          capture_output=True, text=True)


def docs(out):
    return [d for d in yaml.safe_load_all(out) if d]


def api_values(out):
    for d in docs(out):
        if d["metadata"].get("name") == "admins-mctl-api" and d["kind"] == "Application":
            return yaml.safe_load(d["spec"]["sources"][0]["helm"]["values"])
    raise SystemExit("admins-mctl-api Application not rendered")


def secret(out):
    return [d for d in docs(out) if d["kind"] == "ExternalSecret"
            and d["metadata"]["name"] == "mctl-api-c2-control-caller"]


def kind_named(out, kind, name):
    return [d for d in docs(out) if d["kind"] == kind and d["metadata"]["name"] == name]


def refused(args, needle):
    r = helm(*args)
    check(r.returncode != 0 and needle in r.stderr, f"{args}: expected failure containing {needle!r}, "
          f"got rc={r.returncode} {r.stderr[-200:]!r}")


def gate_module():
    spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TEMPLATE = "platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml"


def gate_reads_tag(gate, text, label):
    """The release gate's own reader must still see a string image.tag (UNKNOWN = gate blocked)."""
    try:
        img = gate.block_values(text).get("image")
        ok = isinstance(img, dict) and isinstance(img.get("tag"), str)
    except Exception as exc:  # any failure is the gate answering UNKNOWN
        check(False, f"{label}: release gate cannot read image.tag: {type(exc).__name__}: {exc}")
        return
    check(ok, f"{label}: release gate cannot read image.tag")


def gate_regression():
    """The gate parses the raw template (Go lines stripped), so the sidecar block is always
    in what it parses; it also parses the rendered values of both switch states. An inline
    directive left outside quotes made the sidecar `command` a dict used as a key (unhashable)."""
    gate = gate_module()
    gate_reads_tag(gate, (ROOT / TEMPLATE).read_text(), "raw template")
    for label, args in (("rendered OFF", []), ("rendered ON", LIT)):
        out = helm(*args)
        if out.returncode != 0:
            check(False, f"{label}: render failed: {out.stderr[-200:]}")
            continue
        for d in docs(out.stdout):
            if d["kind"] == "Application" and d["metadata"].get("name") == "admins-mctl-api":
                vals = d["spec"]["sources"][0]["helm"]["values"]
                wrapped = "      values: |\n" + "".join("        " + ln + "\n" for ln in vals.splitlines())
                gate_reads_tag(gate, wrapped, label)
                break
        else:
            check(False, f"{label}: admins-mctl-api Application not rendered")


def main():
    gate_regression()
    dark = helm()
    check(dark.returncode == 0, f"dark render failed: {dark.stderr[-300:]}")
    v = api_values(dark.stdout)
    env = v["env"]
    check(not secret(dark.stdout), "dark: the control-caller ExternalSecret rendered")
    check(not kind_named(dark.stdout, "SecretStore", "mctl-api-control-vault"), "dark: the isolated store rendered")
    check(not kind_named(dark.stdout, "ServiceAccount", "mctl-api-control-eso"), "dark: the control SA rendered")
    for k in ("GLOVO_C2_CONTROL_URL", "GLOVO_C2_CONTROL_TOKEN_FILE", "GLOVO_C2_KILLSWITCH_ENABLED"):
        check(k not in env, f"dark: {k} rendered")
    for k in ("extraContainers", "extraVolumes", "extraVolumeMounts"):
        check(k not in v, f"dark: {k} rendered")

    refused(["--set", "apiC2Control.killSwitch=true"], "killSwitch requires apiC2Control.enabled")
    refused(["--set", "apiC2Control.enabled=true"], "chartSlots")
    refused(["--set", "apiC2Control.enabled=true", "--set", "apiC2Control.chartSlots=true"], "placeholder")
    refused(["--set", "apiC2Control.enabled=true", "--set", "apiC2Control.chartSlots=true",
             "--set", "apiC2Control.refresherImage.tag=1.2.3"], "refresherImage.command")

    lit = helm(*LIT)
    check(lit.returncode == 0, f"lit render failed: {lit.stderr[-300:]}")
    if lit.returncode == 0:
        v = api_values(lit.stdout)
        env = v["env"]
        check(env.get("GLOVO_C2_CONTROL_URL") == "http://mctl-glovo.mctl-glovo.svc:8080", "lit: control URL")
        check(env.get("GLOVO_C2_CONTROL_TOKEN_FILE") == "/var/run/secrets/c2-control/token", "lit: token file")
        check("GLOVO_C2_KILLSWITCH_ENABLED" not in env, "lit without killSwitch: the route flag rendered")
        sc = v["extraContainers"][0]
        check(sc["image"] == "ghcr.io/mctlhq/mctl-glovo:1.2.3", "lit: sidecar image")
        check(sc["command"] == ["/refresher", "control"], "lit: sidecar command")
        envs = {e["name"]: e for e in sc["env"]}
        check(envs["TOKEN_FILE"]["value"] == env["GLOVO_C2_CONTROL_TOKEN_FILE"],
              "lit: the sidecar writes where mctl-api reads")
        check(envs["ZITADEL_USER_ID"]["valueFrom"]["secretKeyRef"]["name"] == "mctl-api-c2-control-caller",
              "lit: user id comes from the control-caller Secret")
        check(envs["ZITADEL_SCOPE"]["valueFrom"]["configMapKeyRef"]["key"] == "control_scope",
              "lit: scope comes from the ids ConfigMap")
        check(sc["securityContext"]["readOnlyRootFilesystem"] is True
              and sc["securityContext"]["capabilities"]["drop"] == ["ALL"], "lit: sidecar hardening")
        ssc = sc["securityContext"]
        check(ssc.get("runAsNonRoot") is True and ssc.get("runAsUser") == 1000
              and ssc.get("allowPrivilegeEscalation") is False
              and ssc.get("seccompProfile") == {"type": "RuntimeDefault"},
              "lit: sidecar securityContext must satisfy PSA restricted "
              "(runAsNonRoot, numeric runAsUser, no privilege escalation, seccomp RuntimeDefault)")
        mounts = [m["name"] for m in v["extraVolumeMounts"]]
        check(mounts == ["c2-control-token"],
              "lit: the main container mounts only the token volume, never the key")
        vols = {x["name"]: x for x in v["extraVolumes"]}
        check(vols["c2-control-key"]["secret"]["secretName"] == "mctl-api-c2-control-caller", "lit: key volume")
        check(vols["c2-control-key"]["secret"]["defaultMode"] == 0o444,
              "lit: key file mode must be 0444 (the chart sets no fsGroup, the sidecar is not root)")
        check(vols["c2-control-token"]["emptyDir"]["medium"] == "Memory", "lit: token volume is memory")
        check(v["extraVolumeMounts"] == [{"name": "c2-control-token", "mountPath": "/var/run/secrets/c2-control",
                                          "readOnly": True}], "lit: main container mounts the token read-only")
        es = secret(lit.stdout)
        check(len(es) == 1, "lit: exactly one control-caller ExternalSecret")
        if es:
            data = es[0]["spec"]["data"]
            check([d["secretKey"] for d in data] == ["user_id", "key_id", "key"], "lit: ExternalSecret fields")
            check({d["remoteRef"]["key"] for d in data} == {"platform/mctl-glovo/control-caller"},
                  "lit: one bare Vault path")
            ref = es[0]["spec"]["secretStoreRef"]
            check(ref == {"kind": "SecretStore", "name": "mctl-api-control-vault"},
                  f"lit: the ExternalSecret must read through the isolated namespaced store, got {ref}")
        # The isolated store: namespaced, own role, own ServiceAccount (ESO token requests only).
        stores = kind_named(lit.stdout, "SecretStore", "mctl-api-control-vault")
        check(len(stores) == 1, "lit: exactly one SecretStore mctl-api-control-vault")
        sas = kind_named(lit.stdout, "ServiceAccount", "mctl-api-control-eso")
        check(len(sas) == 1, "lit: exactly one ServiceAccount mctl-api-control-eso")
        if stores:
            check(stores[0]["metadata"]["namespace"] == "mctl-api", "lit: store namespace")
            vault = stores[0]["spec"]["provider"]["vault"]["auth"]["kubernetes"]
            check(vault["role"] == "eso-mctl-api-control", f"lit: store role {vault['role']}")
            check(vault["serviceAccountRef"] == {"name": "mctl-api-control-eso"}, "lit: store service account")
        if sas:
            check(sas[0]["metadata"]["namespace"] == "mctl-api", "lit: service account namespace")
            check(sas[0].get("automountServiceAccountToken") is False, "lit: service account must not automount")
        check(not [d for d in docs(lit.stdout) if d["kind"] == "ClusterSecretStore"
                   and "control" in d["metadata"].get("name", "")], "lit: no ClusterSecretStore for the key")
        # Nothing in the lit render may point an ExternalSecret that reads the prefix at a cluster store.
        for d in docs(lit.stdout):
            if d["kind"] == "ExternalSecret" and "platform/mctl-glovo" in str(d["spec"].get("data")):
                check(d["spec"]["secretStoreRef"].get("kind") == "SecretStore",
                      f"lit: {d['metadata']['name']} reads the prefix through a cluster store")

    on = helm(*LIT, "--set", "apiC2Control.killSwitch=true")
    check(on.returncode == 0 and api_values(on.stdout)["env"].get("GLOVO_C2_KILLSWITCH_ENABLED") == "true",
          "killSwitch: the route flag is missing")

    if failures:
        print("\n".join("FAIL " + f for f in failures), file=sys.stderr)
        return 1
    print("ok: api control-caller render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
