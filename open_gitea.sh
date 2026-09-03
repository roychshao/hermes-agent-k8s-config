#!/usr/bin/env bash
# Script to port-forward Gitea Web UI
echo "=================================================="
echo " Starting port-forward for Gitea Web UI..."
echo " Open your browser and navigate to: http://localhost:3000"
echo " (Press Ctrl+C to stop)"
echo "=================================================="
while true; do
    kubectl port-forward -n roychshao svc/gitea-service 3000:3000
    echo "[*] Port-forward stream closed. Reconnecting in 1s..."
    sleep 1
done
