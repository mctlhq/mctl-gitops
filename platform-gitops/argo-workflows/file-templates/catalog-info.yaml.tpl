apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: __SERVICE_NAME__
  namespace: __TEAM_NAME__
  description: "__SERVICE_NAME__ service"
  annotations:
    backstage.io/kubernetes-label-selector: app.kubernetes.io/instance=__TEAM_NAME__-__SERVICE_NAME__
    backstage.io/kubernetes-id: __SERVICE_NAME__
    backstage.io/kubernetes-namespace: __TEAM_NAME__
    argocd/app-name: __TEAM_NAME__-__SERVICE_NAME__
    github.com/source-repo: __DOCKERFILE_REPO__
    # mctl.me/auto-deploy — triggered by GitHub App webhook on tag push
    #   "true" or "auto" — deploy immediately via scaffolder
    #   "confirm"         — notify only, user deploys manually from UI
    #   "false" or absent — skip
    mctl.me/auto-deploy: "false"
  links:
    - url: https://ops.mctl.ai/applications/argocd/__TEAM_NAME__-__SERVICE_NAME__
      title: ArgoCD
      icon: dashboard
    - url: https://github.com/__DOCKERFILE_REPO__
      title: Source Repository
      icon: github
    - url: https://workflows.mctl.ai
      title: Argo Workflows
      icon: github
  labels:
    team: __TEAM_NAME__
    env: apps
spec:
  type: __COMPONENT_TYPE__
  lifecycle: production
  owner: group:default/__TEAM_NAME__
  system: system:default/team-__TEAM_NAME__
