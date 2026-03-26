apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-server
  namespace: kube-system
spec:
  template:
    spec:
      containers:
      - name: metrics-server
        resources:
          requests:
            cpu: 100m
            memory: 70Mi
          limits:
            cpu: 250m
            memory: 192Mi
