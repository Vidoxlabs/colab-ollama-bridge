#!/usr/bin/env bash
# Colab Ollama Bridge — Idempotent Headless & Notebook Bootstrap Entrypoint
# Securely initializes Ollama, auth proxy, and Cloudflare Tunnel on Colab or Linux GPU hosts.
set -euo pipefail

# Ensure set -x is disabled to protect credentials
set +x

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- Configuration & Defaults ---
BRIDGE_BIND="${BRIDGE_BIND:-127.0.0.1:11435}"
OLLAMA_BIND="${OLLAMA_BIND:-127.0.0.1:11434}"
BRIDGE_STATE_DIR="${BRIDGE_STATE_DIR:-/tmp/bridge_state}"
BRIDGE_MODE="${BRIDGE_MODE:-auto}" # auto, named, quick
ENABLE_EMBEDDINGS="${ENABLE_EMBEDDINGS:-false}"
MODEL_OVERRIDE="${MODEL_OVERRIDE:-}"
OLLAMA_CONTEXT_LENGTH="${OLLAMA_CONTEXT_LENGTH:-}"
SKIP_SUPERVISE="${SKIP_SUPERVISE:-false}"

mkdir -p "$BRIDGE_STATE_DIR"
chmod 0700 "$BRIDGE_STATE_DIR"

cleanup() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    echo "[ERROR] [STAGE:${CURRENT_STAGE:-unknown}] Bootstrap failed with exit code $exit_code." >&2
  fi
}
trap cleanup EXIT

log_stage() {
  CURRENT_STAGE="$1"
  echo "==> [STAGE:$CURRENT_STAGE] $2"
}

# --- STAGE: Preflight ---
log_stage "preflight" "Validating environment and credentials"

# 1. GPU Presence Check
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "[ERROR] [STAGE:preflight] No NVIDIA GPU detected (nvidia-smi not found)." >&2
  echo "[ERROR] If running in Google Colab, select: Runtime > Change runtime type > T4 / L4 / A100 GPU." >&2
  exit 1
fi

if ! nvidia-smi >/dev/null 2>&1; then
  echo "[ERROR] [STAGE:preflight] nvidia-smi failed or no NVIDIA GPU device is visible." >&2
  exit 1
fi

# 2. Bridge API Key Resolution & Validation
API_KEY=""
if [[ -n "${BRIDGE_API_KEY_FILE:-}" && -f "$BRIDGE_API_KEY_FILE" ]]; then
  API_KEY=$(<"$BRIDGE_API_KEY_FILE")
elif [[ -n "${BRIDGE_API_KEY:-}" ]]; then
  API_KEY="$BRIDGE_API_KEY"
elif [[ -t 0 ]]; then
  read -r -s -p "Enter BRIDGE_API_KEY (min 16 chars): " API_KEY
  echo ""
else
  echo "[ERROR] [STAGE:preflight] BRIDGE_API_KEY or BRIDGE_API_KEY_FILE is required." >&2
  exit 1
fi

# Sanitize & Validate Key
API_KEY=$(echo "$API_KEY" | tr -d '\r\n')
if [[ -z "$API_KEY" ]]; then
  echo "[ERROR] [STAGE:preflight] BRIDGE_API_KEY is empty." >&2
  exit 1
fi

if [[ ${#API_KEY} -lt 16 ]]; then
  echo "[ERROR] [STAGE:preflight] BRIDGE_API_KEY is too short (minimum 16 characters required)." >&2
  exit 1
fi

if [[ "$API_KEY" =~ [[:space:]] ]]; then
  echo "[ERROR] [STAGE:preflight] BRIDGE_API_KEY must not contain whitespace." >&2
  exit 1
fi

KNOWN_EXAMPLES=("example" "test" "your-api-key" "sk-example" "placeholder" "1234567890123456" "password12345678")
for ex in "${KNOWN_EXAMPLES[@]}"; do
  if [[ "$API_KEY" == "$ex" ]]; then
    echo "[ERROR] [STAGE:preflight] Known example/insecure BRIDGE_API_KEY rejected." >&2
    exit 1
  fi
done

# Save key securely to mode 0600 file and unset from env
API_KEY_FILE="$BRIDGE_STATE_DIR/bridge_api.key"
printf "%s" "$API_KEY" > "$API_KEY_FILE"
chmod 0600 "$API_KEY_FILE"
export BRIDGE_API_KEY_FILE="$API_KEY_FILE"
unset BRIDGE_API_KEY
unset API_KEY

# 3. Tunnel Token & Mode Determination
ACTIVE_MODE="$BRIDGE_MODE"
TOKEN_FILE=""

if [[ -n "${TUNNEL_TOKEN_FILE:-}" && -f "$TUNNEL_TOKEN_FILE" ]]; then
  TOKEN_FILE="$TUNNEL_TOKEN_FILE"
elif [[ -n "${TUNNEL_TOKEN:-}" ]]; then
  TOKEN_FILE="$BRIDGE_STATE_DIR/tunnel_token.token"
  printf "%s" "$TUNNEL_TOKEN" > "$TOKEN_FILE"
  chmod 0600 "$TOKEN_FILE"
  export TUNNEL_TOKEN_FILE="$TOKEN_FILE"
  unset TUNNEL_TOKEN
fi

if [[ "$ACTIVE_MODE" == "auto" ]]; then
  if [[ -n "$TOKEN_FILE" ]]; then
    ACTIVE_MODE="named"
  else
    ACTIVE_MODE="quick"
  fi
elif [[ "$ACTIVE_MODE" == "named" ]]; then
  if [[ -z "$TOKEN_FILE" ]]; then
    echo "[ERROR] [STAGE:preflight] BRIDGE_MODE is 'named' but TUNNEL_TOKEN is absent." >&2
    exit 1
  fi
elif [[ "$ACTIVE_MODE" == "quick" ]]; then
  if [[ -n "$TOKEN_FILE" ]]; then
    echo "[ERROR] [STAGE:preflight] BRIDGE_MODE is 'quick' but TUNNEL_TOKEN was provided." >&2
    exit 1
  fi
else
  echo "[ERROR] [STAGE:preflight] Invalid BRIDGE_MODE '$BRIDGE_MODE'. Must be auto, named, or quick." >&2
  exit 1
fi

echo "Selected tunnel mode: $ACTIVE_MODE"

# --- STAGE: Detect ---
log_stage "detect" "Detecting hardware and selecting model profile"

# Query nvidia-smi: index, name, memory.total
GPU_INFO=$(nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits | head -n 1 || true)
if [[ -z "$GPU_INFO" ]]; then
  echo "[ERROR] [STAGE:detect] Unable to read GPU metrics from nvidia-smi." >&2
  exit 1
fi

DETECTED_VRAM=$(echo "$GPU_INFO" | awk -F',' '{print $3}' | tr -d ' ')
GPU_NAME=$(echo "$GPU_INFO" | awk -F',' '{print $2}' | sed 's/^ *//;s/ *$//')

echo "Detected GPU: $GPU_NAME with ${DETECTED_VRAM} MiB VRAM"

# Map to model profile from config/model-profiles.json
PROFILE_DATA=$(python3 -c "
import json, sys
with open('$ROOT/config/model-profiles.json') as f:
    cfg = json.load(f)
vram = int('$DETECTED_VRAM')
selected = None
for p in cfg.get('profiles', []):
    if vram >= p.get('min_vram_mib', 0):
        selected = p
        break
if not selected:
    selected = cfg.get('default_fallback', {})
print(f\"{selected.get('model')}|{selected.get('context_length')}|{selected.get('gpu_family', 'Other')}\")
")

PROFILE_MODEL=$(echo "$PROFILE_DATA" | cut -d'|' -f1)
PROFILE_CONTEXT=$(echo "$PROFILE_DATA" | cut -d'|' -f2)
PROFILE_FAMILY=$(echo "$PROFILE_DATA" | cut -d'|' -f3)

SELECTED_MODEL="$PROFILE_MODEL"
SELECTED_CONTEXT="$PROFILE_CONTEXT"

if [[ -n "$MODEL_OVERRIDE" ]]; then
  echo "[NOTICE] [STAGE:detect] Using model override: $MODEL_OVERRIDE"
  if [[ "$PROFILE_FAMILY" == "T4" && "$MODEL_OVERRIDE" =~ "32b" ]]; then
    echo "[WARNING] [STAGE:detect] MODEL_OVERRIDE ($MODEL_OVERRIDE) may exceed recommended VRAM on $PROFILE_FAMILY." >&2
  fi
  SELECTED_MODEL="$MODEL_OVERRIDE"
fi

if [[ -n "$OLLAMA_CONTEXT_LENGTH" ]]; then
  echo "[NOTICE] [STAGE:detect] Using context length override: $OLLAMA_CONTEXT_LENGTH"
  SELECTED_CONTEXT="$OLLAMA_CONTEXT_LENGTH"
fi

echo "Active configuration -> Model: $SELECTED_MODEL, Context: $SELECTED_CONTEXT"

# --- STAGE: Install ---
log_stage "install" "Verifying required runtime dependencies"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Installing cloudflared..."
  if command -v apt-get >/dev/null 2>&1; then
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | tee /etc/apt/sources.list.d/cloudflared.list
    apt-get update && apt-get install -y cloudflared
  elif command -v brew >/dev/null 2>&1; then
    brew install cloudflared
  else
    # Fallback to direct binary download
    CF_ARCH="amd64"
    if [[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "arm64" ]]; then
      CF_ARCH="arm64"
    fi
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" -o "$BRIDGE_STATE_DIR/cloudflared"
    chmod +x "$BRIDGE_STATE_DIR/cloudflared"
    export PATH="$BRIDGE_STATE_DIR:$PATH"
  fi
fi

# --- STAGE: Ollama Service ---
log_stage "ollama" "Starting loopback Ollama daemon"

OLLAMA_RUNNING=0
if curl -fs "http://$OLLAMA_BIND/" >/dev/null 2>&1; then
  echo "Ollama is already running on $OLLAMA_BIND."
  OLLAMA_RUNNING=1
fi

if [[ $OLLAMA_RUNNING -eq 0 ]]; then
  OLLAMA_HOST="$OLLAMA_BIND" ollama serve > "$BRIDGE_STATE_DIR/ollama.log" 2>&1 &
  OLLAMA_PID=$!
  echo "$OLLAMA_PID" > "$BRIDGE_STATE_DIR/ollama.pid"
  python3 "$ROOT/src/supervisor.py" register ollama "$OLLAMA_PID" "ollama" 2>/dev/null || true

  # Wait for Ollama ready
  READY=0
  for _ in {1..30}; do
    if curl -fs "http://$OLLAMA_BIND/" >/dev/null 2>&1; then
      READY=1
      break
    fi
    sleep 1
  done

  if [[ $READY -eq 0 ]]; then
    echo "[ERROR] [STAGE:ollama] Ollama failed to start on $OLLAMA_BIND within 30s." >&2
    exit 1
  fi
fi

# --- STAGE: Model Pull ---
log_stage "model" "Ensuring model '$SELECTED_MODEL' is available"

if ! ollama list 2>/dev/null | grep -q "^${SELECTED_MODEL}[[:space:]]"; then
  echo "Pulling $SELECTED_MODEL (this may take several minutes)..."
  ollama pull "$SELECTED_MODEL"
else
  echo "Model '$SELECTED_MODEL' is already present."
fi

# --- STAGE: Proxy ---
log_stage "proxy" "Starting loopback authentication proxy on $BRIDGE_BIND"

PROXY_RUNNING=0
if curl -fs "http://$BRIDGE_BIND/healthz" >/dev/null 2>&1; then
  echo "Proxy is already listening on $BRIDGE_BIND."
  PROXY_RUNNING=1
fi

if [[ $PROXY_RUNNING -eq 0 ]]; then
  BRIDGE_BIND="$BRIDGE_BIND" \
  OLLAMA_BIND="$OLLAMA_BIND" \
  BRIDGE_API_KEY_FILE="$API_KEY_FILE" \
  ENABLE_EMBEDDINGS="$ENABLE_EMBEDDINGS" \
  python3 "$ROOT/src/bridge_proxy.py" > "$BRIDGE_STATE_DIR/proxy.log" 2>&1 &
  PROXY_PID=$!
  echo "$PROXY_PID" > "$BRIDGE_STATE_DIR/proxy.pid"
  python3 "$ROOT/src/supervisor.py" register proxy "$PROXY_PID" "bridge_proxy.py" 2>/dev/null || true

  READY=0
  for _ in {1..15}; do
    if curl -fs "http://$BRIDGE_BIND/healthz" >/dev/null 2>&1; then
      READY=1
      break
    fi
    sleep 1
  done

  if [[ $READY -eq 0 ]]; then
    echo "[ERROR] [STAGE:proxy] Proxy failed to become healthy on $BRIDGE_BIND." >&2
    exit 1
  fi
fi

# --- STAGE: Tunnel ---
log_stage "tunnel" "Establishing Cloudflare Tunnel in $ACTIVE_MODE mode"

TUNNEL_URL=""
if [[ "$ACTIVE_MODE" == "named" ]]; then
  echo "Running named tunnel with token file..."
  cloudflared tunnel run --token-file "$TOKEN_FILE" > "$BRIDGE_STATE_DIR/cloudflared.log" 2>&1 &
  CF_PID=$!
  echo "$CF_PID" > "$BRIDGE_STATE_DIR/cloudflared.pid"
  python3 "$ROOT/src/supervisor.py" register cloudflared "$CF_PID" "cloudflared" 2>/dev/null || true
  sleep 3
  if ! kill -0 "$CF_PID" 2>/dev/null; then
    echo "[ERROR] [STAGE:tunnel] Named tunnel process exited immediately. Invalid token or network failure." >&2
    exit 1
  fi
  TUNNEL_URL="https://<your-named-tunnel-domain>"
else
  echo "Starting Quick Tunnel pointing to auth proxy http://$BRIDGE_BIND..."
  cloudflared tunnel --url "http://$BRIDGE_BIND" > "$BRIDGE_STATE_DIR/cloudflared.log" 2>&1 &
  CF_PID=$!
  echo "$CF_PID" > "$BRIDGE_STATE_DIR/cloudflared.pid"
  python3 "$ROOT/src/supervisor.py" register cloudflared "$CF_PID" "cloudflared" 2>/dev/null || true

  # Scrape trycloudflare.com URL from log
  for _ in {1..30}; do
    if [[ -f "$BRIDGE_STATE_DIR/cloudflared.log" ]]; then
      FOUND_URL=$(grep -o 'https://[a-zA-Z0-9-]\+\.trycloudflare\.com' "$BRIDGE_STATE_DIR/cloudflared.log" | head -n 1 || true)
      if [[ -n "$FOUND_URL" ]]; then
        TUNNEL_URL="$FOUND_URL"
        break
      fi
    fi
    sleep 1
  done

  if [[ -z "$TUNNEL_URL" ]]; then
    echo "[ERROR] [STAGE:tunnel] Failed to parse Quick Tunnel URL within 30s." >&2
    exit 1
  fi
fi

echo "Tunnel endpoint established: $TUNNEL_URL"

# --- STAGE: Smoke Test ---
log_stage "smoke" "Verifying authenticated model discovery through proxy"

SMOKE_KEY=$(<"$API_KEY_FILE")
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $SMOKE_KEY" "http://$BRIDGE_BIND/v1/models" || true)

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "[ERROR] [STAGE:smoke] Authenticated smoke test to proxy failed (HTTP $HTTP_CODE)." >&2
  exit 1
fi
echo "Smoke test PASSED: Authenticated endpoint responded HTTP 200."

# --- Output Connection Details ---
echo ""
echo "============================================================================="
echo " Colab Ollama Bridge is READY"
echo " Endpoint: $TUNNEL_URL"
echo " Model:    $SELECTED_MODEL (Context: $SELECTED_CONTEXT)"
echo " Mode:     $ACTIVE_MODE"
echo "============================================================================="
echo ""
echo "Export in your local shell:"
echo "  export COLAB_OLLAMA_BASE_URL=\"$TUNNEL_URL\""
echo "  export COLAB_BRIDGE_API_KEY=\"<your-bridge-key>\""
echo ""

# Generate client config
python3 "$ROOT/scripts/generate-client-config.py" \
  --model "$SELECTED_MODEL" \
  --context "$SELECTED_CONTEXT" \
  --mode "$ACTIVE_MODE"

if [[ "$SKIP_SUPERVISE" == "true" ]]; then
  echo "SKIP_SUPERVISE is true; exiting bootstrap."
  exit 0
fi

# --- STAGE: Supervise ---
log_stage "supervise" "Monitoring background processes"
exec python3 "$ROOT/src/supervisor.py"
