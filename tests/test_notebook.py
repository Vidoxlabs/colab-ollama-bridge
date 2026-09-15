"""Tests for notebooks/colab_ollama.ipynb schema, outputs, and security rules."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
NOTEBOOK_PATH = ROOT / "notebooks" / "colab_ollama.ipynb"
VALIDATOR_PATH = ROOT / "scripts" / "validate-notebook.py"
EXPECTED_BADGE = "https://colab.research.google.com/github/Vidoxlabs/colab-ollama-bridge/blob/main/notebooks/colab_ollama.ipynb"


def test_notebook_exists():
    assert NOTEBOOK_PATH.exists()


def test_notebook_structure_and_empty_outputs():
    with open(NOTEBOOK_PATH, encoding="utf-8") as f:
        nb = json.load(f)

    assert nb["nbformat"] == 4
    cells = nb["cells"]
    assert len(cells) >= 8

    for idx, cell in enumerate(cells):
        if cell["cell_type"] == "code":
            assert cell.get("outputs") == [], f"Cell {idx} has committed outputs"
            assert cell.get("execution_count") is None, f"Cell {idx} has execution_count"


def test_badge_url_present():
    with open(NOTEBOOK_PATH, encoding="utf-8") as f:
        content = f.read()
    assert EXPECTED_BADGE in content


def test_validate_notebook_script_execution():
    res = subprocess.run(
        ["python3", str(VALIDATOR_PATH), str(NOTEBOOK_PATH)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Validator failed: {res.stderr}"
    assert "PASSED" in res.stdout
