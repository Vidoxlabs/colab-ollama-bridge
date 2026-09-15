# Troubleshooting Guide

This guide describes common failure modes, diagnostic steps, and safe recovery procedures.

---

## 1. Diagnostics Overview

All error messages emitted by `bootstrap.sh` and `bridge_proxy.py` follow a standardized format:
```text
[ERROR] [STAGE:<stage_name>] <sanitized error message>
```

Diagnostics never print secrets, API keys, or raw request/response headers.

---

## 2. Common Failure Modes & Resolutions

### 1. `[ERROR] [STAGE:preflight] No NVIDIA GPU detected`
- **Cause**: The current environment lacks an NVIDIA GPU or `nvidia-smi` is not in `PATH`.
- **Resolution**:
  - In Google Colab: Go to **Runtime > Change runtime type**, select **T4 GPU**, **L4 GPU**, or **A100 GPU**, and click **Save**.
  - On Linux hosts: Ensure NVIDIA drivers and CUDA toolkit are installed (`nvidia-smi` works).

### 2. `[ERROR] [STAGE:preflight] BRIDGE_API_KEY is too short`
- **Cause**: The provided key was missing, shorter than 16 characters, contained whitespace, or matched a known insecure example.
- **Resolution**: Generate a secure random key (e.g. `openssl rand -hex 16`) and provide it via Colab Secrets (`BRIDGE_API_KEY`) or the interactive prompt.

### 3. `[ERROR] [STAGE:tunnel] Named tunnel process exited immediately`
- **Cause**: The `TUNNEL_TOKEN` is invalid, expired, or revoked by Cloudflare.
- **Resolution**:
  - Verify your tunnel configuration in the Cloudflare Zero Trust dashboard.
  - Colab Ollama Bridge fails closed and will **never** silently fall back to Quick Tunnel when a named token fails.

### 4. `[ERROR] [STAGE:tunnel] Failed to parse Quick Tunnel URL within 30s`
- **Cause**: `cloudflared` encountered edge rate-limiting or network connectivity issues connecting to Cloudflare.
- **Resolution**: Check your host outbound internet connectivity. Re-run `bootstrap.sh` after a brief pause.

### 5. Client Receives HTTP 302 Redirect or HTML Login Page
- **Cause**: You are using a named tunnel protected by Cloudflare Access, but your client is missing Service Auth headers.
- **Resolution**:
  - Ensure `CF-Access-Client-Id` and `CF-Access-Client-Secret` headers are configured in your OpenCode configuration.
  - Ensure the Cloudflare Access Application policy is set to **Service Auth**, not standard interactive user login.

### 6. Client Receives HTTP 401 Unauthorized
- **Cause**: The `Authorization: Bearer <key>` header provided by the client does not match `BRIDGE_API_KEY`.
- **Resolution**: Check that `COLAB_BRIDGE_API_KEY` is exported correctly in your client's local shell profile.

### 7. Client Receives HTTP 404 Not Found on `/api/*`
- **Cause**: The client attempted to call Ollama native administrative endpoints (e.g. `/api/pull`, `/api/tags`).
- **Resolution**: The bridge proxy allowlists only OpenAI-compatible routes (`/v1/chat/completions`, `/v1/models`, etc.) for security. Use OpenAI-compatible SDKs or clients.

### 8. Colab Session Terminates Unexpectedly
- **Cause**: Google Colab enforces maximum runtime limits (usually 12 hours) and idle timeouts (after ~90 minutes of inactive web browser session).
- **Resolution**: Colab is designed for interactive sessions. Reconnect to a new Colab runtime and re-execute the notebook.
