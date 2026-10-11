#!/usr/bin/env bash
# Prove the mctl-external-manifests-* admission policies (Secret and
# ServiceAccount allowlist, Ingress host pattern, ClusterIP-only Services;
# bootstrap/templates/system/admission-policies.yaml, per-namespace values in
# bootstrap values.yaml externalManifestNamespaces) against a real API
# server, both ways.
#
# k3s at the cluster's version in Docker, the policy exactly as the bootstrap
# chart renders it, then server-side dry-runs:
#
#   tests/fixtures/secret-allowlist/deny/*.yaml   each must be REFUSED by these policies,
#                                                 with the message its `# expect:` line names
#   tests/fixtures/secret-allowlist/admit/*.yaml  each must be ADMITTED
#   an ephemeral container naming a non-allowed Secret, added through the
#   pods/ephemeralcontainers subresource (kubectl debug's path), must be REFUSED
#
# tests/fixtures/secret-allowlist/setup.yaml is created for real first, and
# values-test.yaml is layered over the bootstrap values.
#
# Requires: docker, kubectl, helm, python3 with PyYAML, network access to
# pull rancher/k3s and the pinned Traefik CRD definition.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="$ROOT/tests/fixtures/secret-allowlist"
POLICY=mctl-external-manifests
POLICIES="mctl-external-manifests-secret-allowlist mctl-external-manifests-ingress-hosts mctl-external-manifests-services mctl-external-manifests-no-traefik mctl-external-manifests-no-grafana-configmaps"
# Keep in step with the platform cluster and scripts/test-reserved-hosts-policy.sh.
K3S_IMAGE="${K3S_IMAGE:-rancher/k3s:v1.33.13-k3s1}"
TRAEFIK_VERSION="${TRAEFIK_VERSION:-v3.7.13}"
TRAEFIK_CRDS="https://raw.githubusercontent.com/traefik/traefik/${TRAEFIK_VERSION}/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml"

WORK="$(mktemp -d)"
NAME="mctl-vap-secrets-$$"
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
for _ in $(seq 1 60); do
  kubectl get --raw /readyz >/dev/null 2>&1 && break
  sleep 2
done
kubectl get --raw /readyz >/dev/null

echo "== Traefik CRDs $TRAEFIK_VERSION"
curl -fsSL --retry 3 --retry-delay 2 "$TRAEFIK_CRDS" -o "$WORK/traefik-crds.yaml"
kubectl apply --server-side -f "$WORK/traefik-crds.yaml" >/dev/null
kubectl wait --for=condition=Established --timeout=60s \
  crd/ingressroutes.traefik.io crd/ingressroutetcps.traefik.io crd/ingressrouteudps.traefik.io \
  crd/tlsoptions.traefik.io crd/tlsstores.traefik.io >/dev/null

echo "== policies from the rendered bootstrap chart"
helm template test "$ROOT/platform-gitops/bootstrap" -f "$ROOT/platform-gitops/bootstrap/values.yaml" \
  -f "$FIXTURES/values-test.yaml" > "$WORK/bootstrap.yaml"
# The render must hold exactly one policy and one binding for each name in
# $POLICIES: a policy added to the chart but not here would go untested,
# and one listed here but not rendered would only show up as a timeout.
python3 - "$WORK/bootstrap.yaml" "$POLICY" "$POLICIES" > "$WORK/policy.yaml" <<'PY'
import sys, yaml
docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d
        and d.get("kind") in ("ValidatingAdmissionPolicy", "ValidatingAdmissionPolicyBinding")
        and d["metadata"]["name"].startswith(sys.argv[2] + "-")]
want = sorted(sys.argv[3].split())
for kind in ("ValidatingAdmissionPolicy", "ValidatingAdmissionPolicyBinding"):
    got = sorted(d["metadata"]["name"] for d in docs if d["kind"] == kind)
    if got != want:
        sys.exit(f"{kind}s in the render do not match $POLICIES:\n  render:    {got}\n  POLICIES:  {want}")
print(yaml.safe_dump_all(docs))
PY
kubectl apply -f "$WORK/policy.yaml" >/dev/null

# An expression that does not type-check is skipped at runtime instead of
# denying, so any warning is a failure.
for p in $POLICIES; do
  for _ in $(seq 1 30); do
    kubectl get validatingadmissionpolicy "$p" -o jsonpath='{.status.typeChecking}' 2>/dev/null | grep -q . && break
    sleep 1
  done
  kubectl get validatingadmissionpolicy "$p" -o jsonpath='{.status.typeChecking}' | grep -q . \
    || { echo "FAIL: $p never reported type-checking status"; exit 1; }
  WARN="$(kubectl get validatingadmissionpolicy "$p" -o jsonpath='{.status.typeChecking.expressionWarnings}')"
  if [ -n "$WARN" ] && [ "$WARN" != "[]" ]; then
    echo "FAIL: type-check warnings on $p:"; echo "$WARN"; exit 1
  fi
  echo "ok   type-check $p"
done

for ns in $(cat "$FIXTURES"/setup.yaml "$FIXTURES"/deny/*.yaml "$FIXTURES"/admit/*.yaml \
            | grep -E '^\s+namespace: ' | awk '{print $2}' | sort -u); do
  kubectl create namespace "$ns" >/dev/null 2>&1 || true
done
for _ in $(seq 1 60); do
  kubectl get serviceaccount default -n erpact >/dev/null 2>&1 && break
  sleep 1
done

# The binding is eventually consistent: wait until a known-bad Pod is refused.
for _ in $(seq 1 60); do
  if ! kubectl apply --dry-run=server -f "$FIXTURES/deny/01-volume-reflected-pat.yaml" >/dev/null 2>"$WORK/err" \
     && grep -q "$POLICY" "$WORK/err"; then
    break
  fi
  sleep 1
done
kubectl apply -f "$FIXTURES/setup.yaml" >/dev/null

fail=0
for f in "$FIXTURES"/deny/*.yaml; do
  grep -q '^# expect: .' "$f" || { echo "FAIL deny  $(basename "$f"): no '# expect:' line"; fail=1; continue; }
  if kubectl apply --dry-run=server -f "$f" >/dev/null 2>"$WORK/err"; then
    echo "FAIL deny  $(basename "$f"): admitted"; fail=1
  elif ! grep -q "$POLICY" "$WORK/err"; then
    echo "FAIL deny  $(basename "$f"): refused, but not by $POLICY: $(cat "$WORK/err")"; fail=1
  elif ! grep -qF "$(sed -n 's/^# expect: //p' "$f")" "$WORK/err"; then
    echo "FAIL deny  $(basename "$f"): refused for another reason than '$(sed -n 's/^# expect: //p' "$f")': $(cat "$WORK/err")"; fail=1
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

ephemeral() { # secret name -> patch body
  printf '{"spec":{"ephemeralContainers":[{"name":"dbg","image":"busybox","envFrom":[{"secretRef":{"name":"%s"}}]}]}}' "$1"
}
if kubectl patch pod debug-target -n erpact --subresource=ephemeralcontainers --type=strategic \
     --dry-run=server -p "$(ephemeral github-actions-pat)" >/dev/null 2>"$WORK/err"; then
  echo "FAIL deny  ephemeral container: admitted"; fail=1
elif ! grep -q "$POLICY" "$WORK/err"; then
  echo "FAIL deny  ephemeral container: refused, but not by $POLICY: $(cat "$WORK/err")"; fail=1
else
  echo "ok   deny  ephemeral container"
fi
if kubectl patch pod debug-target -n erpact --subresource=ephemeralcontainers --type=strategic \
     --dry-run=server -p "$(ephemeral clo-s3)" >/dev/null 2>"$WORK/err"; then
  echo "ok   admit ephemeral container"
else
  echo "FAIL admit ephemeral container: $(cat "$WORK/err")"; fail=1
fi

exit "$fail"
