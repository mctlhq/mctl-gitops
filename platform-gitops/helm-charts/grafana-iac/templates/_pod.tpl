{{- /*
  The pod that plans and applies iac/. Shared by the PostSync Job (runs
  after every sync, so a merged change applies at once) and the CronJob
  (reconciles hourly, so a permission changed in the Grafana UI, which no
  sync sees, is reverted).
*/ -}}
{{- define "grafana-iac.podSpec" -}}
serviceAccountName: grafana-iac
restartPolicy: Never
# ghcr.io/mctlhq packages are private; ExternalSecret grafana-iac-ghcr in
# infra-components/observability/grafana-iac/externalsecret.yaml.
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
            name: grafana-iac-inputs
            key: allowed-actions
      - name: ALLOWED_DELETES
        valueFrom:
          configMapKeyRef:
            name: grafana-iac-inputs
            key: allowed-deletes
    command: ["/bin/sh", "-c"]
    args:
      - |
        set -eu
        # The Grafana server admin, for basic auth on the in-cluster Service
        # (iac/provider.tf). Read from files rather than env so the password
        # is never in the pod spec; an empty value fails the run instead of
        # sending an anonymous request.
        GRAFANA_AUTH="$(cat /grafana-admin/admin-user):$(cat /grafana-admin/admin-password)"
        case "$GRAFANA_AUTH" in :*|*:) echo "grafana-iac: the admin credential is empty; refusing"; exit 1 ;; esac
        export GRAFANA_AUTH
        # VMAuth user erpact's password for the erpact org's datasource
        # (iac/erpact.tf), as a sensitive variable: never in a plan or log.
        TF_VAR_erpact_metrics_password="$(cat /tenant-erpact/metrics-password)"
        [ -n "$TF_VAR_erpact_metrics_password" ] || { echo "grafana-iac: the erpact metrics password is empty; refusing"; exit 1; }
        export TF_VAR_erpact_metrics_password
        cp /iac-root/*.tf /iac-root/*.json /work/
        cp /iac-root/terraform.lock.hcl /work/.terraform.lock.hcl
        cd /work
        tofu init -lockfile=readonly -no-color
        set +e
        tofu plan -detailed-exitcode -out=tfplan -no-color
        rc=$?
        set -e
        if [ "$rc" = 0 ]; then echo "grafana-iac: no changes"; exit 0; fi
        if [ "$rc" != 2 ]; then echo "grafana-iac: plan failed ($rc)"; exit "$rc"; fi
        tofu show -json tfplan > plan.json
        actions="$(grep -o '"actions":\[[^]]*\]' plan.json | sed 's/^"actions"://' | grep -o '"[a-z-]*"' | tr -d '"' | sort -u)"
        if [ -z "$actions" ]; then echo "grafana-iac: could not read the plan's actions; refusing"; exit 1; fi
        for a in $actions; do
          [ "$a" = delete ] && continue
          case " $ALLOWED_ACTIONS " in
            *" $a "*) ;;
            *) echo "grafana-iac: plan contains '$a', allowed: $ALLOWED_ACTIONS; refusing to apply"; exit 1 ;;
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
          if [ "$got" != "$want" ]; then echo "grafana-iac: plan deletes $want resource(s) but $got address(es) were read; refusing"; exit 1; fi
          for d in $deletes; do
            case " $ALLOWED_DELETES " in
              *" $d "*) echo "grafana-iac: delete of $d is allowed" ;;
              *) echo "grafana-iac: plan deletes $d, allowed deletes: '$ALLOWED_DELETES'; refusing to apply"; exit 1 ;;
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
      - name: admin
        mountPath: /grafana-admin
        readOnly: true
      - name: tenant-erpact
        mountPath: /tenant-erpact
        readOnly: true
      - name: work
        mountPath: /work
      - name: tmp
        mountPath: /tmp
volumes:
  - name: root
    configMap:
      name: grafana-iac-inputs
  # Grafana's built-in admin, from Vault platform/grafana through the
  # ExternalSecret grafana-iac-admin (infra-components/observability/grafana-iac).
  # Not optional: without it the pod does not start.
  - name: admin
    secret:
      secretName: grafana-iac-admin
  # VMAuth user erpact's password (Vault platform/grafana-tenants/erpact),
  # through the ExternalSecret grafana-iac-tenant-erpact. Not optional.
  - name: tenant-erpact
    secret:
      secretName: grafana-iac-tenant-erpact
  - name: work
    emptyDir: {}
  - name: tmp
    emptyDir: {}
{{- end }}
