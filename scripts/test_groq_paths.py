#!/usr/bin/env python3
"""Compare Groq responses via LiteLLM vs direct Groq HTTP client.

Usage:
  cd ~/diabetes-buddy
  source venv/bin/activate
  python scripts/test_groq_paths.py

Requires:
  - GROQ_API_KEY in environment
"""

import json
import os
import sys
import time
from typing import Any, Dict

import requests
from dotenv import load_dotenv


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def run_litellm(prompt: str) -> Dict[str, Any]:
    from litellm import completion

    started = time.time()
    response = completion(
        model="groq/openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=200,
    )
    elapsed = time.time() - started

    choice = response.choices[0]
    msg = getattr(choice, "message", None)
    content = ""
    reasoning = ""
    if msg is not None:
        content = getattr(msg, "content", "") or ""
        reasoning = getattr(msg, "reasoning", "") or ""

    return {
        "path": "litellm",
        "elapsed_s": round(elapsed, 3),
        "content": content,
        "reasoning": reasoning,
        "raw_finish_reason": getattr(choice, "finish_reason", None),
    }


def run_direct_groq(prompt: str, api_key: str) -> Dict[str, Any]:
    urls = [
        "https://api.groq.com/openai/v1/chat/completions",
        "https://api.groq.com/v1/chat/completions",
    ]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-oss-20b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 200,
    }

    last_error = None
    for url in urls:
        started = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            elapsed = time.time() - started
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = msg.get("content", "") or ""
            reasoning = msg.get("reasoning", "") or ""

            return {
                "path": f"direct_groq_http ({url})",
                "elapsed_s": round(elapsed, 3),
                "content": content,
                "reasoning": reasoning,
                "raw_finish_reason": choice.get("finish_reason"),
            }
        except Exception as e:
            last_error = e
            continue

    raise last_error


def print_result(result: Dict[str, Any]) -> None:
    print("\n" + "=" * 80)
    print(f"Path: {result['path']}")
    print(f"Elapsed: {result['elapsed_s']}s")
    print(f"Content len: {len(result['content'])}")
    print(f"Reasoning len: {len(result['reasoning'])}")
    print(f"Finish reason: {result['raw_finish_reason']}")
    print("Content:")
    print(result["content"])
    if result["reasoning"]:
        print("\nReasoning:")
        print(result["reasoning"])


def main() -> int:
    load_dotenv()
    prompt = "Say hello in one sentence."

    try:
        api_key = _env("GROQ_API_KEY")
    except RuntimeError as e:
        print(str(e))
        return 1

    try:
        litellm_result = run_litellm(prompt)
        print_result(litellm_result)
    except Exception as e:
        print("\n" + "=" * 80)
        print("Path: litellm")
        print(f"Error: {e}")

    try:
        direct_result = run_direct_groq(prompt, api_key)
        print_result(direct_result)
    except Exception as e:
        print("\n" + "=" * 80)
        print("Path: direct_groq_http")
        print(f"Error: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
