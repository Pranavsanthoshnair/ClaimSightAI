"""Test all 3 OpenRouter vision tiers with the new max_tokens fix."""
import sys, os
sys.path.insert(0, "code")
from dotenv import load_dotenv
load_dotenv()

from services.providers.openrouter_provider import OpenRouterProvider
from PIL import Image
import io

key = os.getenv("OPENROUTER_API_KEY", "")

buf = io.BytesIO()
img = Image.new("RGB", (100, 100), color=(255, 100, 50))
img.save(buf, format="JPEG", quality=85)
image_bytes = buf.getvalue()
print(f"Test image: {len(image_bytes)} bytes")

SYSTEM = "You are a JSON API. Reply only with valid JSON."
PROMPT = 'Describe the dominant color of this image. Reply with JSON: {"color": "...", "ok": true}'

tiers = [
    ("T1", "qwen/qwen2.5-vl-72b-instruct"),
    ("T2", "meta-llama/llama-3.2-11b-vision-instruct"),
    ("T3", "anthropic/claude-3-haiku"),
]

results = {}
for label, model in tiers:
    print(f"\n--- Testing {label}: {model} ---")
    p = OpenRouterProvider(api_key=key, model=model, max_tokens=1024)
    try:
        result = p.analyze_image(system=SYSTEM, prompt=PROMPT, image_bytes=image_bytes)
        print(f"  SUCCESS: {result[:120]}")
        results[label] = "PASS"
    except Exception as e:
        print(f"  FAIL: {str(e)[:200]}")
        results[label] = "FAIL"

print("\n=== SUMMARY ===")
for label, status in results.items():
    print(f"  {label}: {status}")

all_pass = all(v == "PASS" for v in results.values())
sys.exit(0 if all_pass else 1)
