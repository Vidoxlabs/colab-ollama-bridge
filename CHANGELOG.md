# Changelog

All notable changes to `colab-ollama-bridge` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-09-15

### Fixed
- Upstream Ollama origin rejection: rewrite `Host` header to upstream `host:port` (`127.0.0.1:11434`) in `src/bridge_proxy.py` to satisfy Ollama 403 Forbidden origin validation when accessed via Cloudflare Tunnels.

### Changed
- Bumped default distribution URL in `scripts/bootstrap.sh` to pinned immutable release tag `v0.1.1` and updated embedded runtime manifest SHA-256 digest (`6d084f38...`).

### Added
- Documented live verification on NVIDIA A100-SXM4-40GB GPU with `qwen2.5-coder:7b` and `qwen2.5-coder:1.5b`.
- Expanded OpenCode client configuration guidance for model discovery, custom model overrides, and connection recovery.

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
