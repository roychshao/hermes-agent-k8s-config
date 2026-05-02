kubectl apply -f ./k8s/secrets/hermes-sealed-secret.yaml
kubectl apply -f ./k8s/rbac.yaml
kubectl apply -f ./k8s/configmap.yaml
kubectl apply -f ./k8s/pvc.yaml
kubectl apply -f ./k8s/deployment.yaml
kubectl apply -f ./k8s/service.yaml
