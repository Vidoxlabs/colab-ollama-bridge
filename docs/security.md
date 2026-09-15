# Security Policy & Threat Model

`colab-ollama-bridge` is designed with a defense-in-depth, fail-closed security posture. This document outlines the threat model, secret handling invariants, and vulnerability reporting procedures.

---

## 1. Threat Model

| Boundary | Assumption | Mitigation |
| :--- | :--- | :--- |
| **Repository** | Everything committed to Git is globally public. | Pre-commit hooks, CI secret scanning, and `scripts/scan-public-tree.sh` enforce zero committed credentials or private network identifiers. |
| **Google Colab** | Interactive, shared runtime. Cell outputs may be saved, screenshotted, or shared. | Notebook metadata strips outputs (`outputs: []`). Secrets are resolved in memory or temporary mode `0600` files and never interpolated into cells. |
| **Network Edge** | A public Cloudflare Tunnel URL is publicly reachable. | The tunnel terminates exclusively at the Bridge Auth Proxy on `127.0.0.1:11435`, never Ollama directly. Origin bearer key validation is mandatory in both named and Quick Tunnel modes. |
| **Upstream Service** | Ollama daemon does not implement route-level authentication. | Ollama binds exclusively to loopback (`127.0.0.1:11434`). The proxy allowlists only safe OpenAI inference routes, blocking native administrative endpoints (`/api/*`). |

---

## 2. Secret Lifecycle Management

- **`BRIDGE_API_KEY`**:
  - Minimum length: 16 characters.
  - Rejects known weak/example strings and whitespace.
  - Stored in memory or in a temporary mode `0600` file (`bridge_api.key`).
  - Never passed as command-line arguments (which are visible in process tables like `ps`).
  - Validated using constant-time comparison (`hmac.compare_digest`) to prevent timing attacks.
  - Never forwarded to upstream Ollama.
- **`TUNNEL_TOKEN`**:
  - Written immediately to a mode `0600` file and passed to cloudflared via `--token-file`.
  - Unset from environment immediately upon ingestion.
  - Deleted automatically on process exit or supervisor shutdown.

---

## 3. Logging & Redaction Invariants

- **Disallowed in Logs**: Request bodies, response bodies, headers (especially `Authorization` and `CF-Access-*`), environment variables, and shell command lines.
- **Allowed in Logs**: Stage names, HTTP status codes, request methods, sanitized paths, and elapsed durations.
- **Shell Tracing**: `set -x` is strictly forbidden in all shell scripts.

---

## 4. Fail-Closed Principles

1. **No Silent Downgrades**: If a named tunnel token is invalid or fails to connect, the system halts immediately. It never silently falls back to an unauthenticated or Quick Tunnel.
2. **Missing Credentials**: Missing or empty API keys abort startup before any tunnel or proxy process is launched.
3. **Route Allowlist**: Any unmapped route returns HTTP 404. Unauthenticated requests return generic HTTP 401 without stack traces.
4. **Manifest Tampering**: Any modification to runtime assets or the runtime manifest causes bootstrap to abort before starting any Python processes.

---

## 5. Distribution Integrity & Checksum Trust Root

When `scripts/bootstrap.sh` runs outside of a Git checkout (e.g. piped via `curl ... | bash` in a fresh Colab runtime or container):
1. **Initial Trust Root**: `bootstrap.sh` is retrieved by the operator from an immutable Git release tag (`v0.1.0`) or commit hash.
2. **Embedded Manifest Digest**: `bootstrap.sh` embeds the exact expected SHA-256 digest of `runtime-SHA256SUMS.txt`.
3. **Manifest Authentication**: `bootstrap.sh` downloads `runtime-SHA256SUMS.txt` and verifies its SHA-256 digest against `RUNTIME_MANIFEST_SHA256` before downloading assets. If the manifest has been modified, execution halts immediately.
4. **Asset Integrity**: Each downloaded runtime asset (`config/model-profiles.json`, `src/bridge_proxy.py`, `src/supervisor.py`, `scripts/generate-client-config.py`) is verified against the authenticated manifest.
5. **Separation of Checksum Artifacts**:
   - `runtime-SHA256SUMS.txt`: Dedicated, committed manifest for runtime assets.
   - `release-SHA256SUMS.txt`: Generated during CI release packaging for release tarballs and archives.
6. **Operator Trust Path**: Cryptographic hashing guarantees tamper detection; operator trust is completed by fetching `bootstrap.sh` from protected, annotated release tags (`refs/tags/v*`) with optional cryptographic tag signatures.

---

## 5. Vulnerability Reporting

If you identify a potential security issue or vulnerability in `colab-ollama-bridge`, please report it privately:
- Use **GitHub Private Vulnerability Reporting** via the repository's **Security > Advisories** tab.
- Do not open a public issue or discussion for suspected security vulnerabilities.
