"""Quick live test of paid models with new free-tier keys vs paid models."""
import sys, os, requests, base64, io
sys.path.insert(0, "code")
from dotenv import load_dotenv; load_dotenv()
from PIL import Image

buf = io.BytesIO()
Image.new("RGB", (8, 8), (80, 120, 40)).save(buf, format="JPEG")
data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
URL = "https://openrouter.ai/api/v1/chat/completions"

PAID_MODELS = [
    "meta-llama/llama-3.2-11b-vision-instruct",
    "anthropic/claude-3-haiku",
    "qwen/qwen2.5-vl-72b-instruct",
]

keys = [(v, os.getenv(v, "")) for v in
        ["OPENROUTER_API_KEY","OPENROUTER_API_KEY_2","OPENROUTER_API_KEY_3",
         "OPENROUTER_API_KEY_4","OPENROUTER_API_KEY_5"] if os.getenv(v)]

print("Testing PAID models with each key (just K1 for speed):\n")
k1 = keys[0][1]
for m in PAID_MODELS:
    hdrs    = {"Authorization": f"Bearer {k1}", "Content-Type": "application/json", "X-Title": "ClaimSight AI"}
    payload = {"model": m, "max_tokens": 16,
               "messages": [{"role": "user", "content": [
                   {"type": "text", "text": "Say ok."},
                   {"type": "image_url", "image_url": {"url": data_url}}]}]}
    r = requests.post(URL, json=payload, headers=hdrs, timeout=12)
    if r.status_code == 200:
        print(f"  OK   {m}")
    else:
        err = r.json().get("error", {}).get("message", "?")[:90]
        print(f"  {r.status_code}  {m}")
        print(f"       {err}")
