#!/usr/bin/env bash
# Prove the mctl-tenant-workflow-sa-argocd-* admission policies
# (bootstrap/templates/system/admission-policies.yaml) and the tenant chart's
# argocd Role (helm-charts/tenant/templates/argo-workflow.yaml) against a real
# API server, both ways.
#
# k3s at the cluster's version in Docker, the Argo CD CRDs at the version the
# cluster runs, the policies exactly as the bootstrap chart renders them, the
# Role exactly as the tenant chart renders it for tenant karabu, and the
# objects in tests/fixtures/tenant-workflow-sa-argocd/setup.yaml. Then
# server-side dry-runs as system:serviceaccount:karabu:argo-workflow-sa:
#
#   admit  every write the tenant workflow templates send (refresh annotations,
#          delete of an owned Application, the retire finalizer fallback)
#   deny   every other write, and each must be refused by the policy itself,
#          not by RBAC: the message must name the policy
#   rbac   writes the narrowed Role must refuse before admission runs
#
# plus the platform workflow tier (argo-workflows/argo-workflow-sa), which
# the policies must not match.
#
# TEST_KUBECONFIG=<file> runs against an existing throwaway API server
# instead of starting k3s (for hosts without Docker). It must point at
# 127.0.0.1: the script creates and deletes objects in namespace argocd.
# A bare kube-apiserver has no kube-controller-manager to report type-checking
# status; TEST_SKIP_TYPECHECK=1 skips that one step there. CI runs it in full.
#
# Requires: kubectl, helm, python3 with PyYAML; docker and network access to
# pull rancher/k3s and the pinned Argo CD CRDs unless TEST_KUBECONFIG is set.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="$ROOT/tests/fixtures/tenant-workflow-sa-argocd"
POLICY=mctl-tenant-workflow-sa-argocd
POLICIES="mctl-tenant-workflow-sa-argocd-applications mctl-tenant-workflow-sa-argocd-applicationsets"
# Keep in step with the platform cluster and the other policy scripts.
K3S_IMAGE="${K3S_IMAGE:-rancher/k3s:v1.33.13-k3s1}"
# The Argo CD version the cluster runs (argocd-server image).
ARGOCD_VERSION="${ARGOCD_VERSION:-v3.3.8}"
ARGOCD_CRDS="https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/crds"
TENANT=karabu
SA="system:serviceaccount:${TENANT}:argo-workflow-sa"
PLATFORM_SA="system:serviceaccount:argo-workflows:argo-workflow-sa"

WORK="$(mktemp -d)"
NAME="mctl-vap-argocd-$$"
cleanup() {
  rc=$?
  [ -z "${TEST_KUBECONFIG:-}" ] && docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK"
  exit "$rc"
}
trap cleanup EXIT

if [ -n "${TEST_KUBECONFIG:-}" ]; then
  server="$(kubectl --kubeconfig "$TEST_KUBECONFIG" config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
  case "$server" in
    https://127.0.0.1:*) ;;
    *) echo "TEST_KUBECONFIG must point at a local throwaway API server, got $server" >&2; exit 2 ;;
  esac
  export KUBECONFIG="$TEST_KUBECONFIG"
else
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
fi
for _ in $(seq 1 60); do
  kubectl get --raw /readyz >/dev/null 2>&1 && break
  sleep 2
done
kubectl get --raw /readyz >/dev/null

echo "== Argo CD CRDs $ARGOCD_VERSION"
for crd in application applicationset; do
  curl -fsSL --retry 3 --retry-delay 2 "$ARGOCD_CRDS/$crd-crd.yaml" -o "$WORK/$crd-crd.yaml"
  kubectl apply --server-side -f "$WORK/$crd-crd.yaml" >/dev/null
done
kubectl wait --for=condition=Established --timeout=60s \
  crd/applications.argoproj.io crd/applicationsets.argoproj.io >/dev/null

echo "== policies from the rendered bootstrap chart"
helm template test "$ROOT/platform-gitops/bootstrap" -f "$ROOT/platform-gitops/bootstrap/values.yaml" \
  > "$WORK/bootstrap.yaml"
# Exactly one policy and one binding per name in $POLICIES: a policy added to
# the chart but not here would go untested.
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
  if [ -n "${TEST_SKIP_TYPECHECK:-}" ]; then echo "skip type-check $p"; continue; fi
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

echo "== RBAC: tenant chart for $TENANT, platform tier from argo-workflows config"
for ns in argocd "$TENANT" argo-workflows; do
  kubectl create namespace "$ns" >/dev/null 2>&1 || true
done
helm template test "$ROOT/platform-gitops/helm-charts/tenant" --set "tenant.name=$TENANT" > "$WORK/tenant.yaml"
python3 - "$WORK/tenant.yaml" "$ROOT/platform-gitops/argo-workflows/config/sa-and-rbac.yaml" > "$WORK/rbac.yaml" <<'PY'
import sys, yaml
out = []
tenant = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d]
out += [d for d in tenant if d["kind"] in ("Role", "RoleBinding") and d["metadata"].get("namespace") == "argocd"]
out += [d for d in tenant if d["kind"] == "ServiceAccount" and d["metadata"]["name"] == "argo-workflow-sa"]
platform = [d for d in yaml.safe_load_all(open(sys.argv[2])) if d]
out += [d for d in platform if d["kind"] in ("Role", "RoleBinding") and d["metadata"].get("namespace") == "argocd"]
if len(out) != 5:
    sys.exit(f"expected tenant Role+RoleBinding+SA and platform Role+RoleBinding in argocd, got {[(d['kind'], d['metadata']['name']) for d in out]}")
print(yaml.safe_dump_all(out))
PY
kubectl apply -f "$WORK/rbac.yaml" >/dev/null
kubectl apply -f "$FIXTURES/setup.yaml" >/dev/null

# The binding is eventually consistent: wait until a known-bad delete is refused
# by the policy.
for _ in $(seq 1 60); do
  if ! kubectl --as="$SA" -n argocd delete application root-app --dry-run=server >/dev/null 2>"$WORK/err" \
     && grep -q "$POLICY" "$WORK/err"; then
    break
  fi
  sleep 1
done

fail=0
as_sa() { # run kubectl as the tenant SA; mutating verbs as server-side dry-runs
  case "$1" in
    get) kubectl --as="$SA" -n argocd "$@" ;;
    *)   kubectl --as="$SA" -n argocd "$@" --dry-run=server ;;
  esac
}
admit() { # description, then the kubectl arguments (run as the tenant SA)
  local what="$1"; shift
  if as_sa "$@" >/dev/null 2>"$WORK/err"; then
    echo "ok   admit $what"
  else
    echo "FAIL admit $what: $(cat "$WORK/err")"; fail=1
  fi
}
deny() { # description, expected message, then the kubectl arguments;
         # must be refused by the policy, for that reason
  local what="$1" expect="$2"; shift 2
  if as_sa "$@" >/dev/null 2>"$WORK/err"; then
    echo "FAIL deny  $what: admitted"; fail=1
  elif ! grep -q "$POLICY" "$WORK/err"; then
    echo "FAIL deny  $what: refused, but not by $POLICY: $(cat "$WORK/err")"; fail=1
  elif ! grep -qF "$expect" "$WORK/err"; then
    echo "FAIL deny  $what: refused for another reason than '$expect': $(cat "$WORK/err")"; fail=1
  else
    echo "ok   deny  $what"
  fi
}
rbac() { # description, then the kubectl arguments; must be refused by RBAC
  local what="$1"; shift
  if as_sa "$@" >/dev/null 2>"$WORK/err"; then
    echo "FAIL rbac  $what: admitted"; fail=1
  elif ! grep -q "Forbidden\|forbidden" "$WORK/err" || grep -q "$POLICY" "$WORK/err"; then
    echo "FAIL rbac  $what: not an RBAC refusal: $(cat "$WORK/err")"; fail=1
  else
    echo "ok   rbac  $what"
  fi
}
REFRESH='{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard","mctl.ai/refresh-ts":"1790976098"}}}'

# What the tenant workflow templates send.
admit "smoke-test: refresh own Application" \
  annotate application karabu-web argocd.argoproj.io/refresh=hard --overwrite
admit "smoke-test: refresh shared-pg" \
  annotate application shared-pg argocd.argoproj.io/refresh=hard --overwrite
admit "deploy-service: refresh ApplicationSet apps" \
  patch applicationset apps --type merge -p "$REFRESH"
admit "deploy-service: get ApplicationSet apps" \
  get applicationset apps
admit "retire-service: delete own Application" \
  delete application karabu-web
admit "retire-service: clear own Application's finalizers" \
  patch application karabu-web --type merge -p '{"metadata":{"finalizers":null}}'

# Deletes of anything not owned (team=karabu AND project apps).
deny "delete root-app" "may only delete Applications labelled" delete application root-app
deny "delete shared-pg" "may only delete Applications labelled" delete application shared-pg
deny "delete another tenant's app" "may only delete Applications labelled" delete application labs-web
deny "delete tenant-karabu" "may only delete Applications labelled" delete application tenant-karabu
deny "delete team=karabu outside project apps" "may only delete Applications labelled" delete application karabu-outside-apps

# Updates beyond the refresh annotations.
deny "retarget own Application's repoURL" "may not change an Application's spec" \
  patch application karabu-web --type merge -p '{"spec":{"source":{"repoURL":"https://example.invalid/x.git"}}}'
deny "move own Application to another project" "may not change an Application's spec" \
  patch application karabu-web --type merge -p '{"spec":{"project":"default"}}'
deny "start an operation on root-app" "may not start or change an Application operation" \
  patch application root-app --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'
deny "write status on root-app" "may not change an Application's status" \
  patch application root-app --type merge -p '{"status":{"sync":{"status":"Synced"}}}'
deny "relabel own Application to another team" "may not change an Application's labels" \
  label application karabu-web team=labs --overwrite
deny "label root-app as owned" "may not change an Application's labels" \
  label application root-app team=karabu
deny "clear root-app's finalizers" "may only remove finalizers, and only from their own" \
  patch application root-app --type merge -p '{"metadata":{"finalizers":null}}'
deny "clear another tenant's finalizers" "may only remove finalizers, and only from their own" \
  patch application labs-web --type merge -p '{"metadata":{"finalizers":null}}'
deny "add a finalizer to own Application" "may only remove finalizers, and only from their own" \
  patch application karabu-web --type merge -p '{"metadata":{"finalizers":["resources-finalizer.argocd.argoproj.io","example.invalid/hold"]}}'
deny "set another annotation on root-app" "may only change the annotations" \
  annotate application root-app argocd.argoproj.io/sync-options=Prune=true --overwrite
deny "remove an annotation from own Application" "may only change the annotations" \
  annotate application karabu-web argocd.argoproj.io/tracking-id-
deny "set ownerReferences on own Application" "ownerReferences" \
  patch application karabu-web --type merge -p '{"metadata":{"ownerReferences":[{"apiVersion":"argoproj.io/v1alpha1","kind":"ApplicationSet","name":"tenants","uid":"00000000-0000-0000-0000-000000000000"}]}}'
deny "change ApplicationSet apps' template project" "may not change an ApplicationSet's spec" \
  patch applicationset apps --type merge -p '{"spec":{"template":{"spec":{"project":"default"}}}}'
deny "label ApplicationSet apps" "may not change an ApplicationSet's labels" \
  label applicationset apps example.invalid/x=y
deny "set another annotation on ApplicationSet apps" "may only change the annotations" \
  annotate applicationset apps argocd.argoproj.io/tracking-id=x --overwrite

# What the narrowed Role refuses before admission.
rbac "patch ApplicationSet tenants"  patch applicationset tenants --type merge -p "$REFRESH"
rbac "delete ApplicationSet apps"    delete applicationset apps
rbac "list ApplicationSets"          get applicationsets

# The platform workflow tier is not matched.
if kubectl --as="$PLATFORM_SA" -n argocd delete application tenant-karabu --dry-run=server >/dev/null 2>"$WORK/err"; then
  echo "ok   admit platform tier: delete tenant-karabu"
else
  echo "FAIL admit platform tier: delete tenant-karabu: $(cat "$WORK/err")"; fail=1
fi

exit "$fail"
