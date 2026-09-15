# Publishing & Release Procedure

This document provides the canonical operator-gated instructions for initializing the remote repository, configuring GitHub rulesets, executing the zero-leak release gate, and publishing public releases.

> [!CAUTION]
> **Operator Authorization Invariant**:
> Commands that create remote repositories, alter visibility, modify branch rulesets, push tags, or publish releases require explicit operator review and execution.

---

## 1. Remote Repository Initialization

Create the repository initially as **Private**:

```bash
# 1. Create remote repository under Vidoxlabs organization
gh repo create Vidoxlabs/colab-ollama-bridge \
  --private \
  --description "Securely connect OpenCode-compatible clients to Ollama on Google Colab or remote NVIDIA GPUs through Cloudflare Tunnel." \
  --disable-wiki

# 2. Add remote and push initial main branch
git remote add origin https://github.com/Vidoxlabs/colab-ollama-bridge.git
git push -u origin main
```

---

## 2. Configure Repository Settings & Topics

```bash
# Enable topics
gh repo edit Vidoxlabs/colab-ollama-bridge --add-topic \
  "google-colab,ollama,opencode,cloudflare-tunnel,gpu,openai-compatible,mcp,ai-coding"

# Configure merge policy: squash only, auto-delete head branches
gh repo edit Vidoxlabs/colab-ollama-bridge \
  --enable-squash-merge \
  --delete-branch-on-merge
```

---

## 3. Branch Protection & Ruleset Configuration

Apply a repository ruleset for `main`:
1. Require pull requests before merging.
2. Require status checks to pass (`validate / check`).
3. Require linear history.
4. Block force pushes and branch deletion.

---

## 4. Zero-Leak Verification Gate

Before public switch or tag creation, execute the full validation gate locally on the exact candidate commit:

```bash
# Run narrow test suites
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
bats tests/test_bootstrap.bats
python3 scripts/validate-notebook.py notebooks/colab_ollama.ipynb

# Run full tree and history scanner
bash scripts/scan-public-tree.sh --test
bash scripts/scan-public-tree.sh

# Run comprehensive check target
make check
```

---

## 5. Transition to Public Visibility

Only after operator review and confirmation of clean scan receipts:

```bash
# Operator confirmation required
gh repo edit Vidoxlabs/colab-ollama-bridge --visibility public
```

---

## 6. Release Tagging & Publication

```bash
# Create annotated tag
git tag -a v0.1.0 -m "Release v0.1.0: Colab Ollama Bridge initial release"
git push origin v0.1.0

# GitHub Actions release.yml workflow triggers on v* tags and creates the release
```

---

## 7. Rollback & Incident Procedure

If any credential, unintended disclosure, or security defect is discovered:
1. **Immediately revoke / rotate** the affected secret or token.
2. Switch repository visibility back to private:
   ```bash
   gh repo edit Vidoxlabs/colab-ollama-bridge --visibility private
   ```
3. Rewrite Git history using `git-filter-repo` if a secret was committed.
4. Rerun `scripts/scan-public-tree.sh` across all branches and tags.
5. Invalidate affected release assets.
