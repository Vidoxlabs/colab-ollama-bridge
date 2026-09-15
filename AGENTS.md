# Colab Ollama Bridge agent contract

`colab-ollama-bridge` is a public Vidoxlabs tool that exposes an authenticated, OpenAI-compatible Ollama endpoint from an interactive Google Colab GPU runtime or a user-controlled Linux GPU host. Treat every committed byte, notebook cell, generated snippet, test fixture, issue, log excerpt, and CI artifact as public.

## Start here
1. Run `git status --short --branch` and preserve unrelated user work.
2. Read `README.md`, `docs/architecture.md`, and `docs/security.md`.
3. Inspect the relevant source and tests before proposing changes.
4. Use test-driven development for behavior changes.
5. Run `make check` before handoff or publication.

## Authority order
1. Current source and tests
2. Current contracts in `docs/architecture.md` and `docs/security.md`
3. Fresh local verification from canonical commands
4. Current compatibility evidence in `docs/compatibility.md`
5. Historical issues, reports, and release notes

Configuration is not runtime evidence. Never claim that Colab, a GPU, Ollama, Cloudflare, OpenCode, Antigravity, or `colab-mcp` works unless that surface was directly exercised. Use `LIVE_RUNTIME_VERIFICATION_REQUIRED` when it was not.

## Security invariants
- Never commit, print, interpolate into generated config, or pass as a CLI argument any credential, token, API key, Access secret, private hostname, private IP, local path, account identifier, or captured runtime output.
- Ollama binds to loopback. Cloudflare tunnels terminate only at the local auth proxy; they never target Ollama directly.
- Bearer authentication is mandatory in both named and Quick Tunnel modes.
- Named tunnel tokens use `--token-file` with mode `0600`; delete temporary token files on exit. Do not enable shell tracing.
- Quick Tunnels are development-only. Do not describe them as private, production-ready, reliable, or access-controlled by Cloudflare.
- The proxy exposes only approved OpenAI-compatible inference routes. Do not expose Ollama model mutation or administrative routes.
- Logs contain stage names, status codes, and sanitized health only—never request bodies, response bodies, headers, environment dumps, or command lines containing secrets.
- Fail closed: a present-but-invalid tunnel token, missing auth key, failed proxy, failed health check, or unknown configuration stops startup. Do not silently downgrade to an unprotected or different tunnel mode.
- Do not add browser-click, JavaScript keepalive, reconnect automation, or any mechanism intended to bypass Colab idle, quota, anti-abuse, or maximum runtime enforcement.

## Implementation boundaries
- `config/model-profiles.json` is the only source of default VRAM thresholds, model tags, and runtime contexts.
- The notebook orchestrates shared scripts; it must not duplicate bootstrap, proxy, model-selection, or supervisor logic.
- `scripts/bootstrap.sh` supports Colab and Linux but does not manage DNS, Cloudflare accounts, Access policies, WAF rules, or repository settings.
- Google's `colab-mcp` is optional and separate from inference. Do not vendor it or claim client compatibility without testing dynamic tool-list updates.
- Prefer small, typed Python units and portable Bash. Quote every expansion, use bounded network timeouts/retries, own every PID before stopping it, and keep cleanup idempotent.
- Do not introduce a web UI, telemetry, analytics, database, remote shell, file-serving surface, or persistent user data without an approved ADR.

## Verification
Run the narrow test first, then the complete repository gate:
```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
bats tests/test_bootstrap.bats
python scripts/validate-notebook.py notebooks/colab_ollama.ipynb
bash scripts/scan-public-tree.sh
make check
```

GPU pulls, live inference, named tunnels, Quick Tunnels, Access policies, and client integrations are opt-in live tests. Record their exact tested versions and sanitized outcome in `docs/compatibility.md`; never run them in public CI with credentials.

## Repository policy
- Canonical remote: `https://github.com/Vidoxlabs/colab-ollama-bridge`
- Long-lived branch: `main`
- Use Conventional Commits and squash merge pull requests.
- Do not push, publish, tag, create releases, change repository settings, or mutate Cloudflare resources without explicit operator authorization.
- Never weaken a test, scan, authentication check, or refusal path merely to make validation pass.

## What does not belong here
- Real or example-shaped credentials
- Private Vidoxlabs infrastructure facts or repository content
- Saved notebook outputs or runtime logs
- Model blobs, caches, coverage output, tunnel state, or generated config with resolved values
- Duplicate agent instruction systems; `CLAUDE.md` imports this file
