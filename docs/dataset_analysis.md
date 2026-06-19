# Dataset Analysis: Multi-Modal Evidence Review

This document summarizes dataset characteristics for system design and evaluation.
It is for understanding the data distribution only. It should not be used to
hardcode sample answers, row-specific behavior, filenames, or dataset-specific
shortcuts.

## Scope

Analyzed files:

| File | Rows | Columns | Purpose |
|---|---:|---:|---|
| `dataset/sample_claims.csv` | 20 | 14 | Labeled development/evaluation examples |
| `dataset/claims.csv` | 44 | 4 | Unlabeled test inputs for final `output.csv` |
| `dataset/user_history.csv` | 47 | 8 | User risk context |
| `dataset/evidence_requirements.csv` | 11 | 4 | Minimum evidence requirements |

Image inventory:

| Split | Referenced JPGs | Local JPGs | Missing references |
|---|---:|---:|---:|
| Sample | 29 | 29 | 0 |
| Test | 82 | 82 | 0 |
| Total | 111 | 111 | 0 |

Note: CSV `image_paths` values are written as `images/...` and resolve relative
to `dataset/`, for example `dataset/images/test/case_001/img_1.jpg`.

## Input Distribution

### Object Distribution

`sample_claims.csv`:

| claim_object | Count | Share |
|---|---:|---:|
| car | 8 | 40% |
| laptop | 6 | 30% |
| package | 6 | 30% |

`claims.csv`:

| claim_object | Count | Share |
|---|---:|---:|
| car | 18 | 41% |
| laptop | 13 | 30% |
| package | 13 | 30% |

The sample set is small but roughly aligned with the test input distribution.
Cars are slightly overrepresented; laptops and packages are balanced.

### Images Per Claim

`sample_claims.csv`:

| Image count | Rows |
|---:|---:|
| 1 | 11 |
| 2 | 9 |

`claims.csv`:

| Image count | Rows |
|---:|---:|
| 1 | 13 |
| 2 | 24 |
| 3 | 7 |

The test set has more multi-image cases than the sample set. The pipeline should
aggregate image-level evidence and not assume the first image is always the best
supporting image.

## Label Distributions in `sample_claims.csv`

### Evidence Standard Met

| evidence_standard_met | Count | Share |
|---|---:|---:|
| true | 18 | 90% |
| false | 2 | 10% |

Most labeled examples are reviewable, but the negative evidence-standard cases
are important because they represent wrong angle, cropped, obstructed, or
insufficient evidence.

### Valid Image

| valid_image | Count | Share |
|---|---:|---:|
| true | 18 | 90% |
| false | 2 | 10% |

`valid_image=false` does not always mean an unreadable file. It can also reflect
non-original, unusable, cropped, obstructed, or otherwise unsuitable evidence.

### Claim Status

| claim_status | Count | Share |
|---|---:|---:|
| supported | 13 | 65% |
| contradicted | 5 | 25% |
| not_enough_information | 2 | 10% |

The sample set is support-heavy. A robust system should avoid overpredicting
`supported` by checking whether the claimed part and claimed issue are both
visible.

### Issue Type Frequencies

| issue_type | Count |
|---|---:|
| dent | 3 |
| crack | 3 |
| broken_part | 3 |
| unknown | 3 |
| scratch | 2 |
| none | 2 |
| stain | 1 |
| crushed_packaging | 1 |
| torn_packaging | 1 |
| water_damage | 1 |

Observations:

- Damage taxonomy is broad relative to the small sample size.
- `unknown` appears in insufficient, wrong-object, and wrong-angle contexts.
- `none` is used when the relevant part is visible and no claimed physical
  damage is present.

### Object Part Frequencies

| object_part | Count |
|---|---:|
| rear_bumper | 2 |
| front_bumper | 2 |
| screen | 2 |
| seal | 2 |
| windshield | 1 |
| side_mirror | 1 |
| headlight | 1 |
| door | 1 |
| hinge | 1 |
| keyboard | 1 |
| corner | 1 |
| trackpad | 1 |
| package_corner | 1 |
| package_side | 1 |
| contents | 1 |
| unknown | 1 |

The part taxonomy is sparse. The model should generalize by object family and
part visibility, not memorize part-to-case patterns.

### Severity Frequencies

| severity | Count |
|---|---:|
| medium | 11 |
| low | 4 |
| unknown | 2 |
| none | 2 |
| high | 1 |

Severity is dominated by medium examples. `none` appears in contradicted cases
where the claimed damage is not visible despite a reviewable image.

### Risk Flag Frequencies

Risk flags are semicolon-delimited; rows can contain multiple flags.

| risk_flag | Count |
|---|---:|
| none | 11 |
| manual_review_required | 7 |
| user_history_risk | 6 |
| damage_not_visible | 4 |
| claim_mismatch | 3 |
| wrong_angle | 1 |
| blurry_image | 1 |
| non_original_image | 1 |
| cropped_or_obstructed | 1 |
| wrong_object | 1 |
| text_instruction_present | 1 |

Risk flags are not mutually exclusive. The common pattern is a visual problem
combined with `manual_review_required`, sometimes with `user_history_risk`.

### Supporting Image IDs

| supporting_image_ids token | Count |
|---|---:|
| img_1 | 16 |
| img_2 | 3 |
| none | 2 |

`img_1` is most common, but several supported rows use `img_2`, and one
contradicted package row uses both `img_1;img_2`. The implementation should
evaluate every image independently.

## User History Characteristics

`user_history.csv` risk tokens:

| history flag token | Count |
|---|---:|
| none | 22 |
| user_history_risk | 22 |
| manual_review_required | 11 |

User history is intentionally mixed: about half the users have a history risk.
Per the problem statement, this should only affect risk context and manual
review flags. It must not override clear image evidence.

## Evidence Requirement Coverage

| claim_object in requirements | Count |
|---|---:|
| all | 3 |
| car | 3 |
| package | 3 |
| laptop | 2 |

The requirements table is compact and qualitative. It is best used to decide
whether an image set is sufficient for evaluation, not as a label lookup.

## Edge Cases in Labeled Samples

The following sample cases exercise behavior that the final system must handle
without relying on filenames or sample labels.

| Case | Object | Why it is an edge case | Expected behavior pattern |
|---|---|---|---|
| case_002 | car | Hindi/English conversation and two images | Parse multilingual claim; use image evidence for front bumper scratch |
| case_005 | car | Claimed severe damage, visible minor scratch, risky user history | Contradict severity/claim mismatch; add history risk |
| case_006 | car | Claimed headlight crack, image does not show headlight | Evidence not met; not enough information |
| case_007 | car | One blurry image, second clearer image | Do not reject full set if another image is sufficient |
| case_008 | car | Image shows severe front-end damage but claim is hood scratch; non-original risk | Contradict claimed issue/part; mark manual review |
| case_014 | laptop | Trackpad visible but claimed physical damage absent | Contradict; issue_type `none`, severity `none` |
| case_017 | package | Claim visually supported but user history risky | Support image evidence while adding history/manual-review context |
| case_018 | package | Contents/missing item unclear from cropped/obstructed images | Evidence not met; not enough information |
| case_019 | package | Visible damage-like object, but wrong object for shipping box claim | Contradict with wrong-object and claim-mismatch risk |
| case_020 | package | Image contains instruction-like text and no torn seal | Ignore text instruction; contradict visual claim |

## Ambiguous Samples

Ambiguity in this dataset usually comes from one of five sources:

1. The claimed part is not visible.
2. The visible damage does not match the claimed damage.
3. The image is readable but not valid for automated review.
4. Multiple images differ in quality or relevance.
5. User history adds risk context but visual evidence remains primary.

Most ambiguous labeled rows:

| Case | Ambiguity source | Label pattern |
|---|---|---|
| case_005 | Minor visible scratch vs stronger user claim | `contradicted`, `claim_mismatch` |
| case_006 | Wrong angle; headlight not visible | `not_enough_information`, `wrong_angle`, `damage_not_visible` |
| case_007 | One blurry image but another useful image | `supported`, `blurry_image` |
| case_008 | Claim part/issue mismatch and non-original image concern | `contradicted`, `valid_image=false` |
| case_014 | Claimed trackpad damage not visible | `contradicted`, `issue_type=none` |
| case_018 | Missing contents cannot be verified | `not_enough_information`, `valid_image=false` |
| case_019 | Wrong object for package claim | `contradicted`, `wrong_object` |
| case_020 | Text instruction present; damage absent | `contradicted`, `text_instruction_present` |

These rows should guide evaluation slices, not hardcoded responses.

## Unlabeled Test-Input Edge Hints

The test input contains many multi-image rows and several claim conversations
with wording that signals ambiguity:

| Case | Object | Images | Conversation hint |
|---|---|---:|---|
| case_001 | car | 3 | Multiple claimed parts: front bumper and headlight |
| case_004 | car | 2 | Windshield claim described from one side |
| case_005 | car | 2 | User says one photo may be clearer and asks to ignore unrelated photos |
| case_006 | car | 1 | User is unsure about the issue |
| case_010 | car | 3 | Same area shown across several photos |
| case_019 | laptop | 3 | Multi-image laptop claim |
| case_031 | package | 3 | Multi-image package claim |
| case_040 | package | 3 | Multi-image package claim |
| case_041 | car | 3 | Multi-image car claim |
| case_051 | package | 3 | Multi-image package claim |

These are not labels. They indicate where the pipeline should pay attention to
image aggregation, part matching, and relevance filtering.

## Image Quality Analysis

A simple local image pass found:

| Metric | Value |
|---|---:|
| JPEG images | 111 |
| Unreadable JPEGs | 0 |
| Brightness min | 38.03 |
| Brightness median | 120.80 |
| Brightness max | 243.79 |
| Contrast min | 28.04 |
| Contrast median | 58.41 |
| Contrast max | 98.50 |

Heuristic quality flags:

| Heuristic | Count |
|---|---:|
| Low light (`brightness < 55`) | 4 |
| Glare or washout (`brightness > 220`) | 1 |
| Small image dimension (`width < 400` or `height < 400`) | 39 |
| Low contrast (`contrast < 25`) | 0 |
| Low edge detail | 0 |

Important caveat: these are lightweight image heuristics, not ground-truth
quality labels. A small image can still be reviewable if it clearly shows the
claimed part. A bright or dark image can still contain enough visual evidence.

Common quality and usability issues visible from labels and heuristics:

- Small images are common, especially web-sized car and laptop photos.
- Low-light cases exist and can overlap with authenticity or mismatch concerns.
- The labeled set includes one explicit `blurry_image` risk.
- The labeled set includes cropped/obstructed evidence for a missing-contents
  package claim.
- The labeled set includes wrong-angle evidence for a headlight claim.
- The labeled set includes `text_instruction_present`, which the model must
  ignore as an instruction and treat only as image content risk.
- Wrong-object and wrong-part mismatches are as important as raw image quality.

## Design Implications

1. Use image evidence as the final authority for visual facts.
2. Parse the conversation only to identify the target issue and part.
3. Inspect every submitted image independently before aggregating.
4. Separate evidence sufficiency from claim status.
5. Allow `supported` with risk flags when the image supports the claim but user
   history or image quality requires review.
6. Use `issue_type=none` only when the relevant part is visible and no damage is
   present.
7. Use `unknown` when the issue or part cannot be determined from the images.
8. Treat user history as risk context only.
9. Track image IDs carefully; supporting evidence is not always `img_1`.
10. Resolve CSV image paths relative to `dataset/`.

## Recommended Evaluation Slices

Beyond exact-match metrics, evaluate performance by:

- Object family: car, laptop, package.
- Status: supported, contradicted, not_enough_information.
- Image count: single image vs multi-image.
- Risk flags: no-risk vs manual-review/user-history/image-quality risk.
- Evidence sufficiency: standard met vs not met.
- Part visibility: known object part vs unknown.
- Damage visibility: visible damage vs no visible damage vs unknown.
- Supporting-image selection: `img_1`, `img_2`, multiple IDs, or `none`.

These slices reflect the dataset structure and should help avoid a system that
looks good only on the dominant supported, reviewable examples.
