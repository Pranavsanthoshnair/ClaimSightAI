"""Quick credit check on both OpenRouter keys."""
import sys, os, requests, base64, io
sys.path.insert(0, "code")
from dotenv import load_dotenv
load_dotenv()
from PIL import Image

key1 = os.getenv("OPENROUTER_API_KEY", "")
key2 = os.getenv("OPENROUTER_API_KEY_BACKUP", "")
print(f"Key1 (primary) : ...{key1[-8:]}")
print(f"Key2 (backup)  : ...{key2[-8:]}")

# Tiny image — minimal token cost
buf = io.BytesIO()
Image.new("RGB", (10, 10), (200, 100, 50)).save(buf, format="JPEG")
b64 = base64.b64encode(buf.getvalue()).decode()
data_url = f"data:image/jpeg;base64,{b64}"

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [
    "qwen/qwen2.5-vl-72b-instruct",
    "meta-llama/llama-3.2-11b-vision-instruct",
    "anthropic/claude-3-haiku",
]

for label, key in [("KEY1 (primary)", key1), ("KEY2 (backup)", key2)]:
    print(f"\n=== {label} ===")
    for m in MODELS:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                   "X-Title": "ClaimSight AI - Test"}
        payload = {
            "model": m,
            "max_tokens": 32,
            "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": "Say ok. Reply JSON: {\"ok\":true}"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]}
            ],
        }
        r = requests.post(URL, json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            print(f"  OK  {m}")
        else:
            err = r.json().get("error", {}).get("message", "?")[:100]
            print(f"  {r.status_code} {m}")
            print(f"      {err}")
