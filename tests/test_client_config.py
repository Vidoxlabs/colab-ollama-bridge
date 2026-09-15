"""Tests for scripts/generate-client-config.py and example configurations."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT_PATH = ROOT / "scripts" / "generate-client-config.py"
EXAMPLES_DIR = ROOT / "examples"


def strip_jsonc_comments(text: str) -> str:
    """Remove line comments from JSONC."""
    return re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)


def test_generate_quick_config():
    res = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            "--model",
            "qwen2.5-coder:7b",
            "--mode",
            "quick",
            "--json-only",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(res.stdout)
    assert "$schema" in data
    provider = data["provider"]["colab-ollama"]
    assert provider["options"]["baseURL"] == "{env:COLAB_OLLAMA_BASE_URL}/v1"
    assert provider["options"]["apiKey"] == "{env:COLAB_BRIDGE_API_KEY}"
    assert "headers" not in provider["options"]
    assert "qwen2.5-coder:7b" in provider["models"]


def test_generate_access_config():
    res = subprocess.run(
        [
            "python3",
            str(SCRIPT_PATH),
            "--model",
            "qwen2.5-coder:14b",
            "--mode",
            "access",
            "--json-only",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(res.stdout)
    provider = data["provider"]["colab-ollama"]
    headers = provider["options"]["headers"]
    assert headers["CF-Access-Client-Id"] == "{env:CF_ACCESS_CLIENT_ID}"
    assert headers["CF-Access-Client-Secret"] == "{env:CF_ACCESS_CLIENT_SECRET}"


def test_no_secrets_in_generated_output():
    res = subprocess.run(
        ["python3", str(SCRIPT_PATH), "--model", "qwen2.5-coder:32b", "--mode", "access"],
        capture_output=True,
        text=True,
        check=True,
    )
    output = res.stdout
    # Must only contain {env:...} references
    assert "{env:COLAB_BRIDGE_API_KEY}" in output
    assert "sk-" not in output
    assert "password" not in output.lower()


def test_example_files_parseable():
    quick_file = EXAMPLES_DIR / "opencode.example.jsonc"
    quick_raw = strip_jsonc_comments(quick_file.read_text())
    quick_data = json.loads(quick_raw)
    assert "colab-ollama" in quick_data["provider"]

    access_file = EXAMPLES_DIR / "opencode.access.example.jsonc"
    access_raw = strip_jsonc_comments(access_file.read_text())
    access_data = json.loads(access_raw)
    assert "colab-ollama" in access_data["provider"]
    assert "CF-Access-Client-Id" in access_data["provider"]["colab-ollama"]["options"]["headers"]

    mcp_file = EXAMPLES_DIR / "antigravity.mcp_config.json"
    mcp_data = json.loads(mcp_file.read_text())
    assert "mcpServers" in mcp_data
    assert "colab" in mcp_data["mcpServers"]


def test_colab_mcp_config_pinned():
    mcp_file = EXAMPLES_DIR / "antigravity.mcp_config.json"
    mcp_data = json.loads(mcp_file.read_text())
    args = mcp_data["mcpServers"]["colab"]["args"]
    assert any("@v1.0.2" in arg for arg in args), "colab-mcp should be pinned to @v1.0.2"
    assert not any("@main" in arg for arg in args), "colab-mcp must not use unpinned @main"
