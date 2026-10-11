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
# the tenant policies must not match and the mctl-platform-workflow-sa-argocd-*
# policies narrow, proven the same way: admit what create-tenant and
# delete-tenant(-safe) send, deny every other write by policy, and the
# narrowed Role in argo-workflows/config/sa-and-rbac.yaml.
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
PLATFORM_POLICY=mctl-platform-workflow-sa-argocd
POLICIES="$POLICY-applications $POLICY-applicationsets $PLATFORM_POLICY-applications $PLATFORM_POLICY-applicationsets $PLATFORM_POLICY-rbac"
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
# `kubectl wait` errors out instead of waiting while a fresh CRD has no
# status.conditions yet, so retry it.
for _ in $(seq 1 30); do
  kubectl wait --for=condition=Established --timeout=10s \
    crd/applications.argoproj.io crd/applicationsets.argoproj.io >/dev/null 2>&1 && break
  sleep 2
done
kubectl wait --for=condition=Established --timeout=10s \
  crd/applications.argoproj.io crd/applicationsets.argoproj.io >/dev/null

echo "== policies from the rendered bootstrap chart"
helm template test "$ROOT/platform-gitops/bootstrap" -f "$ROOT/platform-gitops/bootstrap/values.yaml" \
  > "$WORK/bootstrap.yaml"
# Exactly one policy and one binding per name in $POLICIES: a policy added to
# the chart but not here would go untested.
python3 - "$WORK/bootstrap.yaml" "$POLICY $PLATFORM_POLICY" "$POLICIES" > "$WORK/policy.yaml" <<'PY'
import sys, yaml
prefixes = tuple(p + "-" for p in sys.argv[2].split())
docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if d
        and d.get("kind") in ("ValidatingAdmissionPolicy", "ValidatingAdmissionPolicyBinding")
        and d["metadata"]["name"].startswith(prefixes)]
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

# The ApplicationSet controller marks what it generates with a controller
# ownerReference; give the fixtures that stand for generated Applications the
# same, pointing at the real fixture ApplicationSets (a dangling owner would
# be garbage-collected on k3s). karabu-outside-apps gets one too, so the
# project check is what refuses it.
owner() { # application, applicationset
  local uid
  uid="$(kubectl get applicationset "$2" -n argocd -o jsonpath='{.metadata.uid}')"
  kubectl patch application "$1" -n argocd --type merge -p \
    "{\"metadata\":{\"ownerReferences\":[{\"apiVersion\":\"argoproj.io/v1alpha1\",\"kind\":\"ApplicationSet\",\"name\":\"$2\",\"uid\":\"$uid\",\"controller\":true}]}}" >/dev/null
}
owner karabu-web apps
owner labs-web apps
owner karabu-outside-apps apps
owner tenant-karabu tenants

# Live Applications carry a status of up to ~700 KB (resources, history,
# operationState). Application has no status subresource, so every refresh
# annotation re-compares that whole status: give the refreshable fixtures one
# of about 1 MB so the admit cases below run against that cost, not against
# an empty status.
python3 - > "$WORK/status.json" <<'PY'
import json
msg = "x" * 1500
res = [{"group": "apps", "version": "v1", "kind": "Deployment", "namespace": "karabu",
        "name": f"r{i}", "status": "Synced", "health": {"status": "Healthy", "message": msg}}
       for i in range(250)]
sync = [{"group": "apps", "version": "v1", "kind": "Deployment", "namespace": "karabu",
         "name": f"r{i}", "status": "Synced", "message": msg, "syncPhase": "Sync"}
        for i in range(250)]
hist = [{"id": i, "revision": f"{i:040x}", "deployedAt": "2026-10-11T00:00:00Z",
         "source": {"repoURL": "https://github.com/mctlhq/mctl-gitops.git", "path": "p", "targetRevision": "main"}}
        for i in range(10)]
print(json.dumps({"status": {
    "resources": res, "history": hist,
    "sync": {"status": "Synced", "revision": "0" * 40},
    "health": {"status": "Healthy"},
    "operationState": {"phase": "Succeeded", "message": msg, "startedAt": "2026-10-11T00:00:00Z",
                       "operation": {"sync": {"revision": "0" * 40}},
                       "syncResult": {"revision": "0" * 40, "resources": sync}}}}))
PY
for app in karabu-web shared-pg root-app; do
  kubectl patch application "$app" -n argocd --type merge --patch-file "$WORK/status.json" >/dev/null
done

# The binding is eventually consistent: wait until a known-bad delete is refused
# by the policy.
ready=0
for _ in $(seq 1 60); do
  if ! kubectl --as="$SA" -n argocd delete application root-app --dry-run=server >/dev/null 2>"$WORK/err" \
     && grep -q "$POLICY" "$WORK/err"; then
    ready=1; break
  fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "FAIL: $POLICY binding never took effect: $(cat "$WORK/err")"; exit 1; }

fail=0
# AS and POL select the identity the cases run as and the policy prefix a
# refusal must name: the tenant SA first, the platform tier further down.
AS="$SA"
POL="$POLICY"
as_sa() { # run kubectl as $AS; mutating verbs as server-side dry-runs
  case "$1" in
    get) kubectl --as="$AS" -n argocd "$@" ;;
    *)   kubectl --as="$AS" -n argocd "$@" --dry-run=server ;;
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
  elif ! grep -q "$POL" "$WORK/err"; then
    echo "FAIL deny  $what: refused, but not by $POL: $(cat "$WORK/err")"; fail=1
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
  elif ! grep -q "Forbidden\|forbidden" "$WORK/err" || grep -q "ValidatingAdmissionPolicy" "$WORK/err"; then
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

# Creates. The Role grants no create, and the API server checks create for a
# server-side apply that would create the object, so RBAC refuses it today.
cat > "$WORK/new-app.yaml" <<'YAML'
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: karabu-new
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://example.invalid/x.git
    path: .
    targetRevision: HEAD
  destination:
    server: https://kubernetes.default.svc
    namespace: karabu
YAML
rbac "server-side apply creates an Application" apply --server-side -f "$WORK/new-app.yaml"

# Refresh annotations only where the templates send them.
deny "refresh root-app" "and only on their own Applications and shared-pg" \
  annotate application root-app argocd.argoproj.io/refresh=hard --overwrite
deny "refresh another tenant's app" "and only on their own Applications and shared-pg" \
  annotate application labs-web argocd.argoproj.io/refresh=hard --overwrite
deny "refresh tenant-karabu" "and only on their own Applications and shared-pg" \
  annotate application tenant-karabu mctl.ai/refresh-ts=1 --overwrite

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
  patch application root-app --type merge -p '{"status":{"health":{"status":"Degraded"}}}'
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
cat > "$WORK/new-appset.yaml" <<'YAML'
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: karabu-new
  namespace: argocd
spec:
  generators:
    - list:
        elements: []
  template:
    metadata:
      name: x
    spec:
      project: default
      source:
        repoURL: https://example.invalid/x.git
        path: .
      destination:
        server: https://kubernetes.default.svc
YAML
rbac "server-side apply creates an ApplicationSet" apply --server-side -f "$WORK/new-appset.yaml"

# The policies refuse creates on their own, so a later widening of the Role
# does not reopen them: grant create for the duration of these two cases.
kubectl create role widened-create -n argocd --verb=create \
  --resource=applications.argoproj.io,applicationsets.argoproj.io >/dev/null
kubectl create rolebinding widened-create -n argocd --role=widened-create \
  --serviceaccount="$TENANT:argo-workflow-sa" >/dev/null
for _ in $(seq 1 30); do
  kubectl auth can-i create applications.argoproj.io -n argocd --as="$SA" >/dev/null 2>&1 && break
  sleep 1
done
deny "create an Application (Role widened)" "may not create Applications" \
  create -f "$WORK/new-app.yaml"
deny "create an ApplicationSet (Role widened)" "may not create or delete ApplicationSets" \
  create -f "$WORK/new-appset.yaml"
kubectl delete rolebinding widened-create -n argocd >/dev/null
kubectl delete role widened-create -n argocd >/dev/null

# The platform workflow tier: the tenant policies do not match it, its own do.
AS="$PLATFORM_SA"
POL="$PLATFORM_POLICY"
ready=0
for _ in $(seq 1 60); do
  if ! kubectl --as="$AS" -n argocd delete application root-app --dry-run=server >/dev/null 2>"$WORK/err" \
     && grep -q "$POL" "$WORK/err"; then
    ready=1; break
  fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "FAIL: $POL binding never took effect: $(cat "$WORK/err")"; fail=1; }

# What create-tenant, delete-tenant(-safe) and mctl-agents-shepherd send.
admit "create-tenant/shepherd: list Applications"            get applications
admit "create-tenant: get tenant-karabu"                     get application tenant-karabu
admit "create-tenant: refresh ApplicationSet tenants" \
  annotate applicationset tenants argocd.argoproj.io/refresh=hard --overwrite
admit "delete-tenant-safe: refresh ApplicationSet apps" \
  annotate applicationset apps argocd.argoproj.io/refresh=hard --overwrite
admit "refresh ApplicationSet apps with the merge patch deploy-service uses" \
  patch applicationset apps --type merge -p "$REFRESH"
admit "delete-tenant-safe: delete a service app the apps ApplicationSet generated" \
  delete application karabu-web
admit "delete-tenant-safe: delete another tenant's generated service app" \
  delete application labs-web
admit "delete-tenant: delete tenant-karabu" \
  delete application tenant-karabu
admit "delete-tenant: delete Role argo-workflow-argocd-karabu" \
  delete role argo-workflow-argocd-karabu
admit "delete-tenant: delete RoleBinding argo-workflow-argocd-karabu" \
  delete rolebinding argo-workflow-argocd-karabu
admit "orphan cleanup: delete Role argo-workflow-argocd-ttt" \
  delete role argo-workflow-argocd-ttt
admit "orphan cleanup: delete RoleBinding argo-workflow-argocd-ttt" \
  delete rolebinding argo-workflow-argocd-ttt

# Deletes of anything the tenant ApplicationSets did not generate.
DEL_APP="may only delete tenant Applications generated by the"
deny "platform: delete root-app"            "$DEL_APP" delete application root-app
deny "platform: delete shared-pg"           "$DEL_APP" delete application shared-pg
deny "platform: delete temporal (project platform)" "$DEL_APP" delete application temporal
deny "platform: delete team-labelled app outside project apps" "$DEL_APP" \
  delete application karabu-outside-apps
deny "platform: delete a service-shaped app nothing generated" "$DEL_APP" \
  delete application karabu-handmade
deny "platform: delete a tenant-shaped app nothing generated" "$DEL_APP" \
  delete application tenant-labs
DEL_RBAC="may only delete the tenant chart's argo-workflow-argocd-"
deny "platform: delete its own Role argo-workflow-argocd-sync" "$DEL_RBAC" \
  delete role argo-workflow-argocd-sync
deny "platform: delete Argo CD's Role argocd-server" "$DEL_RBAC" delete role argocd-server
deny "platform: delete a tenant-labelled RoleBinding under another name" "$DEL_RBAC" \
  delete rolebinding karabu-extra

# ApplicationSet updates beyond the refresh annotations.
deny "platform: change ApplicationSet apps' template project" \
  "may not change an ApplicationSet's spec" \
  patch applicationset apps --type merge -p '{"spec":{"template":{"spec":{"project":"default"}}}}'
deny "platform: label ApplicationSet tenants" "may not change an ApplicationSet's labels" \
  label applicationset tenants example.invalid/x=y
deny "platform: set another annotation on ApplicationSet tenants" "may only change the annotations" \
  annotate applicationset tenants argocd.argoproj.io/tracking-id=x --overwrite

# What the narrowed Role refuses before admission.
rbac "platform: patch an Application" \
  annotate application tenant-karabu argocd.argoproj.io/refresh=hard --overwrite
rbac "platform: patch ApplicationSet openclaw-skills" \
  patch applicationset openclaw-skills --type merge -p "$REFRESH"
rbac "platform: list ApplicationSets"    get applicationsets
rbac "platform: delete ApplicationSet apps" delete applicationset apps
rbac "platform: server-side apply creates an Application" apply --server-side -f "$WORK/new-app.yaml"
rbac "platform: get Roles"               get roles

# The policies refuse on their own, so a later widening of the Role does not
# reopen any of this: grant the verbs for the duration of these cases.
kubectl create role widened-platform -n argocd \
  --verb=get,create,update,patch,delete \
  --resource=applications.argoproj.io,applicationsets.argoproj.io,roles.rbac.authorization.k8s.io >/dev/null
kubectl create rolebinding widened-platform -n argocd --role=widened-platform \
  --serviceaccount="argo-workflows:argo-workflow-sa" >/dev/null
for _ in $(seq 1 30); do
  kubectl auth can-i create applications.argoproj.io -n argocd --as="$AS" >/dev/null 2>&1 && break
  sleep 1
done
deny "platform: create an Application (Role widened)" "may not create or modify Applications" \
  create -f "$WORK/new-app.yaml"
deny "platform: refresh an Application (Role widened)" "may not create or modify Applications" \
  annotate application tenant-karabu argocd.argoproj.io/refresh=hard --overwrite
deny "platform: create an ApplicationSet (Role widened)" "may not create or delete ApplicationSets" \
  create -f "$WORK/new-appset.yaml"
deny "platform: delete ApplicationSet apps (Role widened)" "may not create or delete ApplicationSets" \
  delete applicationset apps
deny "platform: refresh ApplicationSet openclaw-skills (Role widened)" \
  "may only refresh the ApplicationSets apps and tenants" \
  patch applicationset openclaw-skills --type merge -p "$REFRESH"
# No rules, so RBAC's escalation check has nothing to refuse.
cat > "$WORK/new-role.yaml" <<'YAML'
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: made-by-platform
  namespace: argocd
rules: []
YAML
deny "platform: create a Role (Role widened)" "may not create or modify Roles" \
  create -f "$WORK/new-role.yaml"
kubectl delete rolebinding widened-platform -n argocd >/dev/null
kubectl delete role widened-platform -n argocd >/dev/null

exit "$fail"
