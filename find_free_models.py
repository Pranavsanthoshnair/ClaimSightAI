"""Find all currently free vision-capable models on OpenRouter."""
import sys, os, requests
sys.path.insert(0, "code")
from dotenv import load_dotenv; load_dotenv()

k1 = os.getenv("OPENROUTER_API_KEY", "")
r  = requests.get("https://openrouter.ai/api/v1/models",
                  headers={"Authorization": f"Bearer {k1}"}, timeout=15)
models = r.json().get("data", [])

free_vision = []
for m in models:
    pricing   = m.get("pricing", {})
    prompt_p  = pricing.get("prompt", "999") or "999"
    modality  = str(m.get("architecture", {}).get("modality", ""))
    is_free   = float(prompt_p) == 0.0
    has_vision = any(t in modality for t in ["image", "vision", "multimodal"])
    if is_free and has_vision:
        free_vision.append(m)

print(f"Free vision models available: {len(free_vision)}\n")
for m in free_vision:
    slug = m["id"]
    ctx  = m.get("context_length", "?")
    print(f"  {slug}  (ctx={ctx})")
