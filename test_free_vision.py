"""Test which free vision models actually work for image analysis."""
import sys, os, requests, base64, io
sys.path.insert(0, "code")
from dotenv import load_dotenv; load_dotenv()
from PIL import Image

k1 = os.getenv("OPENROUTER_API_KEY", "")
print(f"Using key: ...{k1[-8:]}\n")

buf = io.BytesIO()
Image.new("RGB", (20, 20), (80, 120, 40)).save(buf, format="JPEG")
b64      = base64.b64encode(buf.getvalue()).decode()
data_url = f"data:image/jpeg;base64,{b64}"
URL      = "https://openrouter.ai/api/v1/chat/completions"

CANDIDATES = [
    "google/gemma-4-27b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nex-agi/nex-n2-pro:free",
    "openrouter/free",
]

working = []
for model in CANDIDATES:
    hdrs = {
        "Authorization": f"Bearer {k1}",
        "Content-Type": "application/json",
        "X-Title": "ClaimSight AI",
    }
    payload = {
        "model": model,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": [
            {"type": "text",      "text": "What color is this tiny square image? Reply in 3 words."},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
    }
    r = requests.post(URL, json=payload, headers=hdrs, timeout=20)
    if r.status_code == 200:
        ans = r.json()["choices"][0]["message"]["content"][:60]
        print(f"  OK   {model}")
        print(f"       => {ans}")
        working.append(model)
    else:
        err = r.json().get("error", {}).get("message", "?")[:80]
        print(f"  {r.status_code}  {model}")
        print(f"       {err}")

print(f"\nWorking free vision models: {len(working)}")
for m in working:
    print(f"  {m}")
