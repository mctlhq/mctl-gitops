"""k3s-preview kured and system-upgrade-controller: the user manifests must win
and follow kube.tf (#2036).

kube-hetzner bundles its own kured DaemonSet and system-upgrade-controller
Deployment, both without resources, and re-applies them whenever
terraform_data.kustomization is replaced. The real objects live in
infrastructure/k3s-preview/extra-manifests/, and the module re-applies a user
manifest only when its rendered content changes. The #2035 apply replaced the
base layer and kured silently lost its requests and limits.

K1. The module arguments that feed the base kustomization triggers read from
    `local.<same name>`, so a bump has exactly one place to go.
K2. base_kustomization_inputs hashes every one of those locals, so a change
    to any of them changes the rendered kured manifest.
K3. extra_kustomize_parameters passes base_kustomization_inputs,
    kured_version and sys_upgrade_controller_version into the user templates.
K4. kured.yaml.tpl renders the hash as an annotation and the image tag from
    kured_version, with no other placeholder. Rendering with a different
    value for either changes the output, and the rendered DaemonSet keeps
    its resources.
K5. system-upgrade-controller.yaml.tpl does the same for the Deployment, is
    listed in kustomization.yaml.tpl, and stays a COMPLETE Deployment: the
    module applied upstream's with `kubectl apply`, so a partial one would
    make kubectl's three-way merge delete the fields it leaves out.
K6. hetzner_csi_values replaces the module's default CSI values wholesale, so
    it must carry the default node affinity (control plane DoesNotExist,
    provided-by NotIn robot) and set resources for every chart container.

No pytest, matching the plain `python3 tests/<file>.py` convention.

Run: python3 tests/test_k3s_kured_single_owner.py
"""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
K3S = ROOT / "infrastructure/k3s-preview"
KUBE_TF = K3S / "kube.tf"
KURED_TPL = K3S / "extra-manifests/kured.yaml.tpl"
SUC_TPL = K3S / "extra-manifests/system-upgrade-controller.yaml.tpl"
KUSTOMIZATION_TPL = K3S / "extra-manifests/kustomization.yaml.tpl"

TRACKED = [
    "install_k3s_version",
    "hetzner_ccm_version",
    "hetzner_csi_version",
    "kured_version",
    "sys_upgrade_controller_version",
    "traefik_version",
    "cert_manager_version",
    "hetzner_ccm_merge_values",
    "hetzner_csi_values",
]

CSI_CONTAINERS = {
    "controller": ["csiAttacher", "csiResizer", "csiProvisioner", "livenessProbe", "hcloudCSIDriver"],
    "node": ["csiNodeDriverRegistrar", "livenessProbe", "hcloudCSIDriver"],
}

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def block(src: str, header_re: str) -> str:
    """Return the brace-balanced body that follows a header like `locals {`."""
    m = re.search(header_re, src, re.M)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1 : j]
    return ""


def render(tpl: str, params: dict[str, str]) -> str:
    """templatefile() for the subset the user templates use: ${name} only."""
    names = set(re.findall(r"\$\{([^}]*)\}", tpl))
    missing = names - params.keys()
    if missing:
        raise KeyError(f"template uses parameters nobody passes: {sorted(missing)}")
    return re.sub(r"\$\{([^}]*)\}", lambda m: params[m.group(1)], tpl)


def main() -> int:
    tf = KUBE_TF.read_text()
    module = block(tf, r'^module "kube-hetzner" \{')
    check(bool(module), "kube.tf: module \"kube-hetzner\" block not found")
    locals_bodies = [block(tf[m.start():], r"^locals \{") for m in re.finditer(r"^locals \{", tf, re.M)]
    locals_src = "\n".join(locals_bodies)

    # K1 (top-level module arguments only, not keys inside nested maps)
    params_body = block(module, r"^\s*extra_kustomize_parameters\s*=\s*\{")
    top_level = module.replace(params_body, "") if params_body else module
    for name in TRACKED:
        args = re.findall(rf"^\s*{name}\s*=\s*(.+)$", top_level, re.M)
        check(args == [f"local.{name}"], f"K1: module argument {name} must be exactly `local.{name}`, got {args}")
        check(re.search(rf"^\s*{name}\s*=", locals_src, re.M) is not None, f"K1: local.{name} is not defined")

    # K2
    hash_body = re.search(r"base_kustomization_inputs\s*=\s*sha1\(jsonencode\(\[(.*?)\]\)\)", locals_src, re.S)
    check(hash_body is not None, "K2: base_kustomization_inputs = sha1(jsonencode([...])) not found")
    if hash_body:
        hashed = set(re.findall(r"local\.(\w+)", hash_body.group(1)))
        for name in TRACKED:
            check(name in hashed, f"K2: base_kustomization_inputs does not hash local.{name}")

    # K3
    for name in ("base_kustomization_inputs", "kured_version", "sys_upgrade_controller_version"):
        check(
            re.search(rf"^\s*{name}\s*=\s*local\.{name}\s*$", params_body, re.M) is not None,
            f"K3: extra_kustomize_parameters must pass {name} = local.{name}",
        )

    # K4
    tpl = KURED_TPL.read_text()
    params = {"base_kustomization_inputs": "a" * 40, "kured_version": "1.21.0"}
    try:
        out = render(tpl, params)
    except KeyError as e:
        failures.append(f"K4: {e}")
        out = ""
    if out:
        ds = [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "DaemonSet"]
        check(len(ds) == 1, f"K4: expected one DaemonSet, found {len(ds)}")
        if ds:
            d = ds[0]
            ann = (d["metadata"].get("annotations") or {}).get("mctl.ai/base-kustomization-inputs")
            check(ann == params["base_kustomization_inputs"], f"K4: hash annotation renders as {ann!r}")
            c = d["spec"]["template"]["spec"]["containers"][0]
            check(c["image"] == "ghcr.io/kubereboot/kured:1.21.0", f"K4: image renders as {c['image']!r}")
            res = c.get("resources") or {}
            check(bool(res.get("requests")) and bool(res.get("limits")), "K4: rendered kured lost its resources")
        for key, other in (("base_kustomization_inputs", "b" * 40), ("kured_version", "9.9.9")):
            check(render(tpl, {**params, key: other}) != out, f"K4: changing {key} does not change the rendered manifest")

    # K5
    tpl = SUC_TPL.read_text()
    params = {"base_kustomization_inputs": "a" * 40, "sys_upgrade_controller_version": "v0.18.0"}
    try:
        out = render(tpl, params)
    except KeyError as e:
        failures.append(f"K5: {e}")
        out = ""
    if out:
        docs = [d for d in yaml.safe_load_all(out) if d]
        check(
            [(d.get("kind"), d["metadata"].get("name")) for d in docs] == [("Deployment", "system-upgrade-controller")],
            f"K5: expected exactly the system-upgrade-controller Deployment, found {[d.get('kind') for d in docs]}",
        )
        if docs:
            d = docs[0]
            ann = (d["metadata"].get("annotations") or {}).get("mctl.ai/base-kustomization-inputs")
            check(ann == params["base_kustomization_inputs"], f"K5: hash annotation renders as {ann!r}")
            spec = d.get("spec") or {}
            pod = (spec.get("template") or {}).get("spec") or {}
            check(bool(spec.get("selector")) and bool(spec.get("strategy")), "K5: Deployment lost its selector or strategy")
            for field in ("affinity", "tolerations", "volumes", "serviceAccountName"):
                check(bool(pod.get(field)), f"K5: pod spec lost {field}; a partial Deployment strips live fields")
            vols = [v["name"] for v in pod.get("volumes") or []]
            check(vols[:1] == ["ca-certificates"], f"K5: the module's ca-certificates volume must come first, got {vols}")
            c = (pod.get("containers") or [{}])[0]
            check(c.get("image") == "rancher/system-upgrade-controller:v0.18.0", f"K5: image renders as {c.get('image')!r}")
            for field in ("env", "envFrom", "securityContext", "volumeMounts"):
                check(bool(c.get(field)), f"K5: container lost {field}; a partial Deployment strips live fields")
            res = c.get("resources") or {}
            check(bool(res.get("requests")) and bool(res.get("limits")), "K5: rendered Deployment lost its resources")
        for key, other in (("base_kustomization_inputs", "b" * 40), ("sys_upgrade_controller_version", "v9.9.9")):
            check(render(tpl, {**params, key: other}) != out, f"K5: changing {key} does not change the rendered manifest")
    listed = (yaml.safe_load(KUSTOMIZATION_TPL.read_text()) or {}).get("resources") or []
    check("system-upgrade-controller.yaml" in listed, "K5: kustomization.yaml.tpl does not list system-upgrade-controller.yaml")

    # K6
    heredoc = re.search(r"^\s*hetzner_csi_values\s*=\s*<<-EOT\n(.*?)^\s*EOT\s*$", locals_src, re.S | re.M)
    check(heredoc is not None, "K6: local.hetzner_csi_values must be a <<-EOT heredoc")
    if heredoc:
        csi = yaml.safe_load(textwrap.dedent(heredoc.group(1))) or {}
        terms = (
            (((csi.get("node") or {}).get("affinity") or {}).get("nodeAffinity") or {})
            .get("requiredDuringSchedulingIgnoredDuringExecution", {})
            .get("nodeSelectorTerms")
            or [{}]
        )
        exprs = {(e.get("key"), e.get("operator"), tuple(e.get("values") or ())) for e in terms[0].get("matchExpressions") or []}
        for want in (
            ("node-role.kubernetes.io/control-plane", "DoesNotExist", ()),
            ("instance.hetzner.cloud/provided-by", "NotIn", ("robot",)),
        ):
            check(want in exprs, f"K6: CSI node affinity lost the module default {want}")
        for part, names in CSI_CONTAINERS.items():
            res = (csi.get(part) or {}).get("resources") or {}
            for name in names:
                r = res.get(name) or {}
                check(
                    bool((r.get("requests") or {}).get("memory")) and bool((r.get("limits") or {}).get("memory")),
                    f"K6: {part}.resources.{name} needs a memory request and limit",
                )

    if failures:
        for f in failures:
            print("FAIL", f)
        return 1
    print("ok: K1-K6")
    return 0


if __name__ == "__main__":
    sys.exit(main())
