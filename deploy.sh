#!/usr/bin/env bash
set -e

# Build and push the latest Taiwan Stock Service image
echo "=========================================================="
echo "Building and pushing taiwan-stock-service Docker image..."
echo "=========================================================="
docker build -t roychshao/taiwan-stock-service:latest ./subservices/Taiwan-Stock-Service
docker push roychshao/taiwan-stock-service:latest

# Build and push the latest custom hermes-agent image
echo "=========================================================="
echo "Building and pushing custom hermes-agent Docker image..."
echo "=========================================================="
docker build -t roychshao/hermes-agent:latest -f Dockerfile.hermes-agent .
docker push roychshao/hermes-agent:latest


# Delete all deployments in the namespace (excluding persistence/PVCs/Secrets/CMs)
echo "=========================================================="
echo "Clearing all existing deployments in namespace roychshao..."
echo "=========================================================="
kubectl delete deployments --all -n roychshao --ignore-not-found=true

# Wait a few seconds for resources to clean up
echo "Waiting for deployments to terminate..."
sleep 5

echo "=========================================================="
echo "Re-deploying resources..."
echo "=========================================================="
kubectl apply -f ./k8s/secrets/hermes-sealed-secret.yaml
kubectl apply -f ./k8s/rbac.yaml
kubectl apply -f ./k8s/configmap.yaml
kubectl apply -f ./k8s/pvc.yaml
kubectl apply -f ./k8s/postgres.yaml
kubectl apply -f ./k8s/gitea.yaml
kubectl apply -f ./k8s/taiwan-stock-service.yaml
kubectl apply -f ./k8s/deployment.yaml
kubectl apply -f ./k8s/service.yaml

echo "=========================================================="
echo "Deployment completed successfully!"
echo "=========================================================="
