apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: __SERVICE_NAME__
  description: "__SERVICE_NAME__ service deployed to preview"
  annotations:
    backstage.io/kubernetes-id: __SERVICE_NAME__
    argocd/app-name: preview-__TEAM_NAME__-__SERVICE_NAME__
    github.com/source-repo: __DOCKERFILE_REPO__
  labels:
    team: __TEAM_NAME__
    env: preview
spec:
  type: __COMPONENT_TYPE__
  lifecycle: production
  owner: group:__TEAM_NAME__
  system: team-__TEAM_NAME__
