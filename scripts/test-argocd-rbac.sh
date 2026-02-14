#!/bin/bash
# Test ArgoCD RBAC configuration for preview.mctl.me cluster
# Run this after connecting to the preview cluster

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BOLD}=== ArgoCD RBAC Configuration Test ===${NC}"
echo ""

# Check we're on the right cluster
CLUSTER_URL=$(kubectl config current-context)
echo -e "${BOLD}1. Current cluster context:${NC} $CLUSTER_URL"
ARGOCD_URL=$(kubectl get configmap argocd-cm -n argocd -o jsonpath='{.data.url}' 2>/dev/null || echo "N/A")
echo -e "${BOLD}   ArgoCD URL:${NC} $ARGOCD_URL"
echo ""

if [[ "$ARGOCD_URL" != *"preview.mctl.me"* ]]; then
    echo -e "${RED}⚠️  Warning: You're not on the preview.mctl.me cluster!${NC}"
    echo -e "${YELLOW}   Expected ArgoCD URL to contain 'preview.mctl.me'${NC}"
    echo -e "${YELLOW}   Current URL: $ARGOCD_URL${NC}"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if argocd-rbac-cm ConfigMap exists
echo -e "${BOLD}2. Checking RBAC ConfigMap...${NC}"
if kubectl get configmap argocd-rbac-cm -n argocd &>/dev/null; then
    echo -e "   ${GREEN}✓${NC} ConfigMap argocd-rbac-cm exists"

    # Check if it's managed by Helm or GitOps
    MANAGED_BY=$(kubectl get configmap argocd-rbac-cm -n argocd -o jsonpath='{.metadata.labels.app\.kubernetes\.io/managed-by}' 2>/dev/null || echo "unknown")
    echo -e "   ${BOLD}Managed by:${NC} $MANAGED_BY"

    if [[ "$MANAGED_BY" == "Helm" ]]; then
        echo -e "   ${YELLOW}⚠️  ConfigMap is managed by Helm (from Terraform)${NC}"
        echo -e "   ${YELLOW}   Need to apply argocd.yaml to enable GitOps management${NC}"
    fi
else
    echo -e "   ${RED}✗${NC} ConfigMap argocd-rbac-cm NOT found"
fi
echo ""

# Check current RBAC policies
echo -e "${BOLD}3. Current RBAC Policies:${NC}"
POLICIES=$(kubectl get configmap argocd-rbac-cm -n argocd -o jsonpath='{.data.policy\.csv}' 2>/dev/null || echo "")
if [[ -n "$POLICIES" ]]; then
    echo "$POLICIES" | grep -E "^(p|g)," | head -20
else
    echo -e "   ${RED}✗${NC} No policies found"
fi
echo ""

# Check for expected teams
echo -e "${BOLD}4. Team Mappings Check:${NC}"
declare -a EXPECTED_TEAMS=("dmitriimashkov:admin" "dmitriimashkov:libertex" "dmitriimashkov:internal")
for team in "${EXPECTED_TEAMS[@]}"; do
    if echo "$POLICIES" | grep -q "g, $team,"; then
        ROLE=$(echo "$POLICIES" | grep "g, $team," | awk -F', ' '{print $3}')
        echo -e "   ${GREEN}✓${NC} Team $team → $ROLE"
    else
        echo -e "   ${RED}✗${NC} Team $team NOT found"
    fi
done
echo ""

# Check if argocd-self-managed Application exists
echo -e "${BOLD}5. Self-Managed ArgoCD Application:${NC}"
if kubectl get application argocd-self-managed -n argocd &>/dev/null; then
    STATUS=$(kubectl get application argocd-self-managed -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "unknown")
    HEALTH=$(kubectl get application argocd-self-managed -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null || echo "unknown")
    echo -e "   ${GREEN}✓${NC} Application argocd-self-managed exists"
    echo -e "   ${BOLD}Sync Status:${NC} $STATUS"
    echo -e "   ${BOLD}Health Status:${NC} $HEALTH"
else
    echo -e "   ${RED}✗${NC} Application argocd-self-managed NOT found"
    echo -e "   ${YELLOW}   Run: kubectl apply -f platform-gitops/apps/templates/argocd.yaml${NC}"
fi
echo ""

# Check ExternalSecrets for repo credentials
echo -e "${BOLD}6. Repository Authentication (ExternalSecrets):${NC}"
if kubectl get externalsecret -n argocd &>/dev/null; then
    kubectl get externalsecret -n argocd -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[0].type,READY:.status.conditions[0].status 2>/dev/null | grep -E "argocd-repo|NAME"
else
    echo -e "   ${YELLOW}⚠️  ExternalSecrets CRD not found${NC}"
fi
echo ""

# Check repository secrets
echo -e "${BOLD}7. Repository Secrets:${NC}"
for secret in argocd-repo-mctl-me argocd-repo-creds-github-https; do
    if kubectl get secret $secret -n argocd &>/dev/null; then
        HAS_PASSWORD=$(kubectl get secret $secret -n argocd -o jsonpath='{.data.password}' 2>/dev/null)
        if [[ -n "$HAS_PASSWORD" ]]; then
            echo -e "   ${GREEN}✓${NC} Secret $secret has password field"
        else
            echo -e "   ${RED}✗${NC} Secret $secret missing password field"
        fi
    else
        echo -e "   ${RED}✗${NC} Secret $secret NOT found"
    fi
done
echo ""

# Check Applications status
echo -e "${BOLD}8. Applications Status:${NC}"
kubectl get application -n argocd -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status 2>/dev/null | head -10
echo ""

# Summary
echo -e "${BOLD}=== Summary ===${NC}"
echo ""
echo "Next steps:"
echo ""
if ! kubectl get application argocd-self-managed -n argocd &>/dev/null; then
    echo -e "1. ${YELLOW}Apply self-managed ArgoCD Application:${NC}"
    echo "   kubectl apply -f platform-gitops/apps/templates/argocd.yaml"
    echo ""
fi

if [[ "$MANAGED_BY" == "Helm" ]]; then
    echo -e "2. ${YELLOW}RBAC ConfigMap is still managed by Helm${NC}"
    echo "   After applying argocd.yaml, ArgoCD will take over management"
    echo ""
fi

echo -e "3. ${GREEN}Test RBAC with user login:${NC}"
echo "   argocd login argocd-preview.mctl.me"
echo "   argocd app list"
echo ""

echo -e "4. ${GREEN}Watch ArgoCD sync:${NC}"
echo "   kubectl get application argocd-self-managed -n argocd -w"
echo ""

echo "Done!"
