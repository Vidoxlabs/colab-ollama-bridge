#!/usr/bin/env bash
# Colab Ollama Bridge — Public Tree & Git History Secret/Leak Scanner
# Enforces zero leaks of private IPs, local home paths, private repo URLs, and credentials.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Run synthetic test suite if requested
if [[ "${1:-}" == "--test" ]]; then
  echo "Running scan-public-tree self-tests..."
  TMP_TEST_DIR=$(mktemp -d)
  trap 'rm -rf "$TMP_TEST_DIR"' EXIT

  # 1. Test clean directory passes
  mkdir -p "$TMP_TEST_DIR/clean"
  echo "Clean content with https://example.com" > "$TMP_TEST_DIR/clean/file.txt"
  if ! (SCAN_DIR="$TMP_TEST_DIR/clean" "$0" --run-scan >/dev/null 2>&1); then
    echo "FAIL: Clean directory falsely flagged as violation"
    exit 1
  fi

  # 2. Test private IP leak triggers failure
  mkdir -p "$TMP_TEST_DIR/leak-ip"
  echo "Leaking IP: 10.10.10.110" > "$TMP_TEST_DIR/leak-ip/leak.txt"
  if (SCAN_DIR="$TMP_TEST_DIR/leak-ip" "$0" --run-scan >/dev/null 2>&1); then
    echo "FAIL: Scanner missed private IP leak"
    exit 1
  fi

  # 3. Test JWT leak triggers failure
  mkdir -p "$TMP_TEST_DIR/leak-jwt"
  echo "eyJhGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotCommit" > "$TMP_TEST_DIR/leak-jwt/token.txt"
  if (SCAN_DIR="$TMP_TEST_DIR/leak-jwt" "$0" --run-scan >/dev/null 2>&1); then
    echo "FAIL: Scanner missed JWT leak"
    exit 1
  fi

  # 4. Test local home path leak triggers failure
  mkdir -p "$TMP_TEST_DIR/leak-path"
  echo "Local path: /Users/johndoe/workspace" > "$TMP_TEST_DIR/leak-path/path.txt"
  if (SCAN_DIR="$TMP_TEST_DIR/leak-path" "$0" --run-scan >/dev/null 2>&1); then
    echo "FAIL: Scanner missed local home path leak"
    exit 1
  fi

  # 5. Test PEM private key leak triggers failure
  mkdir -p "$TMP_TEST_DIR/leak-pem"
  echo "-----BEGIN RSA PRIVATE KEY-----" > "$TMP_TEST_DIR/leak-pem/key.txt"
  if (SCAN_DIR="$TMP_TEST_DIR/leak-pem" "$0" --run-scan >/dev/null 2>&1); then
    echo "FAIL: Scanner missed PEM private key leak"
    exit 1
  fi

  # 6. Test high-entropy secret assignment triggers failure
  mkdir -p "$TMP_TEST_DIR/leak-entropy"
  echo 'api_key = "a8f9b2c3d4e5f60718293a4b5c6d7e8f"' > "$TMP_TEST_DIR/leak-entropy/secret.txt"
  if (SCAN_DIR="$TMP_TEST_DIR/leak-entropy" "$0" --run-scan >/dev/null 2>&1); then
    echo "FAIL: Scanner missed high-entropy secret assignment leak"
    exit 1
  fi

  echo "All scanner self-tests PASSED."
  exit 0
fi

SCAN_TARGET="${SCAN_DIR:-$ROOT}"
cd "$SCAN_TARGET"

failures=0

# Forbidden tracked file patterns
FORBIDDEN_FILES=(
  ".env"
  ".env.local"
  "*.token"
  "*.key"
  "*.pem"
  "*.log"
  "*.swp"
  "*state.json"
  ".DS_Store"
)

echo "--- 1. Checking for forbidden file patterns ---"
for pat in "${FORBIDDEN_FILES[@]}"; do
  if git ls-files --error-unmatch "$pat" >/dev/null 2>&1; then
    echo "ERROR: Tracked forbidden file found: $pat"
    failures=$((failures + 1))
  fi
done

echo "--- 2. Checking tree content for sensitive patterns ---"
LEAK_REGEXES=(
  # Private IPv4 addresses (10.x.x.x, 192.168.x.x, 172.16-31.x.x)
  '(^|[^0-9])(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.[0-9]{1,3}\.[0-9]{1,3})([^0-9]|$)'
  # Absolute user paths
  '(/Users/[a-zA-Z0-9_-]+|/home/[a-zA-Z0-9_-]+)'
  # Internal domain names
  '(\.internal|\.localdomain|\.cluster)'
  # Private SSH URLs
  'git@github\.com:'
  # Private Vidoxlabs repos (vitools-public and colab-ollama-bridge are public)
  'github\.com/Vidoxlabs/(vinet|ViApp|violet_app|vidoxlabs\.dev)'
  # Credential shapes
  '(ghp_[A-Za-z0-9_]{36}|gho_[A-Za-z0-9_]{36}|AIza[0-9A-Za-z-_]{35}|sk-[A-Za-z0-9_-]{20,})'
  # JWT tokens
  'ey[A-Za-z0-9_-]{20,}\.ey[A-Za-z0-9_-]{20,}\.'
  # PEM private key blocks
  '-----BEGIN[ A-Z0-9_-]*PRIVATE KEY-----'
  # High-entropy secret assignments
  '(api[_-]?key|secret[_-]?key|auth[_-]?token|access[_-]?token|cf[_-]?token)[[:space:]]*[:=][[:space:]]*["'\''][A-Za-z0-9+/=_-]{32,}["'\'']'
)

# Files to inspect
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  FILES=$(git ls-files)
else
  FILES=$(find . -type f -not -path '*/.*')
fi

# Exclude the scanner itself from pattern checks so its regexes don't trip itself
for pattern in "${LEAK_REGEXES[@]}"; do
  matches=$(echo "$FILES" | while IFS= read -r f; do
    if [[ -f "$f" && "$f" != *"scan-public-tree.sh"* ]]; then
      grep -En -e "$pattern" "$f" 2>/dev/null || true
    fi
  done)

  if [[ -n "$matches" ]]; then
    echo "ERROR: Sensitive pattern detected ($pattern):"
    echo "$matches" | head -n 10
    failures=$((failures + 1))
  fi
done

echo "--- 3. Checking reachable Git history ---"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git rev-parse --verify HEAD >/dev/null 2>&1; then
  for pattern in "${LEAK_REGEXES[@]}"; do
    history_matches=$(git log -p --all -- ":!scripts/scan-public-tree.sh" | grep -En -e "$pattern" 2>/dev/null || true)
    if [[ -n "$history_matches" ]]; then
      echo "ERROR: Sensitive pattern found in Git history ($pattern):"
      echo "$history_matches" | head -n 10
      failures=$((failures + 1))
    fi
  done
fi

if [[ "$failures" -gt 0 ]]; then
  echo ""
  echo "Public tree scan FAILED with $failures violation(s)."
  exit 1
fi

echo "Public tree scan PASSED: Zero leaks detected."
exit 0
