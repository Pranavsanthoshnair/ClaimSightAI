"""Full vision pipeline diagnostic — run from repo root."""
import sys, json, os
sys.path.insert(0, "code")

from dotenv import load_dotenv
load_dotenv(".env")

from pathlib import Path
from config import Settings
from services.model_service import ModelService
from prompts.templates import VISION_EVIDENCE_SYSTEM, VISION_EVIDENCE_USER, PROMPT_VERSION

repo = Path(".").resolve()
settings = Settings(repo_root=repo)

print(f"provider: {settings.model_provider}")
print(f"model:    {settings.vision_model}")
print(f"has_vlm:  {settings.has_vision_model}")
print(f"key set:  {bool(settings.gemini_api_key)}")
print(f"prompt:   {PROMPT_VERSION}")
print()

# Pick the first sample image
img_path = repo / "dataset/images/sample/case_001/img_1.jpg"
print(f"Image: {img_path}")
print(f"Exists: {img_path.exists()}")

image_bytes = img_path.read_bytes()
print(f"Bytes: {len(image_bytes)}")

from models.enums import IssueType, ObjectPart, RiskFlag, ClaimObject

ISSUE_TYPES_STR = ", ".join(f'"{v}"' for v in IssueType)
RISK_FLAGS_STR  = ", ".join(f'"{v}"' for v in RiskFlag)
PART_VALUES = ", ".join(f'"{v}"' for v in [
    ObjectPart.FRONT_BUMPER, ObjectPart.REAR_BUMPER, ObjectPart.DOOR,
    ObjectPart.HOOD, ObjectPart.WINDSHIELD, ObjectPart.SIDE_MIRROR,
    ObjectPart.HEADLIGHT, ObjectPart.TAILLIGHT, ObjectPart.FENDER,
    ObjectPart.QUARTER_PANEL, ObjectPart.BODY, ObjectPart.UNKNOWN,
])

prompt = VISION_EVIDENCE_USER.format(
    claim_object="car",
    claimed_part="rear_bumper",
    claimed_issue="dent",
    image_id="img_1",
    issue_type_values=ISSUE_TYPES_STR,
    object_part_values=PART_VALUES,
    risk_flag_values=RISK_FLAGS_STR,
)

print(f"\nPrompt length: {len(prompt)} chars")
print(f"System length: {len(VISION_EVIDENCE_SYSTEM)} chars")

# Call provider
svc = ModelService(settings=settings)
print("\n--- Calling Gemini ---")
try:
    raw = svc.inspect_image(VISION_EVIDENCE_SYSTEM, prompt, image_bytes)
    print(f"raw type:   {type(raw)}")
    print(f"raw length: {len(raw) if raw else 0}")
    print(f"raw preview: {str(raw)[:500]}")
except Exception as e:
    print(f"CALL FAILED: {e}")
    sys.exit(1)

# Parse JSON
import re
print("\n--- Parsing JSON ---")
try:
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = re.sub(r"^```(?:json)?\s*|```\s*$", "", raw.strip(), flags=re.M)
            data = json.loads(cleaned)
    print(f"Parse OK: {list(data.keys())}")
    print(f"object_present: {data.get('object_present')}")
    print(f"visible_parts:  {data.get('visible_parts')}")
    print(f"visible_issues: {data.get('visible_issues')}")
    print(f"supports_claim: {data.get('supports_claim')}")
    print(f"confidence:     {data.get('confidence')}")
    print(f"severity:       {data.get('severity')}")
    print(f"quality_flags:  {data.get('quality_flags')}")
    print(f"description:    {str(data.get('description',''))[:200]}")
except Exception as e:
    print(f"PARSE FAILED: {e}")
    print(f"raw was: {raw}")
    sys.exit(1)

# Coerce enums
print("\n--- Enum coercion ---")
def safe_enum(cls, v, default):
    try: return cls(v)
    except: return default

def safe_list(cls, vals):
    result = []
    for v in (vals or []):
        try: result.append(cls(v))
        except Exception as e: print(f"  COERCE FAIL: {cls.__name__}({v!r}) -> {e}")
    return result

parts  = safe_list(ObjectPart, data.get("visible_parts", []))
issues = safe_list(IssueType,  data.get("visible_issues", []))
flags  = safe_list(RiskFlag,   data.get("quality_flags", []))
print(f"coerced parts:  {[p.value for p in parts]}")
print(f"coerced issues: {[i.value for i in issues]}")
print(f"coerced flags:  {[f.value for f in flags]}")
print(f"object_present: {data.get('object_present')}")

print("\n--- DIAGNOSIS ---")
if not data.get("object_present"):
    print("ROOT CAUSE: object_present is False/None — model says object not visible")
    print("Check step1_observations:", data.get("step1_observations", "N/A"))
elif not parts:
    print("ROOT CAUSE D: Taxonomy coercion — visible_parts raw values:", data.get("visible_parts"))
elif not issues:
    print("ROOT CAUSE D: Taxonomy coercion — visible_issues raw values:", data.get("visible_issues"))
else:
    print("Pipeline looks HEALTHY — object visible, parts found, issues found")
print("Done.")
