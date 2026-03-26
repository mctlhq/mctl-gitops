apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kured
rules:
- apiGroups: [""]
  resources: ["nodes"]
  verbs: ["get", "patch"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["list", "delete", "get"]
- apiGroups: ["apps"]
  resources: ["daemonsets"]
  verbs: ["get"]
- apiGroups: [""]
  resources: ["pods/eviction"]
  verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kured
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kured
subjects:
- kind: ServiceAccount
  name: kured
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: kured
  namespace: kube-system
rules:
- apiGroups: ["apps"]
  resources: ["daemonsets"]
  resourceNames: ["kured"]
  verbs: ["update"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: kured
  namespace: kube-system
subjects:
- kind: ServiceAccount
  name: kured
  namespace: kube-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: kured
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: kured
  namespace: kube-system
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: kured
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: kured
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        name: kured
    spec:
      serviceAccountName: kured
      tolerations:
      - key: node-role.kubernetes.io/control-plane
        effect: NoSchedule
      - key: node-role.kubernetes.io/master
        effect: NoSchedule
      hostPID: true
      restartPolicy: Always
      volumes:
      - name: sentinel
        hostPath:
          path: /var/run
          type: Directory
      containers:
      - name: kured
        image: ghcr.io/kubereboot/kured:1.21.0
        imagePullPolicy: IfNotPresent
        securityContext:
          privileged: true
          readOnlyRootFilesystem: true
        ports:
        - containerPort: 8080
          name: metrics
        env:
        - name: KURED_NODE_ID
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        resources:
          requests:
            cpu: 25m
            memory: 64Mi
          limits:
            cpu: 100m
            memory: 128Mi
        volumeMounts:
        - mountPath: /sentinel
          name: sentinel
          readOnly: true
        command:
        - /usr/bin/kured
        - --period=5m
        - --post-reboot-node-labels=kured=done
        - --pre-reboot-node-labels=kured=rebooting
        - --reboot-command=/usr/bin/systemctl reboot
        - --reboot-sentinel=/sentinel/reboot-required
