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
#   every file given with --admit FILE          each object must be ADMITTED
#   --services                                  every Ingress / IngressRoute that
#                                               platform-gitops/services/*/* renders
#                                               through base-service must be ADMITTED
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
TRAEFIK_VERSION="${TRAEFIK_VERSION:-v3.7.13}"
TRAEFIK_CRDS="https://raw.githubusercontent.com/traefik/traefik/${TRAEFIK_VERSION}/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml"

EXTRA_ADMIT=()
SERVICES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --admit) EXTRA_ADMIT+=("$2"); shift 2 ;;
    --services) SERVICES=1; shift ;;
    *) echo "usage: $0 [--services] [--admit FILE]..." >&2; exit 2 ;;
  esac
done

WORK="$(mktemp -d)"
NAME="mctl-vap-test-$$"
# Keep the script's own exit status: without `exit "$rc"` some bash versions
# report the trap's last command (0) for a run that failed, and a detector
# that cannot fail proves nothing.
cleanup() { rc=$?; docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$WORK"; exit "$rc"; }
trap cleanup EXIT

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
for _ in $(seq 1 60); do
  kubectl get --raw /readyz >/dev/null 2>&1 && break
  sleep 2
done
kubectl get --raw /readyz >/dev/null

echo "== Traefik CRDs $TRAEFIK_VERSION"
curl -fsSL "$TRAEFIK_CRDS" -o "$WORK/traefik-crds.yaml"
kubectl apply --server-side -f "$WORK/traefik-crds.yaml" >/dev/null
kubectl wait --for=condition=Established --timeout=60s \
  crd/ingressroutes.traefik.io crd/ingressroutetcps.traefik.io >/dev/null

echo "== policy from the rendered bootstrap chart"
helm template test "$ROOT/platform-gitops/bootstrap" -f "$ROOT/platform-gitops/bootstrap/values.yaml" > "$WORK/bootstrap.yaml"
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
for ns in $(cat "$FIXTURES"/deny/*.yaml "$FIXTURES"/admit/*.yaml ${EXTRA_ADMIT[@]+"${EXTRA_ADMIT[@]}"} 2>/dev/null \
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
    n=$((n + 1))
    if ! kubectl apply --dry-run=server -f "$o" >/dev/null 2>"$WORK/err"; then
      echo "FAIL admit $(basename "$f") $(python3 -c "import sys,yaml;o=yaml.safe_load(open(sys.argv[1]));print(o['kind'], o['metadata']['namespace']+'/'+o['metadata']['name'])" "$o"): $(cat "$WORK/err")"
      bad=$((bad + 1)); fail=1
    fi
  done
  echo "$( [ "$bad" = 0 ] && echo ok || echo FAIL)   admit $(basename "$f"): $((n - bad))/$n objects admitted"
  rm -rf "$WORK/split"
done

exit "$fail"
