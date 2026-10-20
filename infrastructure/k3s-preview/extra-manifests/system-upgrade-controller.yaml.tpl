# The full system-upgrade-controller Deployment, not a partial patch.
#
# kube-hetzner applies upstream's system-upgrade-controller.yaml (which sets no
# resources) with `kubectl apply -k`, so the live object carries a complete
# last-applied-configuration. A partial Deployment like
# metrics-server-resources-patch.yaml.tpl would replace that annotation, and
# kubectl's three-way merge would then delete every field the patch leaves out:
# the affinity, tolerations, env, volumes and security context. metrics-server
# gets away with it because k3s deploys it without that annotation.
#
# This is upstream's Deployment for local.sys_upgrade_controller_version with the
# module's kustomize/system-upgrade-controller.yaml patch merged in (the
# ca-certificates hostPath goes first, where the strategic merge puts it), plus
# resources. Bump it together with local.sys_upgrade_controller_version and
# re-diff it against upstream's release manifest and the module's patch.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: system-upgrade-controller
  namespace: system-upgrade
  annotations:
    # Hash of the module kustomization inputs (kube.tf, base_kustomization_inputs).
    # It changes whenever the module re-applies upstream's Deployment, which
    # has no resources, so this manifest re-applies in the same run and wins.
    mctl.ai/base-kustomization-inputs: "${base_kustomization_inputs}"
spec:
  selector:
    matchLabels:
      upgrade.cattle.io/controller: system-upgrade-controller
  strategy:
    type: Recreate
  template:
    metadata:
      labels:
        app.kubernetes.io/component: controller
        app.kubernetes.io/name: system-upgrade-controller
        upgrade.cattle.io/controller: system-upgrade-controller
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: node-role.kubernetes.io/control-plane
                operator: Exists
              - key: kubernetes.io/os
                operator: In
                values:
                - linux
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values:
                - system-upgrade-controller
            topologyKey: kubernetes.io/hostname
      containers:
      - env:
        - name: SYSTEM_UPGRADE_CONTROLLER_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.labels['upgrade.cattle.io/controller']
        - name: SYSTEM_UPGRADE_CONTROLLER_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        - name: SYSTEM_UPGRADE_CONTROLLER_NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        envFrom:
        - configMapRef:
            name: default-controller-env
        image: rancher/system-upgrade-controller:${sys_upgrade_controller_version}
        imagePullPolicy: IfNotPresent
        name: system-upgrade-controller
        # 7-day peak working set 76Mi and CPU 1.5m on 2026-10-20; upstream sets
        # nothing. No CPU limit, matching the CCM: throttling it only delays
        # upgrade jobs.
        resources:
          requests:
            cpu: 10m
            memory: 96Mi
          limits:
            memory: 192Mi
        securityContext:
          allowPrivilegeEscalation: false
          capabilities:
            drop:
            - ALL
          runAsGroup: 65534
          runAsNonRoot: true
          runAsUser: 65534
          seccompProfile:
            type: RuntimeDefault
        volumeMounts:
        - mountPath: /var/lib/ca-certificates
          name: ca-certificates
        - mountPath: /etc/ssl
          name: etc-ssl
          readOnly: true
        - mountPath: /etc/pki
          name: etc-pki
          readOnly: true
        - mountPath: /etc/ca-certificates
          name: etc-ca-certificates
          readOnly: true
        - mountPath: /tmp
          name: tmp
      serviceAccountName: system-upgrade
      tolerations:
      - key: CriticalAddonsOnly
        operator: Exists
      - effect: NoSchedule
        key: node-role.kubernetes.io/master
        operator: Exists
      - effect: NoSchedule
        key: node-role.kubernetes.io/controlplane
        operator: Exists
      - effect: NoSchedule
        key: node-role.kubernetes.io/control-plane
        operator: Exists
      - effect: NoExecute
        key: node-role.kubernetes.io/etcd
        operator: Exists
      volumes:
      - hostPath:
          path: /var/lib/ca-certificates
          type: Directory
        name: ca-certificates
      - hostPath:
          path: /etc/ssl
          type: DirectoryOrCreate
        name: etc-ssl
      - hostPath:
          path: /etc/pki
          type: DirectoryOrCreate
        name: etc-pki
      - hostPath:
          path: /etc/ca-certificates
          type: DirectoryOrCreate
        name: etc-ca-certificates
      - emptyDir: {}
        name: tmp
