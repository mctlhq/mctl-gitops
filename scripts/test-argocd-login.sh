#!/usr/bin/env bash
# End-to-end check of Argo CD's sign-in plumbing on the upgrade path the
# platform cluster actually takes (#1500). Was test-argocd-dex.sh; Dex is gone
# (#1500 phase 4) and the Dex checks went with it.
#
# The #1545 outage was invisible to tests that rendered config alone: the
# in-place server-side apply of chart objects failed on fields the bootstrap
# Helm release co-owns. So this runs the real thing:
#
#   1. k3s at the cluster's version in Docker;
#   2. Argo CD installed the way the cluster was bootstrapped: the argo-cd
#      chart at the bootstrap version with
#      infrastructure/k3s-preview/cluster-bootstrap/helm-values/argocd.yaml
#      (extraObjects dropped, so nothing syncs from GitHub);
#   3. platform-gitops/argocd as rendered at BASE_REF (default origin/main),
#      applied server-side as Argo CD applies it (field manager
#      argocd-controller, force-conflicts, no prune);
#   4. platform-gitops/argocd from the working tree, applied the same way.
#
# After step 4, argocd-server must be Ready without restarts, no server-side
# apply may have failed, and /auth/login must redirect to the authorize
# endpoint of the oidc.config issuer (ZITADEL).
#
# Kinds whose CRDs this cluster lacks (ExternalSecret, ServiceMonitor) and the
# self-managing Application are left out of steps 3 and 4, and so are Helm
# hooks, which Argo CD runs as sync hooks rather than applying. The keys the
# ExternalSecret merges into argocd-secret are set to dummy values instead.
#
# Requires: docker, kubectl, helm, python3 with PyYAML, curl, git, and network
# access (rancher/k3s, the argo-cd chart, the images).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART_DIR="$ROOT/platform-gitops/argocd"
# Keep in step with the platform cluster and the other k3s test scripts.
K3S_IMAGE="${K3S_IMAGE:-rancher/k3s:v1.33.13-k3s1}"
# infrastructure/k3s-preview/cluster-bootstrap/argocd.tf
BOOTSTRAP_CHART_VERSION="${BOOTSTRAP_CHART_VERSION:-9.4.1}"
BASE_REF="${BASE_REF:-origin/main}"
# Optional: test a committed ref instead of the working tree (e.g. the
# reverted #1545 head, which must FAIL here).
CANDIDATE_REF="${CANDIDATE_REF:-}"

WORK="$(mktemp -d)"
NAME="mctl-argocd-login-$$"
PF_PID=""
cleanup() {
  rc=$?
  [ -n "$PF_PID" ] && kill "$PF_PID" >/dev/null 2>&1 || true
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK"
  exit "$rc"
}
trap cleanup EXIT
fail() {
  echo "FAIL: $*" >&2
  if [ -n "${KEEP_ON_FAIL:-}" ]; then
    echo "kept: docker container $NAME, kubeconfig $WORK/kubeconfig.kept" >&2
    cp "$WORK/kubeconfig" "$WORK/../kubeconfig.$NAME"
    trap - EXIT
  fi
  exit 1
}

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

echo "== bootstrap install: argo-cd $BOOTSTRAP_CHART_VERSION with the bootstrap values"
python3 - "$ROOT/infrastructure/k3s-preview/cluster-bootstrap/helm-values/argocd.yaml" > "$WORK/bootstrap-values.yaml" <<'PY'
import sys, yaml
v = yaml.safe_load(open(sys.argv[1]))
v["extraObjects"] = []
print(yaml.safe_dump(v))
PY
helm install argocd argo-cd --repo https://argoproj.github.io/argo-helm \
  --version "$BOOTSTRAP_CHART_VERSION" -n argocd --create-namespace \
  -f "$WORK/bootstrap-values.yaml" --wait --timeout 10m >/dev/null
# What ExternalSecret argocd-github-oauth merges into argocd-secret in the
# cluster; dummies here.
kubectl -n argocd patch secret argocd-secret --type merge -p \
  '{"stringData":{"webhook.github.secret":"dummy"}}' >/dev/null

# What the zitadel-iac Job writes into argocd-oidc-zitadel in the cluster;
# dummies here, filled in once the Secret exists (see fill_oidc).
OIDC_DUMMY_CLIENT_ID=111111111111111111
fill_oidc() {
  kubectl -n argocd get secret argocd-oidc-zitadel >/dev/null 2>&1 || return 0
  kubectl -n argocd patch secret argocd-oidc-zitadel --type merge -p \
    "{\"stringData\":{\"clientID\":\"$OIDC_DUMMY_CLIENT_ID\",\"clientSecret\":\"dummy\",\"cliClientID\":\"222222222222222222\"}}" >/dev/null
}

render() { # <chart dir> <out>
  helm template argocd "$1" -n argocd > "$WORK/raw.yaml"
  python3 - "$WORK/raw.yaml" > "$2" <<'PY'
import sys, yaml
skip = {"ExternalSecret", "ServiceMonitor", "Application"}
# Helm hooks are run by Argo CD as sync hooks, not applied as resources.
docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d and d.get("kind") not in skip
        and "helm.sh/hook" not in (d["metadata"].get("annotations") or {})]
print(yaml.safe_dump_all(docs))
PY
}
# An apply error does not stop the run: kubectl applies the other objects,
# as Argo CD does, and the checks below show what that did to the server.
# Any apply error still fails the run at the end.
APPLY_ERRORS=""
apply() { # <manifest>
  if ! kubectl apply --server-side --field-manager=argocd-controller --force-conflicts -f "$1" >/dev/null 2>"$WORK/apply.err"; then
    cat "$WORK/apply.err" >&2
    APPLY_ERRORS="$APPLY_ERRORS $(basename "$1")"
  fi
}
settle() {
  for d in $(kubectl -n argocd get deploy -o name); do
    kubectl -n argocd rollout status "$d" --timeout=180s >/dev/null || echo "   $d did not roll out" >&2
  done
}

echo "== $BASE_REF of platform-gitops/argocd, as Argo CD applies it"
git -C "$ROOT" archive "$BASE_REF" platform-gitops/argocd | tar -x -C "$WORK"
render "$WORK/platform-gitops/argocd" "$WORK/base.yaml"
apply "$WORK/base.yaml"
fill_oidc
settle

if [ -n "$CANDIDATE_REF" ]; then
  echo "== $CANDIDATE_REF of platform-gitops/argocd, same way"
  mkdir -p "$WORK/cand"
  git -C "$ROOT" archive "$CANDIDATE_REF" platform-gitops/argocd | tar -x -C "$WORK/cand"
  render "$WORK/cand/platform-gitops/argocd" "$WORK/head.yaml"
else
  echo "== working tree of platform-gitops/argocd, same way"
  render "$CHART_DIR" "$WORK/head.yaml"
fi
apply "$WORK/head.yaml"
fill_oidc
settle
sleep 20

echo "== argocd-server: Ready, no restarts"
kubectl -n argocd wait --for=condition=Ready pod -l app.kubernetes.io/name=argocd-server --timeout=120s >/dev/null \
  || fail "argocd-server not Ready: $(kubectl -n argocd logs deploy/argocd-server --tail=200 2>&1 | grep -m1 -E 'level=(fatal|error)')"
restarts="$(kubectl -n argocd get pods -l app.kubernetes.io/name=argocd-server -o jsonpath='{range .items[*]}{.status.containerStatuses[0].restartCount}{"\n"}{end}' | sort -n | tail -1)"
[ "$restarts" = 0 ] || fail "argocd-server restarted $restarts times: $(kubectl -n argocd logs deploy/argocd-server --previous --tail=5 2>&1)"

URL="$(kubectl -n argocd get cm argocd-cm -o jsonpath='{.data.url}')"
kubectl -n argocd port-forward svc/argocd-server 18080:80 >/dev/null 2>&1 &
PF_PID=$!
for _ in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:18080/healthz && break; sleep 1; done

# The #1545 signal; checked before the login, which needs oidc.config.
[ -z "$APPLY_ERRORS" ] || fail "server-side apply failed for:$APPLY_ERRORS"

# Where Argo CD's own login must send the browser: the oidc.config issuer.
OIDC_ISSUER="$(kubectl -n argocd get cm argocd-cm -o jsonpath='{.data.oidc\.config}' | sed -n 's/^issuer: *//p')"
[ -n "$OIDC_ISSUER" ] || fail "argocd-cm has no oidc.config issuer"
EXPECT_LOGIN="$OIDC_ISSUER/oauth/v2/authorize?client_id=$OIDC_DUMMY_CLIENT_ID&"
echo "== /auth/login redirects to $EXPECT_LOGIN"
loc="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -H "Host: ${URL#https://}" http://127.0.0.1:18080/auth/login)"
case "$loc" in
  "303 $EXPECT_LOGIN"*) echo "   $loc" | cut -c1-120 ;;
  *) fail "/auth/login answered: $loc" ;;
esac

echo "PASS"
