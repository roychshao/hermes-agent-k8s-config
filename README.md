# Hermes Agent Kubernetes Deployment

This repository contains the Kubernetes configuration files and custom build-time patches for deploying [Hermes Agent](https://github.com/NousResearch/Hermes-Agent). It provides a secure, self-healing, and extensible agent architecture on Kubernetes.

---

## 📐 Cluster Architecture

The following diagram illustrates the network flow and service communication within the cluster.

```mermaid
graph TD
    User_Platform([User on Discord / Slack / Telegram]) <-->|Voice/Text Chat| Gateway_APIs[Platform Gateway APIs]
    User_Admin([Admin via WebUI / Dashboard]) <-->|Kubernetes Port-Forward| Agent[Hermes Agent Gateway]
    
    Gateway_APIs <-->|Websocket / Webhook| Agent
    
    subgraph Namespace_roychshao [Namespace: roychshao]
        direction TB
        subgraph Pod_Hermes [hermes-agent Pod]
            Agent
        end
        
        PVC[(Persistent Volume Claim <br> /opt/data)]
        Postgres[(PostgreSQL Pod <br> database for stock portfolio)]
        StockService[taiwan-stock-service Pod <br> MCP SSE Server]
        
        Agent <-->|Stores SQLite DB, Workspace, & Session Cache| PVC
        StockService <-->|Stores Portfolio Data| Postgres
        Agent <-->|MCP over HTTP/SSE| StockService
    end
    
    subgraph Other_Namespaces [Shared Cluster Services]
        LiteLLM[litellm-service Pod <br> GPU Inference Service]
    end
    
    Agent <-->|LLM Inference API| LiteLLM
```

---

## 📂 Repository Structure

```text
.
├── Dockerfile.hermes-agent      # Custom Dockerfile for building the patched agent
├── deploy.sh                    # One-click script to build, push, and deploy all services
├── open_dashboard.sh            # Port-forwarding helper for the Hermes Dashboard (Port: 9119)
├── open_webui.sh                # Port-forwarding helper for the Hermes WebUI (Port: 8787)
├── patch_discord_status.py      # Patches 1 & 2: Discord presence status & typing indicator fixes
├── patch_voice_playback.py      # Patch 3: Voice channel audio routing fix
├── patch_voice_temp_paths.py    # Patch 4: Safe-write roots (/tmp path bypass) fix
├── subservices/                 # Extensible directory for custom code & tools
│   └── Taiwan-Stock-Service/    # Example sub-service (exposed as an MCP server)
└── k8s/                         # Kubernetes deployment resources
    ├── configmap.yaml           # Configs (LLM models, API endpoints, home directory)
    ├── deployment.yaml          # Pod specification for the main agent
    ├── pvc.yaml                 # Persistent Volume Claim for agent workspace & cache
    ├── rbac.yaml                # Service Account for agent permissions
    ├── service.yaml             # Service port declarations
    ├── postgres.yaml            # PostgreSQL database deployment
    └── taiwan-stock-service.yaml # Taiwan Stock Service deployment
```

---

## 🔌 Extending the Agent with Custom Code (`subservices/`)

If you want to add your own custom code, tools, or services to the agent, follow these steps:

1. **Add Code to `subservices/`**:
   Create a new sub-folder under the [`subservices/`](file:///home/royshao/hermes-agent/subservices) directory for your code (e.g., `subservices/my-custom-service`).

2. **Expose it as an MCP (Model Context Protocol) Server**:
   Write your service as an MCP server. The recommended approach is to expose it over **HTTP/SSE (Server-Sent Events)** using Python (e.g., `mcp-installer` or `fastapi-mcp`) or Node.js. 

3. **Deploy as a Separate Pod**:
   Create a Kubernetes deployment YAML for your service and deploy it in the cluster. This decouples your custom logic from the main agent pod and allows you to scale it independently.

4. **Register the Service in `deployment.yaml`**:
   Expose your new service via a Kubernetes `Service`. Then, update the `init-mcp-config` container inside [`k8s/deployment.yaml`](file:///home/royshao/hermes-agent/k8s/deployment.yaml#L31-L55) to automatically register your new endpoint in `/opt/data/config.yaml`:
   ```yaml
   mcp_servers:
     my-custom-service:
       url: "http://my-custom-service-svc:8000/sse"
       transport: sse
   ```
   Upon restart, the Hermes Agent will automatically discover the new tools and capabilities.

---

## 🛠️ Build-Time Patches (Why do we need them?)

Because the official upstream image `nousresearch/hermes-agent:latest` has minor bugs, we patch the code inside the container during the Docker build stage.

### 1. Discord Presence & Typing Indicator ([`patch_discord_status.py`](file:///home/royshao/hermes-agent/patch_discord_status.py))
* **Presence:** Ensures the Bot status is displayed as "Online" when connected, rather than "Offline".
* **Typing Indicator Lock:** Fixes a bug where the bot appears to be permanently "typing" on Discord. We implement a **Generation Guard (generation ID)**. When the bot receives a new input or finishes sending a response, the generation ID increments, causing the previous typing loop tasks to instantly cancel and clean up.

### 2. Voice Channel Audio Playback ([`patch_voice_playback.py`](file:///home/royshao/hermes-agent/patch_voice_playback.py))
* **Issue:** When the agent runs a voice conversation and generates audio through `text_to_speech`, the gateway by default uploads it as an attachment to the Discord text channel instead of playing it in the voice channel.
* **Fix:** Patches [`gateway/platforms/base.py`](file:///home/royshao/Codes/hermes-agent/gateway/platforms/base.py#L6880) and [`gateway/run.py`](file:///home/royshao/Codes/hermes-agent/gateway/run.py#L22981) to route output audio through `play_tts` instead of `send_voice`. This plays the response directly inside the voice channel if the bot is currently connected to it, falling back to a text-channel upload if disconnected.

### 3. Safe-Write Path Access ([`patch_voice_temp_paths.py`](file:///home/royshao/hermes-agent/patch_voice_temp_paths.py))
* **Issue:** The Gateway's Auto-TTS system and live prompt chimes (`play_ack`) were hardcoded to write files to `/tmp/hermes_voice/`. Since the agent has a strict `HERMES_WRITE_SAFE_ROOT` security rule limiting file write operations to `/opt/data`, generating speech would fail with a `protected credential or system path` write denial error.
* **Fix:** Replaces `/tmp/hermes_voice` with the standard `DEFAULT_OUTPUT_DIR` resolved from the agent's home directory (resolves to `/opt/data/cache/audio/`). This allows file synthesis to succeed within the safe write roots.

---

## 🚀 Deployment Guide

Deploying the whole cluster is fully automated. Run the one-click deploy script:

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Build and push the custom `taiwan-stock-service` image.
2. Build the patched `hermes-agent` image using [`Dockerfile.hermes-agent`](file:///home/royshao/hermes-agent/Dockerfile.hermes-agent), applying all three Python patches, and push it.
3. Clean up existing deployments in the namespace `roychshao`.
4. Apply the SealedSecrets, ConfigMap, PVC, PostgreSQL database, and all deployments in order.

---

## 🔒 Managing Secrets (Sealed Secrets)

To avoid storing plain-text API keys or passwords in Git, we use **Sealed Secrets**:

1. Write your plain-text secrets to `k8s/secrets/hermes-raw-secret.yaml` (this file is gitignored and will never be committed).
2. Run the sealing script:
   ```bash
   cd k8s/secrets
   ./seal_secrets.sh
   ```
3. This creates [`k8s/secrets/hermes-sealed-secret.yaml`](file:///home/royshao/hermes-agent/k8s/secrets/hermes-sealed-secret.yaml), which contains encrypted tokens safe to commit to your Git repository.

---

## 🎙️ How to Verify Discord Voice Mode

Once the pods are running and the bot is online on Discord:

1. Join a Discord Voice Channel.
2. Call the bot into the channel by typing:
   ```text
   /voice join
   ```
3. Talk to the bot or text it. The bot will synthesize the response and **play it directly inside the voice channel**.
4. To make the bot leave:
   ```text
   /voice leave
   ```

---

## 🔍 Useful Commands

* **Get Pod Status:**
  ```bash
  kubectl get pods -n roychshao
  ```
* **Follow Agent Container Logs:**
  ```bash
  kubectl logs -f deployment/hermes-agent -n roychshao -c hermes-agent
  ```
* **Follow Gateway Server Logs:**
  ```bash
  kubectl exec deployment/hermes-agent -n roychshao -c hermes-agent -- tail -f /opt/data/logs/gateway.log
  ```
