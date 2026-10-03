{{- /*
  The pod that plans and applies iac/. Shared by the PostSync Job (runs
  after every sync, so a merged change applies at once) and the CronJob
  (reconciles hourly, so a change in Vault, which no sync sees, still lands,
  and console drift is reported or reverted).
*/ -}}
{{- define "zitadel-iac.podSpec" -}}
serviceAccountName: zitadel-iac
restartPolicy: Never
# ghcr.io/mctlhq packages are private; ExternalSecret zitadel-ghcr in
# infra-components/identity/zitadel/externalsecret.yaml.
imagePullSecrets:
  - name: ghcr-credentials
securityContext:
  runAsNonRoot: true
  runAsUser: 65532
  runAsGroup: 65532
  fsGroup: 65532
  seccompProfile:
    type: RuntimeDefault
containers:
  - name: tofu
    image: "{{ .Values.image.repository }}{{ with .Values.image.tag }}:{{ . }}{{ end }}@{{ .Values.image.digest }}"
    env:
      - name: HOME
        value: /work
      - name: ALLOWED_ACTIONS
        valueFrom:
          configMapKeyRef:
            name: zitadel-iac-inputs
            key: allowed-actions
      # Tenant users and the SMTP password come from Vault through the
      # ExternalSecrets in infra-components/identity/zitadel. Neither is
      # optional: a missing Secret fails the pod rather than planning an
      # empty tenant list, which would read as "delete every tenant".
      - name: TF_VAR_tenant_users
        valueFrom:
          secretKeyRef:
            name: zitadel-iac-users
            key: users.json
      - name: TF_VAR_smtp_password
        valueFrom:
          secretKeyRef:
            name: zitadel-iac-smtp
            key: password
    command: ["/bin/sh", "-c"]
    args:
      - |
        set -eu
        cp /iac-root/*.tf /work/
        cp /iac-root/terraform.lock.hcl /work/.terraform.lock.hcl
        cd /work
        tofu init -lockfile=readonly -no-color
        set +e
        tofu plan -detailed-exitcode -out=tfplan -no-color
        rc=$?
        set -e
        if [ "$rc" = 0 ]; then echo "zitadel-iac: no changes"; exit 0; fi
        if [ "$rc" != 2 ]; then echo "zitadel-iac: plan failed ($rc)"; exit "$rc"; fi
        tofu show -json tfplan > plan.json
        actions="$(grep -o '"actions":\[[^]]*\]' plan.json | sed 's/^"actions"://' | grep -o '"[a-z-]*"' | tr -d '"' | sort -u)"
        if [ -z "$actions" ]; then echo "zitadel-iac: could not read the plan's actions; refusing"; exit 1; fi
        for a in $actions; do
          case " $ALLOWED_ACTIONS " in
            *" $a "*) ;;
            *) echo "zitadel-iac: plan contains '$a', allowed: $ALLOWED_ACTIONS; refusing to apply"; exit 1 ;;
          esac
        done
        tofu apply -no-color tfplan
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop: ["ALL"]
    resources:
      requests:
        cpu: 50m
        memory: 128Mi
      limits:
        memory: 512Mi
    volumeMounts:
      - name: root
        mountPath: /iac-root
        readOnly: true
      - name: key
        mountPath: /iac-key
        readOnly: true
      - name: work
        mountPath: /work
      - name: tmp
        mountPath: /tmp
volumes:
  - name: root
    configMap:
      name: zitadel-iac-inputs
  - name: key
    secret:
      secretName: zitadel-iac-key
      items:
        - key: tls.key
          path: tls.key
  - name: work
    emptyDir: {}
  - name: tmp
    emptyDir: {}
{{- end }}
