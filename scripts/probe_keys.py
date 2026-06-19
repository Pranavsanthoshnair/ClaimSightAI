"""Quick probe: test all 5 keys against Llama 11B + Claude Haiku."""
import sys, os, requests, base64, io
sys.path.insert(0, "code")
from dotenv import load_dotenv
load_dotenv()
from PIL import Image

# Build pool from env
keys = []
for var in ["OPENROUTER_API_KEY","OPENROUTER_API_KEY_2","OPENROUTER_API_KEY_3",
            "OPENROUTER_API_KEY_4","OPENROUTER_API_KEY_5"]:
    k = os.getenv(var, "")
    if k and k not in keys:
        keys.append(k)

print(f"Keys in pool: {len(keys)}")
for i, k in enumerate(keys, 1):
    print(f"  K{i}: ...{k[-8:]}")

buf = io.BytesIO()
Image.new("RGB",(8,8),(80,120,40)).save(buf,format="JPEG")
b64 = base64.b64encode(buf.getvalue()).decode()
data_url = f"data:image/jpeg;base64,{b64}"
URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [
    ("meta-llama/llama-3.2-11b-vision-instruct", "Llama 11B"),
    ("anthropic/claude-3-haiku",                 "Claude Haiku"),
]

print()
ok_pairs = []
for slug, name in MODELS:
    print(f"  Model: {name}")
    for i, key in enumerate(keys, 1):
        hdrs = {"Authorization":f"Bearer {key}","Content-Type":"application/json",
                "X-Title":"ClaimSight AI"}
        payload = {"model":slug,"max_tokens":16,
                   "messages":[{"role":"user","content":[
                       {"type":"text","text":"Reply: ok"},
                       {"type":"image_url","image_url":{"url":data_url}}
                   ]}]}
        r = requests.post(URL, json=payload, headers=hdrs, timeout=12)
        if r.status_code == 200:
            print(f"    K{i} OK")
            ok_pairs.append((slug,key))
            break
        else:
            err = r.json().get("error",{}).get("message","?")[:60]
            print(f"    K{i} {r.status_code}: {err}")

print()
if ok_pairs:
    print(f"SUCCESS: {len(ok_pairs)} model(s) responding. Pipeline is ready.")
else:
    print("ALL KEYS EXHAUSTED on all models. Add credits at openrouter.ai/credits")
