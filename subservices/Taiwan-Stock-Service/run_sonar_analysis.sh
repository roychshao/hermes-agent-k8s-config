#!/usr/bin/env bash
set -e

# Change directory to script location
cd "$(dirname "$0")"

# Load environment variables from .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "=========================================================="
echo "Step 1: Running unit tests and generating XML coverage report..."
echo "=========================================================="
PYTHONPATH=. /home/royshao/.local/bin/uv run python -m pytest --cov --cov-report=xml

echo "Adjusting paths in coverage.xml for Docker container compatibility..."
/home/royshao/.local/bin/uv run python -c "
import xml.etree.ElementTree as ET
tree = ET.parse('coverage.xml')
root = tree.getroot()
for source in root.findall('.//source'):
    source.text = '/usr/src'
tree.write('coverage.xml')
"


echo ""
echo "=========================================================="
echo "Step 2: Checking if SonarQube container is running..."
echo "=========================================================="
if [ "$(docker ps -q -f name=sonarqube-server)" ]; then
    echo "SonarQube server is running."
else
    echo "SonarQube server is NOT running. Starting it via Docker Compose..."
    docker compose -f docker-compose.sonar.yml up -d
    echo "Waiting for SonarQube to fully start (this may take up to 30-40 seconds)..."
    until [ "$(docker inspect -f '{{.State.Status}}' sonarqube-server)" == "running" ]; do
        sleep 2
    done
    echo "SonarQube server started. Note: SonarQube web UI (http://localhost:9000) takes a few moments to initialize."
fi

echo ""
echo "=========================================================="
echo "Step 3: Running SonarScanner CLI via Docker..."
echo "=========================================================="

ENV_FLAGS=("-e" "SONAR_HOST_URL=http://host.docker.internal:9000")
if [ -n "$SONAR_TOKEN" ]; then
    ENV_FLAGS+=("-e" "SONAR_TOKEN=$SONAR_TOKEN")
    echo "Authentication token (SONAR_TOKEN) detected."
else
    echo "No SONAR_TOKEN detected. Submitting anonymous scan."
fi

# Using --add-host to allow Linux containers to communicate with host machine's ports
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  "${ENV_FLAGS[@]}" \
  -v "$(pwd):/usr/src" \
  sonarsource/sonar-scanner-cli

echo ""
echo "=========================================================="
echo "Analysis Completed!"
echo "Open your browser and navigate to: http://localhost:9000"
echo "=========================================================="

