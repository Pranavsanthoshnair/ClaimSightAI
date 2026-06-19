"""Quick connectivity test for OpenRouter fallback."""
import sys
sys.path.insert(0, 'code')
from dotenv import load_dotenv
load_dotenv(override=True)
import os
import requests

key = os.getenv('OPENROUTER_API_KEY', '')
gemini_key = os.getenv('GEMINI_API_KEY', '')
print('GEMINI_KEY set:', bool(gemini_key))
print('OPENROUTER_KEY set:', bool(key))
print('OPENROUTER_KEY prefix:', key[:15] if key else 'N/A')
print('MODEL_PROVIDER:', os.getenv('MODEL_PROVIDER'))

if not key:
    print('ERROR: OpenRouter key not loaded')
    sys.exit(1)

payload = {
    'model': 'google/gemini-2.5-flash',
    'messages': [{'role': 'user', 'content': 'Reply with exactly this JSON: {"ok": true}'}],
    'response_format': {'type': 'json_object'},
    'max_tokens': 20
}
headers = {
    'Authorization': f'Bearer {key}',
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://github.com/multi-modal-evidence-review',
}
try:
    resp = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        json=payload,
        headers=headers,
        timeout=30
    )
    print('OpenRouter status:', resp.status_code)
    print('OpenRouter response:', resp.text[:300])
except Exception as e:
    print('OpenRouter error:', e)
