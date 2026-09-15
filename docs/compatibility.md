# Environment Compatibility & Verification Matrix

This matrix tracks verified runtimes, tested hardware environments, and client compatibility. Per Vidoxlabs operational standards, configuration is not runtime evidence; unverified configurations are marked `LIVE_RUNTIME_VERIFICATION_REQUIRED`.

---

## 1. Hardware & Runtime Platforms

| Platform / Accelerator | Detected VRAM | Default Model | Verified Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Google Colab Tesla T4** | ~15,109 MiB | `qwen2.5-coder:7b` | `LIVE_RUNTIME_VERIFICATION_REQUIRED` | Tested locally via synthetic fixture `nvidia-smi-t4.txt`. |
| **Google Colab NVIDIA L4** | ~23,034 MiB | `qwen2.5-coder:14b` | `LIVE_RUNTIME_VERIFICATION_REQUIRED` | Tested locally via synthetic fixture `nvidia-smi-l4.txt`. |
| **Google Colab NVIDIA A100** | ~40,960 MiB | `qwen2.5-coder:32b` | `LIVE_RUNTIME_VERIFICATION_REQUIRED` | Tested locally via synthetic fixture `nvidia-smi-a100.txt`. |
| **Ubuntu 22.04 / 24.04 LTS** | Any | Dynamic | `LIVE_RUNTIME_VERIFICATION_REQUIRED` | Standard headless Linux target for `scripts/bootstrap.sh`. |
| **macOS (arm64)** | Host Apple Silicon | Fallback | Verified (Local Dev) | Full repository static checks, unit tests, and bats suite verified. |

---

## 2. Upstream Software Versions

| Component | Tested Version Floor | Target Version | Verification Status |
| :--- | :--- | :--- | :--- |
| **Python** | `>= 3.10` | `3.11+` | Verified (3.11, 3.12, 3.13 tested in CI/local) |
| **Ollama** | `>= 0.4.0` | Latest release | Compatible with OpenAI `/v1` endpoints |
| **cloudflared** | `>= 2024.1.0` | Latest release | Supports `--token-file` (runtime check enforced) and `--url` |
| **OpenCode** | `>= 1.0.0` | Latest release | Compatible with `@ai-sdk/openai-compatible` |
| **colab-mcp** | `v1.0.2` | Tag `v1.0.2` (`b85ab6e`) | `LIVE_RUNTIME_VERIFICATION_REQUIRED` (Apache-2.0, Python 3.13+) |

---

## 3. Client Integrations

- **OpenCode**: Verified structure using `examples/opencode.example.jsonc` and `examples/opencode.access.example.jsonc`.
- **Google colab-mcp**: Official MCP server provided as an independent companion tool (`examples/antigravity.mcp_config.json`). Note: client must support MCP dynamic tool-list updates (`notifications/tools/list_changed`).
