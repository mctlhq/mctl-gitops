# Tasks: incident-1e0f735d

1. [ ] Locate the ArgoCD Helm values file in platform-gitops that configures
       the applicationset-controller (e.g. under an `infrastructure/argocd/`
       chart-values path), and find the current CPU request/limit for that
       component.
2. [ ] Increase the CPU limit for applicationset-controller (e.g. double the
       current value) and raise the CPU request proportionally, to resolve
       the CPUThrottlingHigh alert.
3. [ ] Verify the edited YAML is well-formed and consistent with the
       conventions used elsewhere in the same values file (units, indentation,
       existing request:limit ratios for sibling components).
4. [ ] No image tag bump needed — this is a config-only resource limit
       change.
