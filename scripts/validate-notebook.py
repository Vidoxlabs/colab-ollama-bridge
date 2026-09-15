#!/usr/bin/env python3
"""Colab Ollama Bridge - Notebook Safety and Schema Validator.

Validates that Jupyter notebooks adhere to security invariants:
1. Valid nbformat 4.
2. Zero committed outputs and execution counts.
3. No committed secrets or credential-shaped literals.
4. No anti-idle or click automation scripts.
5. Verifies canonical Open in Colab badge link.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BADGE_URL = "https://colab.research.google.com/github/Vidoxlabs/colab-ollama-bridge/blob/main/notebooks/colab_ollama.ipynb"

ANTI_IDLE_PATTERNS = [
    re.compile(r"ClickConnect", re.IGNORECASE),
    re.compile(r"auto-click", re.IGNORECASE),
    re.compile(r"colab\.research\.google\.com#keepalive", re.IGNORECASE),
    re.compile(r"setInterval\s*\(\s*function", re.IGNORECASE),
]

SECRET_PATTERNS = [
    re.compile(r"['\"][a-zA-Z0-9_-]{32,}['\"]"),  # suspicious long secret literal
    re.compile(r"ghp_[A-Za-z0-9_]{36}"),
    re.compile(r"gho_[A-Za-z0-9_]{36}"),
    re.compile(r"AIza[0-9A-Za-z-_]{35}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
]


def validate_notebook(nb_path: Path) -> list[str]:
    """Inspect notebook for compliance with Vidoxlabs security invariants."""
    errors: list[str] = []

    if not nb_path.exists():
        return [f"Notebook not found: {nb_path}"]

    try:
        with open(nb_path, encoding="utf-8") as f:
            nb = json.load(f)
    except Exception as e:
        return [f"Failed to parse JSON in {nb_path}: {e}"]

    # 1. Format version
    if nb.get("nbformat") != 4:
        errors.append(f"Expected nbformat 4, found {nb.get('nbformat')}")

    cells = nb.get("cells", [])
    if not cells:
        errors.append("Notebook contains no cells")
        return errors

    badge_found = False

    for idx, cell in enumerate(cells):
        cell_type = cell.get("cell_type")
        source = "".join(cell.get("source", []))

        # Check for badge in markdown
        if cell_type == "markdown" and BADGE_URL in source:
            badge_found = True

        # Check for anti-idle patterns
        for pattern in ANTI_IDLE_PATTERNS:
            if pattern.search(source):
                errors.append(
                    f"Cell {idx}: Disallowed anti-idle / keepalive script detected ({pattern.pattern})"
                )

        # Code cell specific validation
        if cell_type == "code":
            outputs = cell.get("outputs")
            if outputs:
                errors.append(
                    f"Cell {idx}: Found committed outputs ({len(outputs)} items). Outputs must be empty []"
                )

            execution_count = cell.get("execution_count")
            if execution_count is not None:
                errors.append(f"Cell {idx}: Found execution_count {execution_count}. Must be null")

            # Check for hardcoded secrets
            for pattern in SECRET_PATTERNS:
                # Exclude harmless examples or sha256 checksums if labeled
                matches = pattern.findall(source)
                for m in matches:
                    if "sha256" in m.lower() or "00000000" in m or "sample" in m.lower():
                        continue
                    # Ignore pure comment lines
                    errors.append(
                        f"Cell {idx}: Potential hardcoded credential pattern detected: {m[:8]}..."
                    )

    if not badge_found:
        errors.append(f"Required Open in Colab badge with target '{BADGE_URL}' was not found")

    return errors


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python validate-notebook.py <notebook.ipynb> [notebook2.ipynb ...]")
        sys.exit(1)

    all_passed = True
    for path_str in sys.argv[1:]:
        path = Path(path_str)
        errors = validate_notebook(path)
        if errors:
            all_passed = False
            print(f"Validation FAILED for {path}:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
        else:
            print(f"Validation PASSED for {path}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
