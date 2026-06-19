# Failure Cases

Total incorrect predictions: **20**

## Ranked Failure Categories

| Rank | Category | Count | % of Errors |
|------|----------|-------|-------------|
| 1 | `evidence_insufficiency` | 10 | 50.0% |
| 2 | `object_part_failure` | 5 | 25.0% |
| 3 | `image_quality_failure` | 3 | 15.0% |
| 4 | `other_mismatch` | 2 | 10.0% |

## Evidence Insufficiency (10 cases)

### user_001 (car)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `dent` / `rear_bumper`
- **Predicted issue/part**: `dent` / `rear_bumper`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image clearly shows a dent on the rear bumper and the user history does not add risk.
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed car is not visible in any image. Car not visible in images. Claimed part 'rear bumper' not vi

### user_002 (car)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `scratch` / `front_bumper`
- **Predicted issue/part**: `scratch` / `front_bumper`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The close-up image shows a visible scratch on the claimed front bumper.
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed car is not visible in any image. Car not visible in images. Claimed part 'front bumper' not v

### user_007 (car)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `broken_part` / `side_mirror`
- **Predicted issue/part**: `unknown` / `side_mirror`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "issue_type": {"expected": "broken_part", "predicted": "unknown"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The submitted image directly shows damage to the claimed side mirror.
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed car is not visible in any image. Car not visible in images. Claimed part 'side mirror' not vi

### user_005 (car)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `scratch` / `rear_bumper`
- **Predicted issue/part**: `unknown` / `rear_bumper`
- **Risk flags**: `user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "not_enough_information"}, "issue_type": {"expected": "scratch", "predicted": "unknown"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The images show only minor rear bumper scratching, so the severe damage claim is contradicted. User history also shows several rejected claims.
- **Pred justification**: 1/5 evidence requirement(s) satisfied. Gaps: The claimed car is not visible in any image. For multi-part claims, at least one image must clearly show 

### user_009 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `crack` / `screen`
- **Predicted issue/part**: `crack` / `screen`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image directly shows a crack on the laptop screen.
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed laptop is not visible in any image. Laptop not visible in images. Claimed part 'screen' not v

### user_011 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `stain` / `keyboard`
- **Predicted issue/part**: `water_damage` / `keyboard`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "issue_type": {"expected": "stain", "predicted": "water_damage"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The submitted image shows visible staining on the keyboard area.
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed laptop is not visible in any image. Laptop not visible in images. Claimed part 'keyboard' not

### user_012 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `dent` / `corner`
- **Predicted issue/part**: `dent` / `corner`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image set supports the claim because the corner dent is visible in the close-up.
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed laptop is not visible in any image. Laptop not visible in images. Claimed part 'corner' not v

### user_020 (laptop)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `none` / `trackpad`
- **Predicted issue/part**: `unknown` / `trackpad`
- **Risk flags**: `user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "not_enough_information"}, "issue_type": {"expected": "none", "predicted": "unknown"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image shows the trackpad area but does not show clear physical damage, so it contradicts the user's physical damage claim. The user's prior claim 
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed laptop is not visible in any image. Laptop not visible in images. Claimed part 'trackpad' not

### user_015 (package)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `crushed_packaging` / `package_corner`
- **Predicted issue/part**: `crushed_packaging` / `package_corner`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image directly shows crushing on the claimed package corner.
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed package is not visible in any image. Package not visible in images. Claimed part 'package cor

### user_034 (package)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `none` / `seal`
- **Predicted issue/part**: `torn_packaging` / `seal`
- **Risk flags**: `user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "not_enough_information"}, "issue_type": {"expected": "none", "predicted": "torn_packaging"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The visible package seal does not show torn-open packaging. Any instruction-like text inside the image should be ignored, and user history requires re
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed package is not visible in any image. Package not visible in images. Claimed part 'seal' not v

## Object Part Failure (5 cases)

### user_008 (car)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `broken_part` / `front_bumper`
- **Predicted issue/part**: `scratch` / `hood`
- **Risk flags**: `user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "not_enough_information"}, "issue_type": {"expected": "broken_part", "predicted": "scratch"}, "object_part": {"expected": "front_bumper", "predicted": "hood"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image shows severe front-end damage rather than a scratch on the hood, so it does not support the user's hood-scratch claim.
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed car is not visible in any image. Car not visible in images. Claimed part 'hood' not visible (

### user_010 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `broken_part` / `hinge`
- **Predicted issue/part**: `broken_part` / `screen`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "object_part": {"expected": "hinge", "predicted": "screen"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The first image supports the claim because the hinge damage is visible.
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed laptop is not visible in any image. For multi-part claims, at least one image must clearly sh

### user_018 (laptop)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `crack` / `screen`
- **Predicted issue/part**: `glass_shatter` / `keyboard`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "issue_type": {"expected": "crack", "predicted": "glass_shatter"}, "object_part": {"expected": "screen", "predicted": "keyboard"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image supports the claim because the laptop screen has visible cracking consistent with the user's screen damage report.
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed laptop is not visible in any image. For multi-part claims, at least one image must clearly sh

### user_030 (package)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `torn_packaging` / `seal`
- **Predicted issue/part**: `missing_part` / `package_side`
- **Risk flags**: `none`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "issue_type": {"expected": "torn_packaging", "predicted": "missing_part"}, "object_part": {"expected": "seal", "predicted": "package_side"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The first image supports the claim by showing torn-open packaging.
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed package is not visible in any image. Package not visible in images. Claimed part 'package sid

### user_033 (package)
- **Expected claim_status**: `contradicted`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `unknown` / `unknown`
- **Predicted issue/part**: `crushed_packaging` / `box`
- **Risk flags**: `user_history_risk`
- **Field errors**: `{"claim_status": {"expected": "contradicted", "predicted": "not_enough_information"}, "issue_type": {"expected": "unknown", "predicted": "crushed_packaging"}, "object_part": {"expected": "unknown", "predicted": "box"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image does show a visible crease or dent, but the object shown is different from the claimed shipping box, so it does not support the user's crush
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed package is not visible in any image. Package not visible in images. Claimed part 'box' not vi

## Image Quality Failure (3 cases)

### user_004 (car)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `crack` / `windshield`
- **Predicted issue/part**: `crack` / `windshield`
- **Risk flags**: `blurry_image`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image set supports the claim because the windshield crack is visible in the close-up.
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed car is not visible in any image. Car not visible in images. Claimed part 'windshield' not vis

### user_003 (car)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `dent` / `door`
- **Predicted issue/part**: `dent` / `door`
- **Risk flags**: `blurry_image`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The clearer second image supports the claim by showing a dent on the door.
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed car is not visible in any image. Car not visible in images. Claimed part 'door' not visible (

### user_031 (package)
- **Expected claim_status**: `supported`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `water_damage` / `package_side`
- **Predicted issue/part**: `water_damage` / `unknown`
- **Risk flags**: `blurry_image;user_history_risk;manual_review_required`
- **Field errors**: `{"claim_status": {"expected": "supported", "predicted": "not_enough_information"}, "object_part": {"expected": "package_side", "predicted": "unknown"}, "evidence_standard_met": {"expected": "true", "predicted": "false"}}`
- **GT justification**: The image supports the water damage claim, but user history shows prior package claims often needed evidence review.
- **Pred justification**: No valid images were available for assessment. Missing: Readable image showing package unknown with visible water damage damage.

## Other Mismatch (2 cases)

### user_006 (car)
- **Expected claim_status**: `not_enough_information`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `unknown` / `headlight`
- **Predicted issue/part**: `crack` / `headlight`
- **Risk flags**: `none`
- **Field errors**: `{"issue_type": {"expected": "unknown", "predicted": "crack"}}`
- **GT justification**: The submitted image shows another part of the car and does not provide evidence for the headlight claim.
- **Pred justification**: 1/3 evidence requirement(s) satisfied. Gaps: The claimed car is not visible in any image. Car not visible in images. Claimed part 'headlight' not visi

### user_032 (package)
- **Expected claim_status**: `not_enough_information`
- **Predicted claim_status**: `not_enough_information`
- **Expected issue/part**: `unknown` / `contents`
- **Predicted issue/part**: `missing_part` / `contents`
- **Risk flags**: `manual_review_required`
- **Field errors**: `{"issue_type": {"expected": "unknown", "predicted": "missing_part"}}`
- **GT justification**: The package contents are unclear, so the missing-product claim cannot be verified from the submitted images.
- **Pred justification**: 1/4 evidence requirement(s) satisfied. Gaps: The claimed package is not visible in any image. For multi-part claims, at least one image must clearly s
