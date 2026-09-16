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

## 3. Branch & Tag Ruleset Protection

Configure repository rulesets (or branch protection rules) for `main` and release tags `v*`:

### `main` Branch Ruleset
1. Require status check `check` (from `.github/workflows/validate.yml`) before merging.
2. Require linear history (squash or rebase).
3. Block force pushes and branch deletion.
4. Require pull request reviews with CODEOWNERS enforcement (`* @Vioxniv`).

### `v*` Tag Protection Ruleset
1. Prevent tag deletion for `refs/tags/v*`.
2. Prevent updating (force-moving) existing `refs/tags/v*` tags.
3. Restrict tag creation in `refs/tags/v*` to repository maintainers/admins.

> [!NOTE]
> **Plan Limitations**:
> GitHub Free private repositories have limited ruleset support. Operators should check **Settings > Rules > Rulesets** to verify feature availability, or upgrade organization plan if mandatory status check enforcement is required in private state before public transition.

---

## 4. Zero-Leak Verification Gate

Before public switch or tag creation, execute the full validation gate locally on the exact candidate commit:

```bash
# Run narrow test suites
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
bats tests/*.bats
python3 scripts/validate-notebook.py notebooks/colab_ollama.ipynb

# Run full tree and history scanner
bash scripts/scan-public-tree.sh --test
bash scripts/scan-public-tree.sh

# Run comprehensive check target
make check
```

---

## 5. Transition to Public Visibility

Only after operator review, candidate commit verification, and confirmation of clean scan receipts:

```bash
# Explicit operator confirmation and consequence acceptance required
gh repo edit Vidoxlabs/colab-ollama-bridge \
  --visibility public \
  --accept-visibility-change-consequences
```

---

## 6. Release Tagging & Publication

Release tags must be annotated to preserve tagger identity, date, and release notes:

```bash
# 1. Create annotated release tag (e.g., for v0.1.1)
git tag -a v0.1.1 -m "Release v0.1.1: Ollama Host header forwarding fix"

# Note: If GPG or SSH tag signing is configured on your workstation, use signed tags (-s):
# git tag -s v0.1.1 -m "Release v0.1.1: Ollama Host header forwarding fix"
# (Only claim signed release status if verified via 'git tag -v v0.1.1')

# 2. Push tag to trigger release workflow
git push origin v0.1.1

# GitHub Actions release.yml workflow triggers on v* tags, verifies embedded runtime manifest digest, and generates release-SHA256SUMS.txt
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
