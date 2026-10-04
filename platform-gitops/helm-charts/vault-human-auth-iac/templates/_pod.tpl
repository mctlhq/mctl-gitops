{{- /*
  The pod that plans and applies iac/. Shared by the PostSync Job (runs
  after every sync, so a merged change applies at once) and the CronJob
  (reconciles hourly, so a change in Vault, which no sync sees, still lands,
  and console drift is reported or reverted).
*/ -}}
{{- define "vault-human-auth-iac.podSpec" -}}
serviceAccountName: vault-human-auth-iac
restartPolicy: Never
# ghcr.io/mctlhq packages are private; ExternalSecret vault-human-auth-iac-ghcr
# in infra-components/identity/vault-human-auth-iac/externalsecret.yaml.
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
            name: vault-human-auth-iac-inputs
            key: allowed-actions
      - name: ALLOWED_DELETES
        valueFrom:
          configMapKeyRef:
            name: vault-human-auth-iac-inputs
            key: allowed-deletes
      # The OIDC client and the tenant list, written by the zitadel-iac Job
      # into the Secret this namespace pre-creates (infra-components/identity/
      # vault-human-auth-iac/oidc-zitadel.yaml). None is optional: before
      # zitadel-iac has written them the pod does not start, rather than
      # planning an empty tenant list, which would read as "delete every
      # tenant group".
      - name: TF_VAR_oidc_client_id
        valueFrom:
          secretKeyRef:
            name: vault-oidc-zitadel
            key: client_id
      - name: TF_VAR_oidc_client_secret
        valueFrom:
          secretKeyRef:
            name: vault-oidc-zitadel
            key: client_secret
      - name: TF_VAR_tenants
        valueFrom:
          secretKeyRef:
            name: vault-oidc-zitadel
            key: tenants
    command: ["/bin/sh", "-c"]
    args:
      - |
        set -eu
        # The Vault login credential: this pod's ServiceAccount token, read
        # by the provider's auth_login_jwt (iac/provider.tf).
        TERRAFORM_VAULT_AUTH_JWT="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
        export TERRAFORM_VAULT_AUTH_JWT
        cp /iac-root/*.tf /work/
        cp /iac-root/terraform.lock.hcl /work/.terraform.lock.hcl
        cd /work
        tofu init -lockfile=readonly -no-color
        set +e
        tofu plan -detailed-exitcode -out=tfplan -no-color
        rc=$?
        set -e
        if [ "$rc" = 0 ]; then echo "vault-human-auth-iac: no changes"; exit 0; fi
        if [ "$rc" != 2 ]; then echo "vault-human-auth-iac: plan failed ($rc)"; exit "$rc"; fi
        tofu show -json tfplan > plan.json
        actions="$(grep -o '"actions":\[[^]]*\]' plan.json | sed 's/^"actions"://' | grep -o '"[a-z-]*"' | tr -d '"' | sort -u)"
        if [ -z "$actions" ]; then echo "vault-human-auth-iac: could not read the plan's actions; refusing"; exit 1; fi
        for a in $actions; do
          [ "$a" = delete ] && continue
          case " $ALLOWED_ACTIONS " in
            *" $a "*) ;;
            *) echo "vault-human-auth-iac: plan contains '$a', allowed: $ALLOWED_ACTIONS; refusing to apply"; exit 1 ;;
          esac
        done
        # A delete is allowed per resource address, never as an action class:
        # every address the plan destroys or replaces must be listed in
        # ALLOWED_DELETES. The count must match the JSON plan's deletes, so a
        # destroy this text parse misses is refused, not let through.
        if printf '%s\n' $actions | grep -qx delete; then
          tofu show -no-color tfplan > plan.txt
          deletes="$(sed -n -E 's/^  # ([^ ]+) (will be destroyed|must be replaced|is tainted, so must be replaced|will be replaced, as requested)$/\1/p' plan.txt | sort -u)"
          want="$(grep -o '"actions":\[[^]]*"delete"[^]]*\]' plan.json | wc -l | tr -d ' ')"
          got="$(printf '%s' "$deletes" | grep -c . || true)"
          if [ "$got" != "$want" ]; then echo "vault-human-auth-iac: plan deletes $want resource(s) but $got address(es) were read; refusing"; exit 1; fi
          for d in $deletes; do
            case " $ALLOWED_DELETES " in
              *" $d "*) echo "vault-human-auth-iac: delete of $d is allowed" ;;
              *) echo "vault-human-auth-iac: plan deletes $d, allowed deletes: '$ALLOWED_DELETES'; refusing to apply"; exit 1 ;;
            esac
          done
        fi
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
      - name: work
        mountPath: /work
      - name: tmp
        mountPath: /tmp
volumes:
  - name: root
    configMap:
      name: vault-human-auth-iac-inputs
  - name: work
    emptyDir: {}
  - name: tmp
    emptyDir: {}
{{- end }}
