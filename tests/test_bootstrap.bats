#!/usr/bin/env bats
# Tests for scripts/bootstrap.sh using command shims

setup() {
  export TEST_TMP_DIR
  TEST_TMP_DIR=$(mktemp -d)
  export BRIDGE_STATE_DIR="$TEST_TMP_DIR/state"
  export SHIM_DIR="$TEST_TMP_DIR/shims"
  mkdir -p "$SHIM_DIR" "$BRIDGE_STATE_DIR"

  # Default mock nvidia-smi (T4 GPU)
  cat << 'EOF' > "$SHIM_DIR/nvidia-smi"
#!/bin/bash
if [[ "$*" == *"--query-gpu"* ]]; then
  echo "0, Tesla T4, 15109"
else
  echo "NVIDIA-SMI mock active"
fi
EOF
  chmod +x "$SHIM_DIR/nvidia-smi"

  # Mock ollama
  cat << 'EOF' > "$SHIM_DIR/ollama"
#!/bin/bash
if [[ "$1" == "list" ]]; then
  echo "NAME ID SIZE MODIFIED"
elif [[ "$1" == "serve" ]]; then
  sleep 10
elif [[ "$1" == "pull" ]]; then
  echo "success"
fi
EOF
  chmod +x "$SHIM_DIR/ollama"

  # Mock cloudflared
  cat << 'EOF' > "$SHIM_DIR/cloudflared"
#!/bin/bash
if [[ "$*" == *"--url"* ]]; then
  echo "INF +--------------------------------------------------------------------------------------------+"
  echo "INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |"
  echo "INF |  https://mock-test-tunnel.trycloudflare.com                                                |"
  echo "INF +--------------------------------------------------------------------------------------------+"
  sleep 10
elif [[ "$*" == *"tunnel run"* ]]; then
  sleep 10
fi
EOF
  chmod +x "$SHIM_DIR/cloudflared"

  export PATH="$SHIM_DIR:$PATH"
  export SKIP_SUPERVISE="true"
}

teardown() {
  rm -rf "$TEST_TMP_DIR"
}

@test "bootstrap refuses when nvidia-smi is missing" {
  rm "$SHIM_DIR/nvidia-smi"
  run bash scripts/bootstrap.sh
  [ "$status" -ne 0 ]
  [[ "$output" =~ "No NVIDIA GPU detected" ]]
}

@test "bootstrap refuses when BRIDGE_API_KEY is missing" {
  unset BRIDGE_API_KEY
  unset BRIDGE_API_KEY_FILE
  run bash scripts/bootstrap.sh < /dev/null
  [ "$status" -ne 0 ]
  [[ "$output" =~ "BRIDGE_API_KEY or BRIDGE_API_KEY_FILE is required" ]]
}

@test "bootstrap refuses when BRIDGE_API_KEY is too short" {
  export BRIDGE_API_KEY="short-key"
  run bash scripts/bootstrap.sh
  [ "$status" -ne 0 ]
  [[ "$output" =~ "too short" ]]
}

@test "bootstrap refuses when BRIDGE_API_KEY is known example" {
  export BRIDGE_API_KEY="1234567890123456"
  run bash scripts/bootstrap.sh
  [ "$status" -ne 0 ]
  [[ "$output" =~ "Known example/insecure BRIDGE_API_KEY rejected" ]]
}

@test "bootstrap refuses named mode when TUNNEL_TOKEN is absent" {
  export BRIDGE_API_KEY="valid-secret-key-12345678"
  export BRIDGE_MODE="named"
  unset TUNNEL_TOKEN
  unset TUNNEL_TOKEN_FILE
  run bash scripts/bootstrap.sh
  [ "$status" -ne 0 ]
  [[ "$output" =~ "BRIDGE_MODE is 'named' but TUNNEL_TOKEN is absent" ]]
}

@test "bootstrap refuses quick mode when TUNNEL_TOKEN is provided" {
  export BRIDGE_API_KEY="valid-secret-key-12345678"
  export BRIDGE_MODE="quick"
  export TUNNEL_TOKEN="sample-token-string"
  run bash scripts/bootstrap.sh
  [ "$status" -ne 0 ]
  [[ "$output" =~ "BRIDGE_MODE is 'quick' but TUNNEL_TOKEN was provided" ]]
}

@test "bootstrap auto mode selects quick when TUNNEL_TOKEN is absent" {
  export BRIDGE_API_KEY="valid-secret-key-12345678"
  export BRIDGE_MODE="auto"
  unset TUNNEL_TOKEN
  unset TUNNEL_TOKEN_FILE

  # Mock curl to make stages pass
  cat << 'EOF' > "$SHIM_DIR/curl"
#!/bin/bash
if [[ "$*" == *"/healthz"* ]] || [[ "$*" == *"11434"* ]]; then
  exit 0
elif [[ "$*" == *"/v1/models"* ]]; then
  echo "200"
  exit 0
fi
exit 0
EOF
  chmod +x "$SHIM_DIR/curl"

  run bash scripts/bootstrap.sh
  [ "$status" -eq 0 ]
  [[ "$output" =~ "Selected tunnel mode: quick" ]]
  [[ "$output" =~ "https://mock-test-tunnel.trycloudflare.com" ]]
}

@test "bootstrap auto mode selects named when TUNNEL_TOKEN is present" {
  export BRIDGE_API_KEY="valid-secret-key-12345678"
  export BRIDGE_MODE="auto"
  export TUNNEL_TOKEN="mock-tunnel-token-value"

  cat << 'EOF' > "$SHIM_DIR/curl"
#!/bin/bash
if [[ "$*" == *"/healthz"* ]] || [[ "$*" == *"11434"* ]]; then
  exit 0
elif [[ "$*" == *"/v1/models"* ]]; then
  echo "200"
  exit 0
fi
exit 0
EOF
  chmod +x "$SHIM_DIR/curl"

  run bash scripts/bootstrap.sh
  [ "$status" -eq 0 ]
  [[ "$output" =~ "Selected tunnel mode: named" ]]
  # Ensure token was written to mode 0600 file
  [ -f "$BRIDGE_STATE_DIR/tunnel_token.token" ]
}

@test "bootstrap warns when MODEL_OVERRIDE exceeds conservative VRAM profile" {
  export BRIDGE_API_KEY="valid-secret-key-12345678"
  export MODEL_OVERRIDE="qwen2.5-coder:32b"

  cat << 'EOF' > "$SHIM_DIR/curl"
#!/bin/bash
exit 0
EOF
  chmod +x "$SHIM_DIR/curl"

  run bash scripts/bootstrap.sh
  [[ "$output" =~ "MODEL_OVERRIDE (qwen2.5-coder:32b) may exceed recommended VRAM on T4" ]]
}
