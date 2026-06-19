"""Quick test of Gemini API availability."""
import sys
sys.path.insert(0, 'code')
from dotenv import load_dotenv
load_dotenv(override=True)
import os
import time

key = os.getenv('GEMINI_API_KEY', '')
print('GEMINI_KEY set:', bool(key))
print('GEMINI_KEY prefix:', key[:10] if key else 'N/A')

try:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    
    # Simple text-only test
    print('Testing text-only call...')
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='Reply with exactly this JSON: {"ok": true, "status": "working"}',
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            temperature=0.0,
        )
    )
    print('SUCCESS:', response.text[:200])
except Exception as e:
    print('ERROR:', str(e)[:300])
    # Check for quota vs rate limit
    err_str = str(e)
    if '429' in err_str:
        if 'quota' in err_str.lower() or 'QUOTA_EXCEEDED' in err_str:
            print('STATUS: QUOTA EXCEEDED (daily limit hit)')
        else:
            print('STATUS: RATE LIMITED (temporary, will recover)')
    elif '403' in err_str:
        print('STATUS: FORBIDDEN (bad key or key disabled)')
