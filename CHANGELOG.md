# Changelog

All notable changes to `colab-ollama-bridge` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-15

### Added
- Security-first loopback authentication proxy (`src/bridge_proxy.py`) enforcing `BRIDGE_API_KEY`, route allowlists, payload caps (8 MiB), and SSE streaming.
- Dual tunnel support via Cloudflare Tunnel:
  - Named tunnel mode with token file (`0600` permissions) and Cloudflare Access Service Auth hardening.
  - Development-only Quick Tunnel mode with origin authentication preserved.
- Deterministic GPU VRAM detection and profile matrix (`config/model-profiles.json`) for T4, L4, and A100 GPU runtimes.
- Shared idempotent bootstrap script (`scripts/bootstrap.sh`) for headless Linux hosts and Google Colab.
- Process supervisor (`src/supervisor.py`) with strict PID ownership verification and bounded restart loops.
- Interactive, output-free Google Colab notebook (`notebooks/colab_ollama.ipynb`) with Open in Colab badge.
- OpenCode client provider generator (`scripts/generate-client-config.py`) and examples (`examples/opencode.example.jsonc`, `examples/opencode.access.example.jsonc`).
- Companion configuration for Google official `googlecolab/colab-mcp` (`examples/antigravity.mcp_config.json`).
- Automated public tree secret scanner (`scripts/scan-public-tree.sh`) and notebook validator (`scripts/validate-notebook.py`).
- Complete repository documentation suite in `docs/`.
