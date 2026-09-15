#!/usr/bin/env bats
# Clean-Room Bootstrap Tests: Verifies execution via stdin pipe outside git checkout

setup() {
  export REPO_ROOT="$BATS_TEST_DIRNAME/.."
  export CLEAN_TMP_DIR
  CLEAN_TMP_DIR=$(mktemp -d)
  export BRIDGE_STATE_DIR="$CLEAN_TMP_DIR/state"
  export SHIM_DIR="$CLEAN_TMP_DIR/shims"
  export DIST_DIR="$CLEAN_TMP_DIR/dist_server"
  mkdir -p "$SHIM_DIR" "$BRIDGE_STATE_DIR" "$DIST_DIR/config" "$DIST_DIR/src" "$DIST_DIR/scripts"

  # Populate mock distribution server files
  cp "$REPO_ROOT/config/model-profiles.json" "$DIST_DIR/config/"
  cp "$REPO_ROOT/src/bridge_proxy.py" "$DIST_DIR/src/"
  cp "$REPO_ROOT/src/supervisor.py" "$DIST_DIR/src/"
  cp "$REPO_ROOT/scripts/generate-client-config.py" "$DIST_DIR/scripts/"

  # Generate valid runtime-SHA256SUMS.txt
  (
    cd "$DIST_DIR"
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum config/model-profiles.json src/bridge_proxy.py src/supervisor.py scripts/generate-client-config.py > runtime-SHA256SUMS.txt
    else
      shasum -a 256 config/model-profiles.json src/bridge_proxy.py src/supervisor.py scripts/generate-client-config.py > runtime-SHA256SUMS.txt
    fi
  )
  if command -v sha256sum >/dev/null 2>&1; then
    TEST_MANIFEST_SHA256=$(sha256sum "$DIST_DIR/runtime-SHA256SUMS.txt" | awk '{print $1}')
  else
    TEST_MANIFEST_SHA256=$(shasum -a 256 "$DIST_DIR/runtime-SHA256SUMS.txt" | awk '{print $1}')
  fi
  export BRIDGE_RUNTIME_MANIFEST_SHA256="$TEST_MANIFEST_SHA256"

  # Start mock HTTP server for distribution assets
  PORT_FILE="$CLEAN_TMP_DIR/server_port.txt"
  python3 -c "
import http.server, socketserver, os, sys
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='$DIST_DIR', **kwargs)
    def log_message(self, format, *args):
        pass
with socketserver.TCPServer(('127.0.0.1', 0), Handler) as httpd:
    with open('$PORT_FILE', 'w') as f:
        f.write(str(httpd.server_address[1]))
    httpd.serve_forever()
" >/dev/null 2>&1 &
  HTTPD_PID=$!
  echo "$HTTPD_PID" > "$CLEAN_TMP_DIR/httpd.pid"

  # Wait for server port
  for _ in {1..20}; do
    if [[ -f "$PORT_FILE" ]]; then
      break
    fi
    sleep 0.1
  done

  DIST_PORT=$(<"$PORT_FILE")
  export BRIDGE_DIST_URL="http://127.0.0.1:$DIST_PORT"

  # Shims for clean environment
  cat << 'EOF' > "$SHIM_DIR/nvidia-smi"
#!/bin/bash
if [[ "$*" == *"--query-gpu"* ]]; then
  echo "0, Tesla T4, 15109"
else
  echo "NVIDIA-SMI mock active"
fi
EOF
  chmod +x "$SHIM_DIR/nvidia-smi"

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

  cat << 'EOF' > "$SHIM_DIR/cloudflared"
#!/bin/bash
if [[ "$*" == *"--help"* ]]; then
  echo "  --token-file value  Filepath at which to read the tunnel token."
  exit 0
elif [[ "$*" == *"--url"* ]]; then
  echo "INF |  https://cleanroom-test.trycloudflare.com  |"
  sleep 10
fi
EOF
  chmod +x "$SHIM_DIR/cloudflared"

  export PATH="$SHIM_DIR:$PATH"
  export BRIDGE_API_KEY="cleanroom-secret-key-12345678"
  export SKIP_SUPERVISE="true"
}

teardown() {
  if [[ -f "$CLEAN_TMP_DIR/httpd.pid" ]]; then
    HTTPD_PID=$(<"$CLEAN_TMP_DIR/httpd.pid")
    kill "$HTTPD_PID" 2>/dev/null || true
  fi
  for pid_file in "$BRIDGE_STATE_DIR"/*.pid; do
    if [[ -f "$pid_file" ]]; then
      pid=$(<"$pid_file")
      kill "$pid" 2>/dev/null || true
    fi
  done
  rm -rf "$CLEAN_TMP_DIR"
}

@test "clean-room stdin bootstrap fetches assets, verifies checksums, and succeeds" {
  cd "$CLEAN_TMP_DIR"
  # Mock curl proxy/ollama checks
  cat << 'EOF' > "$SHIM_DIR/curl"
#!/bin/bash
if [[ "$*" == *"/healthz"* ]] || [[ "$*" == *"11434"* ]]; then
  exit 0
elif [[ "$*" == *"/v1/models"* ]]; then
  echo "200"
  exit 0
fi
exec /usr/bin/curl "$@"
EOF
  chmod +x "$SHIM_DIR/curl"

  run bash -c "cat '$REPO_ROOT/scripts/bootstrap.sh' | bash"
  [ "$status" -eq 0 ]
  [[ "$output" =~ "Colab Ollama Bridge is READY" ]]
  [[ "$output" =~ "https://cleanroom-test.trycloudflare.com" ]]
  # Verify assets were downloaded to state directory
  [ -f "$BRIDGE_STATE_DIR/assets/config/model-profiles.json" ]
  [ -f "$BRIDGE_STATE_DIR/assets/src/bridge_proxy.py" ]
  [ -f "$BRIDGE_STATE_DIR/assets/src/supervisor.py" ]
  [ -f "$BRIDGE_STATE_DIR/assets/scripts/generate-client-config.py" ]
}

@test "clean-room stdin bootstrap fails closed on checksum mismatch" {
  cd "$CLEAN_TMP_DIR"
  # Corrupt a file in the distribution directory so it doesn't match SHA256SUMS.txt
  echo "tampered content" >> "$DIST_DIR/src/bridge_proxy.py"

  cat << 'EOF' > "$SHIM_DIR/curl"
#!/bin/bash
exec /usr/bin/curl "$@"
EOF
  chmod +x "$SHIM_DIR/curl"

  run bash -c "cat '$REPO_ROOT/scripts/bootstrap.sh' | bash"
  [ "$status" -ne 0 ]
  [[ "$output" =~ "Checksum verification failed" || "$output" =~ "FAILED" ]]
}

@test "clean-room stdin bootstrap fails closed when distribution asset is missing" {
  cd "$CLEAN_TMP_DIR"
  # Delete runtime-SHA256SUMS.txt from distribution
  rm -f "$DIST_DIR/runtime-SHA256SUMS.txt"

  cat << 'EOF' > "$SHIM_DIR/curl"
#!/bin/bash
exec /usr/bin/curl "$@"
EOF
  chmod +x "$SHIM_DIR/curl"

  run bash -c "cat '$REPO_ROOT/scripts/bootstrap.sh' | bash"
  [ "$status" -ne 0 ]
  [[ "$output" =~ "Failed to download" || "$output" =~ "missing" ]]
}

@test "clean-room stdin bootstrap fails closed when runtime manifest is altered despite consistent asset hashes" {
  cd "$CLEAN_TMP_DIR"
  # Tamper with an asset AND regenerate runtime-SHA256SUMS.txt so asset hashes inside it are internally consistent
  echo "# tampered asset" >> "$DIST_DIR/src/bridge_proxy.py"
  (
    cd "$DIST_DIR"
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum config/model-profiles.json src/bridge_proxy.py src/supervisor.py scripts/generate-client-config.py > runtime-SHA256SUMS.txt
    else
      shasum -a 256 config/model-profiles.json src/bridge_proxy.py src/supervisor.py scripts/generate-client-config.py > runtime-SHA256SUMS.txt
    fi
  )
  # Unset test override so bootstrap enforces its embedded trust root
  unset BRIDGE_RUNTIME_MANIFEST_SHA256

  cat << 'EOF' > "$SHIM_DIR/curl"
#!/bin/bash
exec /usr/bin/curl "$@"
EOF
  chmod +x "$SHIM_DIR/curl"

  run bash -c "cat '$REPO_ROOT/scripts/bootstrap.sh' | bash"
  [ "$status" -ne 0 ]
  [[ "$output" =~ "Runtime manifest digest" || "$output" =~ "does not match expected trust root" ]]
}
