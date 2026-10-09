#!/usr/bin/env bash
# Prove the mctl-reserved-platform-hosts-{ingress,ingressroute} admission
# policies (bootstrap/templates/system/admission-policies.yaml, owner map in
# bootstrap values.yaml reservedPlatformHosts) against a real API server,
# both ways.
#
# CEL in a ValidatingAdmissionPolicy is only checked by the API server that
# runs it: a policy that never denies, or one that denies every Ingress, lints
# and renders clean. So this starts k3s at the cluster's version in Docker,
# installs the Traefik CRDs and the policy exactly as the bootstrap chart
# renders it, and server-side dry-runs:
#
#   tests/fixtures/reserved-hosts/deny/*.yaml   each must be REFUSED by these policies
#   tests/fixtures/reserved-hosts/admit/*.yaml  each must be ADMITTED
#   tests/fixtures/reserved-hosts/invalid/*.yaml  each must be REFUSED by API
#                                               server field validation of the host before
#                                               admission: the premise that lets the
#                                               Ingress policy skip case/dot normalising
#   every file given with --admit FILE          each object must be ADMITTED
#   --services                                  every Ingress / IngressRoute that
#                                               platform-gitops/services/*/* renders
#                                               through base-service must be ADMITTED
#   --platform                                  every reserved host the bootstrap
#                                               Applications serve, in their destination
#                                               namespace, and every raw route in their
#                                               paths must be ADMITTED
#
# --admit is how the map is proven against reality before it can block a
# sync: dump the live Ingress / IngressRoute / IngressRouteTCP objects of the
# platform cluster to a file and pass it (docs/runbooks/reserved-hosts.md).
#
# Requires: docker, kubectl, helm, python3 with PyYAML, network access to
# pull rancher/k3s and the pinned Traefik CRD definition.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="$ROOT/tests/fixtures/reserved-hosts"
POLICY=mctl-reserved-platform-hosts
POLICIES="mctl-reserved-platform-hosts-ingress mctl-reserved-platform-hosts-ingressroute"
# Keep in step with the platform cluster (kubectl version) and its traefik image.
K3S_IMAGE="${K3S_IMAGE:-rancher/k3s:v1.33.13-k3s1}"
# The CRDs are fetched by the commit the tag pointed to, not by the tag (a
# tag can be moved), and checked against a digest. Bumping traefik means
# updating all three: git ls-remote https://github.com/traefik/traefik refs/tags/<tag>
TRAEFIK_VERSION="${TRAEFIK_VERSION:-v3.7.13}"
TRAEFIK_COMMIT="${TRAEFIK_COMMIT:-fc92cc118a0557a029c7019d5ee06665127b0f13}"
TRAEFIK_CRDS_SHA256="${TRAEFIK_CRDS_SHA256:-1d5e8558803804562238b0d4a57174aadd6d87c36e3c4c55199ebcc356a9406c}"
TRAEFIK_CRDS="https://raw.githubusercontent.com/traefik/traefik/${TRAEFIK_COMMIT}/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml"

EXTRA_ADMIT=()
SERVICES=0
PLATFORM=0
while [ $# -gt 0 ]; do
  case "$1" in
    --admit) EXTRA_ADMIT+=("$2"); shift 2 ;;
    --services) SERVICES=1; shift ;;
    --platform) PLATFORM=1; shift ;;
    *) echo "usage: $0 [--services] [--platform] [--admit FILE]..." >&2; exit 2 ;;
  esac
done

WORK="$(mktemp -d)"
NAME="mctl-vap-test-$$"
# Keep the script's own exit status: without `exit "$rc"` some bash versions
# report the trap's last command (0) for a run that failed, and a detector
# that cannot fail proves nothing.
cleanup() { rc=$?; docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WORK"; exit "$rc"; }
trap cleanup EXIT

# Docker Hub pulls time out in bursts on GitHub-hosted runners; retry the pull.
# shellcheck source=lib/docker-pull-retry.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/docker-pull-retry.sh"
docker_pull_retry "$K3S_IMAGE"
echo "== starting $K3S_IMAGE"
docker run -d --privileged --name "$NAME" -p 127.0.0.1::6443 "$K3S_IMAGE" server \
  --disable=traefik,servicelb,metrics-server,local-storage \
  --tls-san 127.0.0.1 >/dev/null
for _ in $(seq 1 60); do
  docker exec "$NAME" test -s /etc/rancher/k3s/k3s.yaml 2>/dev/null && break
  sleep 2
done
PORT="$(docker port "$NAME" 6443/tcp | head -1 | sed 's/.*://')"
docker exec "$NAME" cat /etc/rancher/k3s/k3s.yaml | sed "s#https://127.0.0.1:6443#https://127.0.0.1:${PORT}#" > "$WORK/kubeconfig"
chmod 600 "$WORK/kubeconfig"
export KUBECONFIG="$WORK/kubeconfig"

# Render every GitOps service the way applicationset-apps.yaml deploys it:
# release <team>-<service>, namespace <team>, chart base-service. Only the
# host-bearing kinds are kept; the result is admitted like an --admit file, so
# a service claiming another namespace's reserved host fails here, at PR time,
# instead of at sync. A service that does not render is an error, not a skip.
if [ "$SERVICES" = 1 ]; then
  : > "$WORK/services.yaml"
  for values in "$ROOT"/platform-gitops/services/*/*/values.yaml; do
    dir="$(dirname "$values")"; team="$(basename "$(dirname "$dir")")"; svc="$(basename "$dir")"
    helm template "$team-$svc" "$ROOT/platform-gitops/helm-charts/base-service" -n "$team" -f "$values" > "$WORK/one.yaml" \
      || { echo "FAIL: helm template failed for services/$team/$svc"; exit 1; }
    python3 - "$WORK/one.yaml" "$team" >> "$WORK/services.yaml" <<'PY'
import sys, yaml
for d in yaml.safe_load_all(open(sys.argv[1])):
    if d and d.get("kind") in ("Ingress", "IngressRoute", "IngressRouteTCP"):
        d["metadata"]["namespace"] = d["metadata"].get("namespace") or sys.argv[2]
        print("---")
        print(yaml.safe_dump(d))
PY
  done
  EXTRA_ADMIT+=("$WORK/services.yaml")
fi

# The platform's own hosts are not served from services/: they come from the
# Applications the bootstrap chart renders (inline Helm values or valueFiles of
# an upstream chart) and from raw manifests in their infra-components paths.
# Upstream charts are not pulled, so each reserved host found under an
# `ingress` key of an Application's values becomes a minimal Ingress in that
# Application's destination namespace, and raw Ingress / IngressRoute
# manifests in its path sources are taken as they are. Both are admitted like
# an --admit file: an owner map that disagrees with where the platform serves
# a host fails here, at PR time, instead of as a refused sync. Hosts that
# merely appear in values (issuer URLs, env vars) are references, not routes,
# and are not checked. A reserved host that no Application serves under an
# `ingress` key is reported, because it is then only covered by --admit.
if [ "$PLATFORM" = 1 ]; then
  helm template test "$ROOT/platform-gitops/bootstrap" -f "$ROOT/platform-gitops/bootstrap/values.yaml" > "$WORK/platform-apps.yaml"
  python3 - "$ROOT" "$WORK/platform-apps.yaml" > "$WORK/platform.yaml" <<'PY'
import glob, os, re, sys, yaml
root, rendered = sys.argv[1], sys.argv[2]
owners = yaml.safe_load(open(os.path.join(root, "platform-gitops/bootstrap/values.yaml")))["reservedPlatformHosts"]
ROUTES = ("Ingress", "IngressRoute", "IngressRouteTCP")
def repo_id(url):
    # ArgoCD treats these spellings as one repository; so must the skip below,
    # or a harmless spelling change would silently drop this repo's coverage.
    u = url.strip().lower().rstrip("/")
    u = u[:-4] if u.endswith(".git") else u
    if "://" in u:
        u = u.split("://", 1)[1]
    elif re.match(r"^[^/@]+@[^/:]+:", u):  # scp-style git@host:owner/repo
        u = u.split("@", 1)[1].replace(":", "/", 1)
    return u.split("@", 1)[-1]  # drop user@ of ssh://git@host/...

SELF = repo_id("https://github.com/mctlhq/mctl-gitops.git")

def local(src):
    # Files of a source in another repository (a tenant's own repository, e.g.
    # git.mctl.ai/erpact/mctl-apps) are not in this checkout. They hold tenant
    # routes, not platform ones; the admission policy still judges them at sync.
    return repo_id(src.get("repoURL", SELF)) == SELF

def strings(o, path):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from strings(v, path + [str(k)])
    elif isinstance(o, list):
        for v in o:
            yield from strings(v, path)
    elif isinstance(o, str):
        yield path, o

def values_of(src):
    helm = src.get("helm") or {}
    if helm.get("valuesObject"):
        yield helm["valuesObject"]
    if helm.get("values"):
        yield yaml.safe_load(helm["values"])
    for f in helm.get("valueFiles") or []:
        if not local(src):
            continue
        if f.startswith("$"):
            continue  # ApplicationSet data; tenant/service values, not platform
        yield yaml.safe_load(open(os.path.join(root, src["path"], f)))

out, served = [], set()
apps = [d for d in yaml.safe_load_all(open(rendered)) if d and d.get("kind") == "Application"]
# argocd-self-managed (ops.mctl.ai) lives in the argocd wrapper chart, whose
# upstream dependency is not vendored; its Application template is plain YAML.
# A templated file there that declares an Application cannot be read this way
# and is an error, not a skip.
for f in sorted(glob.glob(os.path.join(root, "platform-gitops/argocd/templates/*.yaml"))):
    text = open(f).read()
    if "kind: Application\n" not in text:
        continue
    try:
        apps += [d for d in yaml.safe_load_all(text) if d and d.get("kind") == "Application"]
    except yaml.YAMLError as e:
        sys.exit(f"{f} declares an Application but is templated; extend --platform to render it: {e}")
if not apps:
    sys.exit("no Applications in the bootstrap render")
for app in apps:
    ns = app["spec"]["destination"].get("namespace")
    name = app["metadata"]["name"]
    for src in app["spec"].get("sources") or [app["spec"]["source"]]:
        for values in values_of(src):
            hosts = set()
            for path, s in strings(values or {}, []):
                if not any("ingress" in p.lower() for p in path):
                    continue
                hosts |= {h for h in owners if h == s or s.endswith("://" + h) or s.startswith(h + "/")}
            for h in sorted(hosts):
                served.add(h)
                out.append({"apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
                            "metadata": {"name": f"{name}-{len(out)}", "namespace": ns},
                            "spec": {"rules": [{"host": h}], "tls": [{"hosts": [h]}]}})
        path = src.get("path")
        if not path or not local(src) or path == "platform-gitops/bootstrap" or os.path.exists(os.path.join(root, path, "Chart.yaml")):
            continue
        for f in sorted(glob.glob(os.path.join(root, path, "**", "*.yaml"), recursive=True)):
            for d in yaml.safe_load_all(open(f)):
                if d and d.get("kind") in ROUTES:
                    d["metadata"]["namespace"] = d["metadata"].get("namespace") or ns
                    served |= set(re.findall(r"[A-Za-z0-9*.-]+", yaml.safe_dump(d))) & set(owners)
                    out.append(d)
for h in sorted(set(owners) - served):
    print(f"note: {h} is reserved but served by no bootstrap Application route; only --admit covers it", file=sys.stderr)
if not out:
    sys.exit("no platform routes found: the extraction is broken, not the map")
print(yaml.safe_dump_all(out))
PY
  EXTRA_ADMIT+=("$WORK/platform.yaml")
fi
for _ in $(seq 1 60); do
  kubectl get --raw /readyz >/dev/null 2>&1 && break
  sleep 2
done
kubectl get --raw /readyz >/dev/null

echo "== Traefik CRDs $TRAEFIK_VERSION (${TRAEFIK_COMMIT:0:8})"
curl -fsSL --retry 3 --retry-delay 2 "$TRAEFIK_CRDS" -o "$WORK/traefik-crds.yaml"
got="$( (command -v sha256sum >/dev/null && sha256sum || shasum -a 256) < "$WORK/traefik-crds.yaml" | awk '{print $1}')"
# Case-insensitive: the tools print lowercase hex, an override may not. tr,
# not ${x,,}, because macOS ships bash 3.2.
want="$(printf %s "$TRAEFIK_CRDS_SHA256" | tr 'A-F' 'a-f')"
[ "$got" = "$want" ] || { echo "FAIL: traefik CRD digest $got, expected $TRAEFIK_CRDS_SHA256"; exit 1; }
kubectl apply --server-side -f "$WORK/traefik-crds.yaml" >/dev/null
kubectl wait --for=condition=Established --timeout=60s \
  crd/ingressroutes.traefik.io crd/ingressroutetcps.traefik.io >/dev/null

echo "== policy from the rendered bootstrap chart"
# values-test.yaml only adds a deeper reserved name for the wildcard fixtures.
helm template test "$ROOT/platform-gitops/bootstrap" -f "$ROOT/platform-gitops/bootstrap/values.yaml" \
  -f "$FIXTURES/values-test.yaml" > "$WORK/bootstrap.yaml"
python3 - "$WORK/bootstrap.yaml" "$POLICY" > "$WORK/policy.yaml" <<'PY'
import sys, yaml
docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d
        and d.get("kind") in ("ValidatingAdmissionPolicy", "ValidatingAdmissionPolicyBinding")
        and d["metadata"]["name"].startswith(sys.argv[2] + "-")]
if len(docs) != 4:
    sys.exit(f"expected two policies and two bindings in the render, found {len(docs)}")
print(yaml.safe_dump_all(docs))
PY
kubectl apply -f "$WORK/policy.yaml" >/dev/null

# Type errors only surface in the policy's status; an expression that does not
# type-check is skipped at runtime rather than denying, so treat any warning as
# a failure.
for p in $POLICIES; do
  for _ in $(seq 1 30); do
    kubectl get validatingadmissionpolicy "$p" -o jsonpath='{.status.typeChecking}' 2>/dev/null | grep -q . && break
    sleep 1
  done
  kubectl get validatingadmissionpolicy "$p" -o jsonpath='{.status.typeChecking}' | grep -q . \
    || { echo "FAIL: $p never reported type-checking status"; exit 1; }
  WARN="$(kubectl get validatingadmissionpolicy "$p" -o jsonpath='{.status.typeChecking.expressionWarnings}')"
  if [ -n "$WARN" ] && [ "$WARN" != "[]" ]; then
    echo "FAIL: type-check warnings on $p:"
    echo "$WARN"
    exit 1
  fi
  echo "ok   type-check $p"
done

# Every namespace a fixture or an --admit object names. The
# ${arr[@]+"${arr[@]}"} form is for bash 3.2 (macOS), where an empty array
# under `set -u` is an unbound variable.
for ns in $(cat "$FIXTURES"/deny/*.yaml "$FIXTURES"/admit/*.yaml "$FIXTURES"/invalid/*.yaml ${EXTRA_ADMIT[@]+"${EXTRA_ADMIT[@]}"} 2>/dev/null \
            | grep -E '^\s+namespace: ' | awk '{print $2}' | sort -u); do
  kubectl create namespace "$ns" >/dev/null 2>&1 || true
done

# The binding is eventually consistent: wait until the policy refuses a
# known-bad object before trusting any admit result.
for probe in "$FIXTURES/deny/01-tenant-claims-auth.yaml" "$FIXTURES/deny/07-route-claims-auth.yaml"; do
  for _ in $(seq 1 60); do
    if ! kubectl apply --dry-run=server -f "$probe" >/dev/null 2>"$WORK/err" && grep -q "$POLICY" "$WORK/err"; then
      break
    fi
    sleep 1
  done
done

fail=0
for f in "$FIXTURES"/deny/*.yaml; do
  if kubectl apply --dry-run=server -f "$f" >/dev/null 2>"$WORK/err"; then
    echo "FAIL deny  $(basename "$f"): admitted"; fail=1
  elif ! grep -q "$POLICY" "$WORK/err"; then
    echo "FAIL deny  $(basename "$f"): refused, but not by $POLICY: $(cat "$WORK/err")"; fail=1
  else
    echo "ok   deny  $(basename "$f")"
  fi
done
for f in "$FIXTURES"/invalid/*.yaml; do
  if kubectl apply --dry-run=server -f "$f" >/dev/null 2>"$WORK/err"; then
    echo "FAIL invalid $(basename "$f"): admitted"; fail=1
  # Identified by structure, not by the upstream message text: a field
  # validation error ("is invalid:") on a host field path, and no admission
  # policy involved.
  elif ! grep -q ' is invalid: ' "$WORK/err" \
       || ! grep -qE 'spec\.(rules|tls)\[[0-9]+\]\.host' "$WORK/err" \
       || grep -q 'ValidatingAdmissionPolicy' "$WORK/err"; then
    echo "FAIL invalid $(basename "$f"): refused, but not by API server host validation: $(cat "$WORK/err")"; fail=1
  else
    echo "ok   invalid $(basename "$f")"
  fi
done
for f in "$FIXTURES"/admit/*.yaml; do
  if kubectl apply --dry-run=server -f "$f" >/dev/null 2>"$WORK/err"; then
    echo "ok   admit $(basename "$f")"
  else
    echo "FAIL admit $(basename "$f"): $(cat "$WORK/err")"; fail=1
  fi
done
for f in ${EXTRA_ADMIT[@]+"${EXTRA_ADMIT[@]}"}; do
  n=0; bad=0
  python3 - "$f" "$WORK/split" <<'PY'
import os, sys, yaml
os.makedirs(sys.argv[2], exist_ok=True)
docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d]
items = []
for d in docs:
    items.extend(d["items"] if d.get("kind", "").endswith("List") else [d])
for i, o in enumerate(items):
    m = o["metadata"]
    o["metadata"] = {"name": m["name"], "namespace": m["namespace"]}
    o.pop("status", None)
    with open(os.path.join(sys.argv[2], f"{i:04d}.yaml"), "w") as fh:
        yaml.safe_dump(o, fh)
PY
  for o in "$WORK"/split/*.yaml; do
    [ -e "$o" ] || continue
    n=$((n + 1))
    if ! kubectl apply --dry-run=server -f "$o" >/dev/null 2>"$WORK/err"; then
      echo "FAIL admit $(basename "$f") $(python3 -c "import sys,yaml;o=yaml.safe_load(open(sys.argv[1]));print(o['kind'], o['metadata']['namespace']+'/'+o['metadata']['name'])" "$o"): $(cat "$WORK/err")"
      bad=$((bad + 1)); fail=1
    fi
  done
  # Zero objects means the dump or the extraction is broken, not that
  # everything was admitted.
  if [ "$n" = 0 ]; then echo "FAIL admit $(basename "$f"): no route objects in it"; fail=1; fi
  echo "$( [ "$bad" = 0 ] && [ "$n" != 0 ] && echo ok || echo FAIL)   admit $(basename "$f"): $((n - bad))/$n objects admitted"
  rm -rf "$WORK/split"
done

exit "$fail"
