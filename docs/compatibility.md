# Environment Compatibility & Verification Matrix

This matrix tracks verified runtimes, tested hardware environments, and client compatibility. Per Vidoxlabs operational standards, configuration is not runtime evidence; unverified configurations are marked `LIVE_RUNTIME_VERIFICATION_REQUIRED`.

---

## 1. Hardware & Runtime Platforms

| Platform / Accelerator | Detected VRAM | Recommended Profile | Recommended Profile Live-Verified | Hardware Live-Verified | Live-Tested Models | Verification Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Google Colab Tesla T4** | ~15,109 MiB | `qwen2.5-coder:7b` | `NO` | `NO` | None | `LIVE_RUNTIME_VERIFICATION_REQUIRED` | Tested locally via synthetic fixture `nvidia-smi-t4.txt`. |
| **Google Colab NVIDIA L4** | ~23,034 MiB | `qwen2.5-coder:14b` | `NO` | `NO` | None | `LIVE_RUNTIME_VERIFICATION_REQUIRED` | Tested locally via synthetic fixture `nvidia-smi-l4.txt`. |
| **Google Colab NVIDIA A100** | ~40,960 MiB | `qwen2.5-coder:32b` | `NO / UNKNOWN` | **YES** | `qwen2.5-coder:7b`, `1.5b` | **Hardware Verified (Live)** | Validated live on NVIDIA A100-SXM4-40GB; recommended 32B profile was not executed during live testing. |
| **Ubuntu 22.04 / 24.04 LTS** | Any | Dynamic | `NO` | `NO` | None | `LIVE_RUNTIME_VERIFICATION_REQUIRED` | Standard headless Linux target for `scripts/bootstrap.sh`. |
| **macOS (arm64)** | Apple Silicon | Fallback (`3b`) | `YES (Local)` | **YES (Local)** | `qwen2.5-coder:3b` | **Verified (Local Dev)** | Full repository static checks, unit tests, bats suite, and loopback bridge verified. |

> [!NOTE]
> **Hardware Verification vs. Model Profile Verification**:
> Hardware verification confirms that the bridge proxy, supervisor, and Ollama service bind, authenticate, and forward inference traffic through Cloudflare Tunnel on the specific GPU host. It does **not** certify that the recommended default profile (e.g., 32B on A100) has been executed; recommended profiles represent conservative VRAM sizing guidelines from `config/model-profiles.json`. Only models explicitly listed under **Live-Tested Models** have completed verified end-to-end inference runs. T4 and L4 accelerators remain strictly marked `LIVE_RUNTIME_VERIFICATION_REQUIRED` until physically exercised.

---

## 2. Upstream Software Versions

| Component | Tested Version Floor | Target Version | Verification Status |
| :--- | :--- | :--- | :--- |
| **Python** | `>= 3.10` | `3.11+` | **Verified** (3.11, 3.12, 3.13 tested in CI/local/Colab) |
| **Ollama** | `>= 0.4.0` | Latest release | **Verified (Live)** with OpenAI `/v1` endpoints on A100 |
| **cloudflared** | `>= 2024.1.0` | Latest release | **Verified (Live)** with Quick Tunnel and token validation |
| **OpenCode** | `>= 1.0.0` | Latest release | **Verified (Live)** with `@ai-sdk/openai-compatible` E2E |
| **colab-mcp** | `v1.0.2` | Tag `v1.0.2` (`b85ab6e`) | **Verified (Live)** with interactive notebook session |

---

## 3. Client Integrations

- **OpenCode**: Verified structure using `examples/opencode.example.jsonc` and `examples/opencode.access.example.jsonc`.
- **Google colab-mcp**: Official MCP server provided as an independent companion tool (`examples/antigravity.mcp_config.json`). Note: client must support MCP dynamic tool-list updates (`notifications/tools/list_changed`).
