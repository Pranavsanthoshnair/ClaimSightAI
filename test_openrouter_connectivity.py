"""OpenRouter connectivity test — verifies the API key and primary model are reachable.

Replaces the removed test_gemini.py. Tests:
1. OPENROUTER_API_KEY is present in environment.
2. Primary model (Qwen2.5-VL) responds to a simple text call.
3. Secondary model (Llama-3.2-90B-Vision) is reachable.
"""

import sys
import os

sys.path.insert(0, "code")
from dotenv import load_dotenv

load_dotenv(override=True)

key = os.getenv("OPENROUTER_API_KEY", "")
primary = os.getenv("OPENROUTER_MODEL_PRIMARY", "qwen/qwen2.5-vl-72b-instruct")
secondary = os.getenv("OPENROUTER_MODEL_SECONDARY", "meta-llama/llama-3.2-90b-vision-instruct")
tertiary = os.getenv("OPENROUTER_MODEL_TERTIARY", "mistralai/pixtral-large-2411")

print(f"OPENROUTER_API_KEY set: {bool(key)}")
print(f"Key prefix: {key[:12]}..." if key else "Key: NOT SET")
print(f"Provider chain:")
print(f"  T1 (Primary):   {primary}")
print(f"  T2 (Secondary): {secondary}")
print(f"  T3 (Tertiary):  {tertiary}")

if not key:
    print("\nERROR: OPENROUTER_API_KEY is not set. Cannot test connectivity.")
    sys.exit(1)

import requests
import json

_URL = "https://openrouter.ai/api/v1/chat/completions"
_HEADERS = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com/multi-modal-evidence-review",
    "X-Title": "ClaimSight AI Connectivity Test",
}


def test_model(model_name: str) -> bool:
    """Send a minimal text-only call to verify the model is accessible."""
    payload = {
        "model": model_name,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": "You are a JSON API. Reply with valid JSON only."},
            {"role": "user", "content": 'Reply with exactly: {"ok": true, "model": "working"}'},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post(_URL, json=payload, headers=_HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(content)
        print(f"  SUCCESS: {parsed}")
        return True
    except Exception as e:
        print(f"  ERROR: {str(e)[:200]}")
        return False


print(f"\n--- Testing T1 ({primary}) ---")
t1_ok = test_model(primary)

print(f"\n--- Testing T2 ({secondary}) ---")
t2_ok = test_model(secondary)

print(f"\n--- Testing T3 ({tertiary}) ---")
t3_ok = test_model(tertiary)

print("\n=== CONNECTIVITY SUMMARY ===")
print(f"  T1 Qwen2.5-VL:   {'PASS' if t1_ok else 'FAIL'}")
print(f"  T2 Llama Vision: {'PASS' if t2_ok else 'FAIL'}")
print(f"  T3 Pixtral Large:{'PASS' if t3_ok else 'FAIL'}")

if not (t1_ok or t2_ok or t3_ok):
    print("\nSTATUS: ALL PROVIDERS UNREACHABLE — check your OPENROUTER_API_KEY")
    sys.exit(1)
elif t1_ok:
    print("\nSTATUS: FULLY OPERATIONAL — primary provider ready")
else:
    print(f"\nSTATUS: DEGRADED — T1 unavailable, fallback providers active")
