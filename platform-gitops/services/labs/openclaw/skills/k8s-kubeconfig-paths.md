# Kubernetes kubeconfig Paths

## k3s-preview cluster

**Path:** `/Users/dmitriimashkov/PycharmProjects/mctlhq/mctl-gitops/infrastructure/k3s-preview/kubeconfig.yaml`

**Usage:**
```bash
export KUBECONFIG=/Users/dmitriimashkov/PycharmProjects/mctlhq/mctl-gitops/infrastructure/k3s-preview/kubeconfig.yaml
kubectl get pods -n labs
```

**Quick access:**
```bash
KUBECONFIG=/Users/dmitriimashkov/PycharmProjects/mctlhq/mctl-gitops/infrastructure/k3s-preview/kubeconfig.yaml kubectl [command]
```

## Related

- Check pod status: `kubectl get pods -n labs -o wide`
- View pod logs: `kubectl logs -n labs <pod-name>`
- Describe pod: `kubectl describe pod -n labs <pod-name>`
