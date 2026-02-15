apiVersion: batch/v1
kind: Job
metadata:
  name: vault-cleanup-__SERVICE_NAME__
  annotations:
    argocd.argoproj.io/hook: PreDelete
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  ttlSecondsAfterFinished: 300
  backoffLimit: 3
  template:
    metadata:
      name: vault-cleanup
    spec:
      serviceAccountName: vault-cleanup
      restartPolicy: Never
      containers:
      - name: cleanup
        image: hashicorp/vault:1.15
        env:
        - name: VAULT_ADDR
          value: "https://vault-preview.mctl.me"
        - name: VAULT_TOKEN
          valueFrom:
            secretKeyRef:
              name: vault-token
              key: token
        - name: TEAM
          value: "__TEAM_NAME__"
        - name: SERVICE
          value: "__SERVICE_NAME__"
        command:
        - sh
        - -c
        - |
          set -e
          echo "🧹 Cleaning up Vault secrets for ${TEAM}/${SERVICE}"
          
          # Delete all secrets for this service
          vault kv metadata delete secret/preview/${TEAM}/${SERVICE} 2>/dev/null && echo "  ✅ Deleted secret/preview/${TEAM}/${SERVICE}" || echo "  ℹ️  No main secrets found"
          vault kv metadata delete secret/preview/${TEAM}/${SERVICE}/repo-pat 2>/dev/null && echo "  ✅ Deleted repo-pat" || echo "  ℹ️  No repo-pat found"
          
          echo "✅ Vault cleanup completed for ${TEAM}/${SERVICE}"
