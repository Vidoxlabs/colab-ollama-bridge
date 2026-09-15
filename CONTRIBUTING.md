# Contributing to Colab Ollama Bridge

Thank you for contributing to `colab-ollama-bridge`! Please review this guide before submitting pull requests.

---

## 1. Operating Rules & Boundaries

- Treat every committed byte, notebook cell, test fixture, and CI log as public.
- Never commit credentials, private IP addresses, internal DNS names, or local home paths.
- Follow test-driven development (TDD) for any behavioral change.
- Run `make check` before submitting a PR.

---

## 2. Development Setup

Prerequisites:
- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)
- [`bats-core`](https://github.com/bats-core/bats-core) and [`shellcheck`](https://www.shellcheck.net/)

```bash
# Clone the repository
git clone https://github.com/Vidoxlabs/colab-ollama-bridge.git
cd colab-ollama-bridge

# Install Python dependencies
make install
```

---

## 3. Running Verification Gates

```bash
# Lint and format checks
make lint

# Run all unit and integration tests
make test

# Run public-tree zero-leak scanner
make scan

# Run comprehensive repository check
make check
```

---

## 4. Pull Request Process

1. Create a descriptive feature branch from `main`.
2. Commit with [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...`).
3. Ensure all automated checks pass locally with `make check`.
4. Submit PR against `main` using the repository's pull request template.
