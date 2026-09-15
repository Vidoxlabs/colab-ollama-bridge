#!/usr/bin/env python3
"""Colab Ollama Bridge - Client Configuration Generator.

Emits sanitized OpenCode provider configuration snippets referencing
environment variables ({env:...}), never raw secret values.
"""

from __future__ import annotations

import argparse
import json


def generate_opencode_config(
    model: str = "qwen2.5-coder:7b",
    context_limit: int = 16384,
    output_limit: int = 8192,
    mode: str = "quick",
) -> dict:
    """Build OpenCode configuration structure."""
    options: dict = {
        "baseURL": "{env:COLAB_OLLAMA_BASE_URL}/v1",
        "apiKey": "{env:COLAB_BRIDGE_API_KEY}",
    }

    if mode == "access":
        options["headers"] = {
            "CF-Access-Client-Id": "{env:CF_ACCESS_CLIENT_ID}",
            "CF-Access-Client-Secret": "{env:CF_ACCESS_CLIENT_SECRET}",
        }

    model_display_name = f"Qwen 2.5 Coder ({model})"
    if "7b" in model:
        model_display_name = "Qwen 2.5 Coder 7B (Colab)"
    elif "14b" in model:
        model_display_name = "Qwen 2.5 Coder 14B (Colab)"
    elif "32b" in model:
        model_display_name = "Qwen 2.5 Coder 32B (Colab)"
    elif "3b" in model:
        model_display_name = "Qwen 2.5 Coder 3B (Colab)"

    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "colab-ollama": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Colab Ollama Bridge",
                "options": options,
                "models": {
                    model: {
                        "name": model_display_name,
                        "limit": {
                            "context": context_limit,
                            "output": output_limit,
                        },
                    }
                },
            }
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate sanitized OpenCode provider configuration."
    )
    parser.add_argument("--model", default="qwen2.5-coder:7b", help="Model identifier")
    parser.add_argument("--context", type=int, default=16384, help="Runtime context limit")
    parser.add_argument("--output-limit", type=int, default=8192, help="Output token limit")
    parser.add_argument(
        "--mode", choices=["quick", "access", "named"], default="quick", help="Tunnel mode"
    )
    parser.add_argument(
        "--json-only", action="store_true", help="Emit raw JSON without header comments"
    )
    args = parser.parse_args()

    mode = "access" if args.mode in ("access", "named") else "quick"
    config = generate_opencode_config(
        model=args.model,
        context_limit=args.context,
        output_limit=args.output_limit,
        mode=mode,
    )

    formatted_json = json.dumps(config, indent=2)

    if args.json_only:
        print(formatted_json)
        return

    print("// =============================================================================")
    print(f"// OpenCode Configuration for Colab Ollama Bridge ({args.mode.upper()} MODE)")
    print("// Add this block to your OpenCode configuration (~/.config/opencode/opencode.json)")
    print("// Ensure environment variables are exported in your local shell profile.")
    print("// =============================================================================")
    print(formatted_json)


if __name__ == "__main__":
    main()
