# Cloudflare Access & Named Tunnel Hardening Guide

For production or persistent development workflows, configuring a named Cloudflare Tunnel with Cloudflare Access Service Auth provides defense-in-depth security.

---

## 1. Prerequisites

- A Cloudflare account with an active domain.
- Cloudflare Zero Trust enabled (free tier supports up to 50 users).
- A generated Cloudflare Access Service Token (`CF-Access-Client-Id` and `CF-Access-Client-Secret`).

---

## 2. Setting Up the Named Tunnel

1. In Cloudflare Zero Trust Dashboard:
   Navigate to **Networks > Tunnels > Create a Tunnel**.
2. Select **Cloudflare Tunnel (cloudflared)**.
3. Name your tunnel (e.g. `colab-ollama-bridge`).
4. Copy the Tunnel Token provided by Cloudflare.
5. Under **Public Hostnames**:
   - Subdomain: `ollama` (or your choice)
   - Domain: `yourdomain.com`
   - Service Type: `HTTP`
   - URL: `127.0.0.1:11435` *(pointing to the Bridge Auth Proxy, never 11434)*

---

## 3. Configuring Cloudflare Access Application

1. Navigate to **Access > Applications > Add an application**.
2. Select **Self-hosted**.
3. Set Application domain: `ollama.yourdomain.com`.
4. Configure Policies:
   - **Policy Name**: `Service Auth Policy`
   - **Action**: `Service Auth`
   - **Include**:
     - `Service Token`: Select or create your Service Token.
5. Save Application.

---

## 4. Configuring OpenCode Client

Export the credentials in your local shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export COLAB_OLLAMA_BASE_URL="https://ollama.yourdomain.com"
export COLAB_BRIDGE_API_KEY="your-bridge-api-key"
export CF_ACCESS_CLIENT_ID="your-cf-access-client-id"
export CF_ACCESS_CLIENT_SECRET="your-cf-access-client-secret"
```

Configure OpenCode (`opencode.json`):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "colab-ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Colab Ollama Bridge",
      "options": {
        "baseURL": "{env:COLAB_OLLAMA_BASE_URL}/v1",
        "apiKey": "{env:COLAB_BRIDGE_API_KEY}",
        "headers": {
          "CF-Access-Client-Id": "{env:CF_ACCESS_CLIENT_ID}",
          "CF-Access-Client-Secret": "{env:CF_ACCESS_CLIENT_SECRET}"
        }
      },
      "models": {
        "qwen2.5-coder:14b": {
          "name": "Qwen 2.5 Coder 14B (Colab)",
          "limit": {
            "context": 16384,
            "output": 8192
          }
        }
      }
    }
  }
}
```

---

## 5. Security Posture Verification

- **Direct requests without Access headers**: Receive Cloudflare Access 302 redirect / 403 Forbidden.
- **Requests with Access headers but invalid Bearer key**: Cloudflare allows through, but the Bridge Auth Proxy rejects with HTTP 401 Unauthorized.
- **Requests to Ollama administrative routes**: Bridge Auth Proxy rejects with HTTP 404 Not Found.
