#!/usr/bin/env bash
# Helper script to create Gitea user accounts for Hermes Agents
set -e

NAMESPACE="roychshao"
DEFAULT_PASSWORD="${GITEA_DEFAULT_PASSWORD:-hermes123}"

create_user() {
    local username="$1"
    local password="${2:-$username}"
    local email="${username}@hermes.local"
    
    echo "Creating Gitea user: ${username} (password: ${password}, email: ${email})..."
    kubectl exec deployment/gitea -n "$NAMESPACE" -c gitea -- \
        su-exec git gitea admin user create \
        --config /data/gitea/conf/app.ini \
        --work-path /data/gitea \
        --username "$username" \
        --password "$password" \
        --email "$email" \
        --must-change-password=false || true
}

if [ $# -eq 0 ]; then
    echo "=========================================================="
    echo " Batch creating accounts for standard Hermes Agent Profiles"
    echo " Default Password rule: password == username"
    echo "=========================================================="
    AGENTS=(
        "dev-architech"
        "dev-backend"
        "dev-frontend"
        "dev-reviewer"
        "dev-ops"
        "dev-tester"
        "dev-pm"
    )
    for agent in "${AGENTS[@]}"; do
        create_user "$agent" "$agent"
    done
else
    # Custom user creation: ./create_agent_users.sh <username> [password]
    USERNAME="$1"
    PASSWORD="${2:-$USERNAME}"
    create_user "$USERNAME" "$PASSWORD"
fi

echo "=========================================================="
echo " Current Gitea Users:"
echo "=========================================================="
kubectl exec deployment/gitea -n "$NAMESPACE" -c gitea -- \
    su-exec git gitea admin user list \
    --config /data/gitea/conf/app.ini \
    --work-path /data/gitea
