"""Tests for config/model-profiles.json and GPU VRAM profile mapping."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config" / "model-profiles.json"
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def load_profiles() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def select_profile(vram_mib: int, profiles: list[dict], fallback: dict) -> dict:
    for profile in profiles:
        if vram_mib >= profile.get("min_vram_mib", 0):
            return profile
    return fallback


def test_model_profiles_structure():
    data = load_profiles()
    assert "profiles" in data
    assert "default_fallback" in data

    profiles = data["profiles"]
    assert len(profiles) >= 4

    families = [p["gpu_family"] for p in profiles]
    assert "A100" in families
    assert "L4" in families
    assert "T4" in families


def test_threshold_a100_boundary():
    data = load_profiles()
    profiles = data["profiles"]
    fallback = data["default_fallback"]

    # >= 36 GiB (36864 MiB)
    prof = select_profile(40960, profiles, fallback)
    assert prof["model"] == "qwen2.5-coder:32b"
    assert prof["context_length"] == 16384
    assert prof["gpu_family"] == "A100"

    prof_exact = select_profile(36864, profiles, fallback)
    assert prof_exact["model"] == "qwen2.5-coder:32b"


def test_threshold_l4_boundary():
    data = load_profiles()
    profiles = data["profiles"]
    fallback = data["default_fallback"]

    # >= 20 GiB (20480 MiB) up to 36863 MiB
    prof = select_profile(23034, profiles, fallback)
    assert prof["model"] == "qwen2.5-coder:14b"
    assert prof["context_length"] == 16384
    assert prof["gpu_family"] == "L4"

    prof_boundary = select_profile(36863, profiles, fallback)
    assert prof_boundary["model"] == "qwen2.5-coder:14b"


def test_threshold_t4_boundary():
    data = load_profiles()
    profiles = data["profiles"]
    fallback = data["default_fallback"]

    # >= 12 GiB (12288 MiB) up to 20479 MiB
    prof = select_profile(15109, profiles, fallback)
    assert prof["model"] == "qwen2.5-coder:7b"
    assert prof["context_length"] == 16384
    assert prof["gpu_family"] == "T4"

    prof_min = select_profile(12288, profiles, fallback)
    assert prof_min["model"] == "qwen2.5-coder:7b"


def test_threshold_fallback_boundary():
    data = load_profiles()
    profiles = data["profiles"]
    fallback = data["default_fallback"]

    # < 12 GiB (< 12288 MiB)
    prof = select_profile(8192, profiles, fallback)
    assert prof["model"] == "qwen2.5-coder:3b"
    assert prof["context_length"] == 8192

    prof_zero = select_profile(0, profiles, fallback)
    assert prof_zero["model"] == "qwen2.5-coder:3b"


def test_fixtures_against_profiles():
    data = load_profiles()
    profiles = data["profiles"]
    fallback = data["default_fallback"]

    # Test A100 fixture
    a100_vram = int((FIXTURES_DIR / "nvidia-smi-a100.txt").read_text().split(",")[2].strip())
    assert select_profile(a100_vram, profiles, fallback)["gpu_family"] == "A100"

    # Test L4 fixture
    l4_vram = int((FIXTURES_DIR / "nvidia-smi-l4.txt").read_text().split(",")[2].strip())
    assert select_profile(l4_vram, profiles, fallback)["gpu_family"] == "L4"

    # Test T4 fixture
    t4_vram = int((FIXTURES_DIR / "nvidia-smi-t4.txt").read_text().split(",")[2].strip())
    assert select_profile(t4_vram, profiles, fallback)["gpu_family"] == "T4"
