"""Check actual credit balance on each key via OpenRouter /auth/key endpoint."""
import sys, os, requests
sys.path.insert(0, "code")
from dotenv import load_dotenv
load_dotenv()

keys = []
for var in ["OPENROUTER_API_KEY","OPENROUTER_API_KEY_2","OPENROUTER_API_KEY_3",
            "OPENROUTER_API_KEY_4","OPENROUTER_API_KEY_5"]:
    k = os.getenv(var, "")
    if k and k not in keys:
        keys.append((var, k))

print(f"Checking {len(keys)} keys...\n")
URL = "https://openrouter.ai/api/v1/auth/key"

for var, key in keys:
    r = requests.get(URL, headers={"Authorization": f"Bearer {key}"}, timeout=10)
    if r.status_code == 200:
        data = r.json().get("data", {})
        label        = data.get("label", "unnamed")
        limit        = data.get("limit")          # None = unlimited (paid)
        limit_remain = data.get("limit_remaining")
        usage        = data.get("usage", 0)
        is_free_tier = data.get("is_free_tier", False)
        rate_limit   = data.get("rate_limit", {})
        print(f"{var}: ...{key[-8:]}")
        print(f"  Label          : {label}")
        print(f"  Free tier      : {is_free_tier}")
        print(f"  Credit limit   : {limit}")
        print(f"  Credits remain : {limit_remain}")
        print(f"  Usage ($)      : {usage}")
        print(f"  Rate limit     : {rate_limit}")
    else:
        print(f"{var}: ...{key[-8:]}  => HTTP {r.status_code}: {r.text[:100]}")
    print()
