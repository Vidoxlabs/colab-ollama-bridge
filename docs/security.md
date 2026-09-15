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

---

## 5. Vulnerability Reporting

If you identify a potential security issue or vulnerability in `colab-ollama-bridge`, please report it privately:
- Use **GitHub Private Vulnerability Reporting** via the repository's **Security > Advisories** tab.
- Do not open a public issue or discussion for suspected security vulnerabilities.
