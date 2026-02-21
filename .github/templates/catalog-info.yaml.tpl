apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: __SERVICE_NAME__
  description: "__SERVICE_NAME__ service deployed to preview"
  annotations:
    backstage.io/kubernetes-id: __SERVICE_NAME__
    backstage.io/kubernetes-namespace: preview
    argocd/app-name: preview-__TEAM_NAME__-__SERVICE_NAME__
    github.com/source-repo: __DOCKERFILE_REPO__
  links:
    - url: https://argocd-preview.mctl.me/applications/argocd/preview-__TEAM_NAME__-__SERVICE_NAME__
      title: ArgoCD
      icon: dashboard
    - url: https://github.com/__DOCKERFILE_REPO__
      title: Source Repository
      icon: github
    - url: https://github.com/dmitriimashkov/mctl.me/actions/workflows/release-service.yml
      title: GitHub Actions
      icon: github
  labels:
    team: __TEAM_NAME__
    env: preview
spec:
  type: __COMPONENT_TYPE__
  lifecycle: production
  owner: group:__TEAM_NAME__
  system: team-__TEAM_NAME__
