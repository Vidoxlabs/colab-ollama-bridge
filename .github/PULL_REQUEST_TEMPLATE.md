## Description
Brief summary of the changes and the rationale.

## Threat Boundary & Security Invariants Checklist
- [ ] No credentials, tokens, Access secrets, private IPs, or internal URLs committed.
- [ ] Loopback bindings preserved (Ollama on `127.0.0.1:11434`, proxy on `127.0.0.1:11435`).
- [ ] Bearer authentication enforced across all non-health routes.
- [ ] Disallowed routes (`/api/*`) remain blocked from upstream.
- [ ] No anti-idle or keepalive automation introduced.
- [ ] Notebook cells contain zero committed outputs (`outputs: []`) and execution counts are null.

## Verification Checklist
- [ ] `uv run ruff check .` passed.
- [ ] `uv run ruff format --check .` passed.
- [ ] `uv run pytest -v` passed.
- [ ] `bats tests/test_bootstrap.bats` passed.
- [ ] `python3 scripts/validate-notebook.py notebooks/colab_ollama.ipynb` passed.
- [ ] `bash scripts/scan-public-tree.sh --test` and `bash scripts/scan-public-tree.sh` passed.
- [ ] `make check` passed.
