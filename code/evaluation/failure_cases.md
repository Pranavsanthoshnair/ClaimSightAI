# Failure Cases

Total incorrect predictions: **14**

## Ranked Failure Categories

| Rank | Category | Count | % of Errors |
|------|----------|-------|-------------|
| 1 | `object_part_failure` | 4 | 28.6% |
| 2 | `issue_type_mismatch` | 3 | 21.4% |
| 3 | `evidence_insufficiency` | 2 | 14.3% |
| 4 | `false_contradiction` | 2 | 14.3% |
| 5 | `image_quality_failure` | 1 | 7.1% |
| 6 | `claim_status_mismatch` | 1 | 7.1% |
| 7 | `false_support` | 1 | 7.1% |

## Object Part Failure (4 cases)

### user_006 (car)
- **Expected claim_status**: `not_enough_information`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `unknown` / `headlight`
- **Predicted issue/part**: `none` / `side_mirror`
- **Risk flags**: `none`
- **Field errors**: `{"issue_type": {"expected": "unknown", "predicted": "none"}, "object_part": {"expected": "headlight", "predicted": "side_mirror"}}`
- **GT justification**: The submitted image shows another part of the car and does not provide evidence for the headlight claim.
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed part 'headlight' is not visible; visible parts: side mirror, door. At least one submitted ima

### user_010 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `supported`
- **Expected issue/part**: `broken_part` / `hinge`
- **Predicted issue/part**: `broken_part` / `screen`
- **Risk flags**: `none`
- **Field errors**: `{"object_part": {"expected": "hinge", "predicted": "screen"}}`
- **GT justification**: The first image supports the claim because the hinge damage is visible.
- **Pred justification**: Visual evidence supports the claim. 1/2 image(s) support the claim (img_1). Visible issues: broken_part, none. Visible parts: screen, keyboard, base. 

### user_018 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `crack` / `screen`
- **Predicted issue/part**: `glass_shatter` / `keyboard`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "issue_type": {"expected": "crack", "predicted": "glass_shatter"}, "object_part": {"expected": "screen", "predicted": "keyboard"}}`
- **GT justification**: The image supports the claim because the laptop screen has visible cracking consistent with the user's screen damage report.
- **Pred justification**: No image fully supports the claim. 1 image(s) show partial evidence (img_1). Visible issues: glass_shatter. Visible parts: screen, keyboard.

### user_033 (package)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `unknown` / `unknown`
- **Predicted issue/part**: `none` / `box`
- **Risk flags**: `user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "not_enough_information"}, "issue_type": {"expected": "unknown", "predicted": "none"}, "object_part": {"expected": "unknown", "predicted": "box"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image does show a visible crease or dent, but the object shown is different from the claimed shipping box, so it does not support the user's crush
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed package is not visible in any image. At least one submitted image must clearly show the claim

## Issue Type Mismatch (3 cases)

### user_007 (car)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `supported`
- **Expected issue/part**: `broken_part` / `side_mirror`
- **Predicted issue/part**: `crack` / `side_mirror`
- **Risk flags**: `none`
- **Field errors**: `{"issue_type": {"expected": "broken_part", "predicted": "crack"}}`
- **GT justification**: The submitted image directly shows damage to the claimed side mirror.
- **Pred justification**: Visual evidence supports the claim. 1/1 image(s) support the claim (img_1). Visible issues: crack. Visible parts: side_mirror. [img_1] The side mirror

### user_008 (car)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `contradicted`
- **Expected issue/part**: `broken_part` / `front_bumper`
- **Predicted issue/part**: `dent` / `hood`
- **Risk flags**: `non_original_image;user_history_risk;claim_mismatch`
- **Field errors**: `{"issue_type": {"expected": "broken_part", "predicted": "dent"}, "object_part": {"expected": "front_bumper", "predicted": "hood"}}`
- **GT justification**: The image shows severe front-end damage rather than a scratch on the hood, so it does not support the user's hood-scratch claim.
- **Pred justification**: Visual evidence contradicts or does not match the claim. No image fully supports the claim. 1 image(s) show partial evidence (img_1). Visible issues: 

### user_011 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `supported`
- **Expected issue/part**: `stain` / `keyboard`
- **Predicted issue/part**: `water_damage` / `keyboard`
- **Risk flags**: `none`
- **Field errors**: `{"issue_type": {"expected": "stain", "predicted": "water_damage"}}`
- **GT justification**: The submitted image shows visible staining on the keyboard area.
- **Pred justification**: Visual evidence supports the claim. 1/1 image(s) support the claim (img_1). Visible issues: water_damage. Visible parts: keyboard. [img_1] The laptop 

## Evidence Insufficiency (2 cases)

### user_005 (car)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `scratch` / `rear_bumper`
- **Predicted issue/part**: `dent` / `rear_bumper`
- **Risk flags**: `user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "not_enough_information"}, "issue_type": {"expected": "scratch", "predicted": "dent"}}`
- **GT justification**: The images show only minor rear bumper scratching, so the severe damage claim is contradicted. User history also shows several rejected claims.
- **Pred justification**: No image fully supports the claim. 1 image(s) show partial evidence (img_2). Visible issues: dent, none. Visible parts: rear_bumper, taillight, fender

### user_020 (laptop)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `none` / `trackpad`
- **Predicted issue/part**: `none` / `trackpad`
- **Risk flags**: `user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "not_enough_information"}}`
- **GT justification**: The image shows the trackpad area but does not show clear physical damage, so it contradicts the user's physical damage claim. The user's prior claim 
- **Pred justification**: No image fully supports the claim. 1 image(s) show partial evidence (img_1). Visible issues: none. Visible parts: keyboard, trackpad.

## False Contradiction (2 cases)

### user_012 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `contradicted`
- **Expected issue/part**: `dent` / `corner`
- **Predicted issue/part**: `none` / `corner`
- **Risk flags**: `blurry_image;low_light_or_glare;claim_mismatch`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "contradicted"}, "issue_type": {"expected": "dent", "predicted": "none"}}`
- **GT justification**: The image set supports the claim because the corner dent is visible in the close-up.
- **Pred justification**: Visual evidence contradicts or does not match the claim. No image fully supports the claim. 1 image(s) show partial evidence (img_1). Visible issues: 

### user_030 (package)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `contradicted`
- **Expected issue/part**: `torn_packaging` / `seal`
- **Predicted issue/part**: `torn_packaging` / `package_side`
- **Risk flags**: `claim_mismatch`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "contradicted"}, "object_part": {"expected": "seal", "predicted": "package_side"}}`
- **GT justification**: The first image supports the claim by showing torn-open packaging.
- **Pred justification**: Visual evidence contradicts or does not match the claim. No image fully supports the claim. 2 image(s) show partial evidence (img_1, img_2). Visible i

## Image Quality Failure (1 cases)

### user_031 (package)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `water_damage` / `package_side`
- **Predicted issue/part**: `water_damage` / `unknown`
- **Risk flags**: `blurry_image;user_history_risk;manual_review_required`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "object_part": {"expected": "package_side", "predicted": "unknown"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image supports the water damage claim, but user history shows prior package claims often needed evidence review.
- **Pred justification**: No valid images were available for assessment. Missing: Readable image showing package unknown with visible water damage damage.

## Claim Status Mismatch (1 cases)

### user_032 (package)
- **Expected claim_status**: `not_enough_information`
- **Predicted claim_status**: `contradicted`
- **Expected issue/part**: `unknown` / `contents`
- **Predicted issue/part**: `none` / `contents`
- **Risk flags**: `manual_review_required;claim_mismatch`
- **Field errors**: `{"claim_status": {"expected": "not_enough_information", "predicted": "contradicted"}, "issue_type": {"expected": "unknown", "predicted": "none"}, "evidence_standard_met": {"expected": "false", "predicted": "true"}}`
- **GT justification**: The package contents are unclear, so the missing-product claim cannot be verified from the submitted images.
- **Pred justification**: Visual evidence contradicts or does not match the claim. No image fully supports the claim. 1 image(s) show partial evidence (img_1). Visible issues: 

## False Support (1 cases)

### user_034 (package)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `supported`
- **Expected issue/part**: `none` / `seal`
- **Predicted issue/part**: `torn_packaging` / `seal`
- **Risk flags**: `text_instruction_present;user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "supported"}, "issue_type": {"expected": "none", "predicted": "torn_packaging"}}`
- **GT justification**: The visible package seal does not show torn-open packaging. Any instruction-like text inside the image should be ignored, and user history requires re
- **Pred justification**: Visual evidence supports the claim. 2/2 image(s) support the claim (img_1, img_2). Visible issues: torn_packaging. Visible parts: seal, box. [img_1] A
