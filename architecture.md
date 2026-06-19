# Production Architecture: Multi-Modal Evidence Review

## 1. System Architecture

The solution is a deterministic, file-driven batch pipeline that reads claim rows, enriches each row with user history and evidence requirements, inspects local images with a vision-language model, applies a constrained decision layer, and writes `output.csv` with the exact required schema.

Core principles:

- Images are the primary source of truth.
- The conversation defines the claim target: object, issue, and part.
- User history contributes only contextual risk flags and never overrides clear image evidence.
- Evidence requirements decide whether the submitted image set is sufficient for review.
- Output values are constrained to the allowed taxonomy from `problem_statement.md`.
- The pipeline must not use filenames, sample labels, row IDs, or dataset-specific lookup hacks to decide claims.

High-level components:

```text
CSV inputs + images
        |
        v
Input loader and schema validator
        |
        v
Claim parser + requirement matcher + history enricher
        |
        v
Image preflight + cache lookup
        |
        v
Vision evidence extractor
        |
        v
Decision normalizer and risk layer
        |
        v
Output writer + evaluation reporter
```

## 2. Folder Structure

```text
.
├── architecture.md
├── output.csv
├── code/
│   ├── README.md
│   ├── main.py
│   ├── requirements.txt
│   ├── config/
│   │   ├── prompts.py
│   │   └── schema.py
│   ├── pipeline/
│   │   ├── io.py
│   │   ├── claim_parser.py
│   │   ├── image_preflight.py
│   │   ├── evidence_requirements.py
│   │   ├── model_client.py
│   │   ├── decision.py
│   │   ├── cache.py
│   │   └── logging_utils.py
│   ├── evaluation/
│   │   ├── main.py
│   │   ├── metrics.py
│   │   └── evaluation_report.md
│   └── tests/
│       └── test_schema_contract.py
└── dataset/
    ├── claims.csv
    ├── sample_claims.csv
    ├── user_history.csv
    ├── evidence_requirements.csv
    └── images/
```

Runtime artifacts should stay reproducible and easy to exclude from submission:

```text
code/.cache/
├── image_fingerprints.jsonl
├── model_responses.jsonl
└── parsed_claims.jsonl

code/logs/
├── run.jsonl
└── evaluation.jsonl
```

## 3. Data Flow

1. Load `claims.csv` or `sample_claims.csv`.
2. Validate required input columns: `user_id`, `image_paths`, `user_claim`, `claim_object`.
3. Split `image_paths` on semicolons and resolve them relative to repo root.
4. Load `user_history.csv` into a `user_id` lookup.
5. Load `evidence_requirements.csv` into object-aware requirement records.
6. Parse the user conversation into a claim target:
   - object family
   - claimed issue family
   - claimed object part
   - whether the user mentions multiple parts
7. Run image preflight:
   - file exists
   - readable image
   - dimensions
   - format
   - blur/low-light heuristics when cheap to compute
8. Inspect each image with the VLM or return cached inspection.
9. Aggregate image-level findings into claim-level evidence.
10. Apply the decision layer:
    - evidence sufficiency
    - visible issue type
    - object part
    - claim status
    - severity
    - risk flags
    - supporting image IDs
11. Validate output enums and required column order.
12. Write `output.csv`.
13. For sample runs, compare predictions to expected sample labels and produce `code/evaluation/evaluation_report.md`.

## 4. Agent Pipeline

The runtime agent is a structured pipeline, not an open-ended chat agent.

### Stage A: Claim Understanding

Input: `user_claim`, `claim_object`

Output:

- normalized claimed object
- claimed issue family
- claimed issue type candidate
- claimed object part candidate
- relevant evidence requirement IDs

Implementation strategy:

- Use deterministic text extraction first for object and part hints.
- Use an LLM only if the claim text is ambiguous or multilingual.
- Never infer visual truth from the conversation alone.

### Stage B: Image Evidence Extraction

Input: local image bytes, image ID, claim target, allowed values

Output per image:

- whether the claimed object is present
- visible parts
- visible damage types
- quality concerns
- possible mismatch or manipulation signals
- concise image-grounded description
- confidence per finding

The VLM prompt asks for structured JSON only and explicitly separates:

- what is visible
- what is not visible
- what cannot be determined
- whether the image supports the claimed issue

### Stage C: Evidence Standard Review

Input: claim target, evidence requirements, image findings

Output:

- `evidence_standard_met`
- `evidence_standard_met_reason`
- image IDs that are sufficient for review

This stage asks: "Can the image set evaluate the claim?" not "Should the claim be accepted?"

### Stage D: Decision and Normalization

Input: parsed claim, image findings, evidence review, user history

Output: full row for `output.csv`

Decision rules:

- If no valid image can evaluate the claimed object or part, return `not_enough_information`.
- If the claimed part is visible and the claimed damage is visible, return `supported`.
- If the claimed part is visible and the claimed damage is absent or a different object/part is shown, return `contradicted`.
- If the part or issue cannot be determined, return `not_enough_information`.
- Add user history risk only as `risk_flags` and supporting justification context.

## 5. Model Strategy

The default architecture uses one configurable multimodal model for evidence extraction and an optional lightweight text model for claim parsing. Model names are environment-configured so the implementation can switch providers without changing decision logic.

Recommended strategy:

- Primary VLM: high-accuracy multimodal model for all images that pass preflight.
- Cheap text parser: deterministic parser first, small LLM fallback only for ambiguous conversations.
- Strict JSON schema output from model calls.
- Temperature `0` or the provider's most deterministic setting.
- Retry with a stricter repair prompt only when JSON parsing fails.
- Use local validation to map model outputs to allowed enums.

Prompt contract:

- The model may describe visual evidence but must not invent unseen details.
- The model must choose from allowed issue and object-part values.
- The model must return `unknown` when uncertain.
- The model must identify all image IDs that support the final decision.
- The model must ignore user history when judging visual evidence.

Fallback strategy:

- If no API key is configured, run a deterministic baseline that validates schema and uses conservative outputs.
- If a model call fails for a claim, mark `valid_image=false` only when image processing itself fails; otherwise use `not_enough_information`, `unknown`, and `manual_review_required`.

## 6. Cost Optimization Strategy

Cost control is built around avoiding repeated or unnecessary model calls.

- Hash image bytes and cache image-level VLM responses.
- Cache parsed claim targets by normalized conversation text and object.
- Process multiple images for the same claim in one VLM request when provider limits allow.
- Resize images to a bounded maximum dimension before sending to a VLM while preserving enough detail for damage inspection.
- Skip model calls for unreadable or missing images and record deterministic risk flags.
- Use cheap local image quality checks before VLM inspection.
- Use the sample set to compare at least two strategies:
  - single-pass VLM claim decision
  - two-stage image evidence extraction plus deterministic decision layer
- Prefer the two-stage strategy if it reduces retries and improves schema consistency.

Operational estimates in the evaluation report should include:

- number of claims
- number of images
- model calls per claim
- approximate text tokens
- approximate image tokens or provider image units
- estimated cost for sample and test
- expected runtime and rate-limit constraints

## 7. Evaluation Methodology

Evaluation runs against `dataset/sample_claims.csv`, which includes expected outputs.

Metrics:

- Exact match by required output field.
- Macro accuracy for `claim_status`.
- Macro accuracy for `issue_type`.
- Macro accuracy for `object_part`.
- Accuracy for `evidence_standard_met`.
- Accuracy for `valid_image`.
- Accuracy for `severity`.
- Partial credit style analysis for `risk_flags` using set precision/recall.
- Supporting image ID match rate.

Diagnostic slices:

- object type: car, laptop, package
- issue family
- single-image vs multi-image rows
- supported vs contradicted vs not enough information
- history-risk users vs normal users
- image-quality-risk rows

The evaluation report should include:

- sample metrics
- confusion tables for key labels
- examples of false support and false contradiction
- prompt/model strategies compared
- final strategy selected for `output.csv`
- operational analysis required by `problem_statement.md`

## 8. Error Handling

Errors should be explicit, recoverable, and visible in logs without breaking the entire batch.

Input errors:

- Missing required CSV columns: fail fast with a clear message.
- Unknown `claim_object`: emit a validation error and stop, because output taxonomy depends on it.
- Missing user history: continue with neutral history context.
- Missing evidence requirements: continue with general requirements and log a warning.

Image errors:

- Missing file: `valid_image=false`, `risk_flags=manual_review_required`, status `not_enough_information`.
- Unreadable file: same as missing file.
- Low-quality image: keep `valid_image=true` if still reviewable; add quality risk flag.
- Wrong object or wrong part: keep image valid if readable, but set mismatch risk flags and usually return `contradicted` or `not_enough_information`.

Model errors:

- JSON parse failure: one repair retry.
- Rate limit: exponential backoff with bounded retries.
- Timeout: retry once, then conservative fallback.
- Provider outage: continue remaining rows if possible and flag failed rows for manual review.

Output errors:

- Enum mismatch: normalize to closest allowed value or `unknown`.
- Empty required field: fill with conservative default.
- Column order mismatch: fail before writing final output.

## 9. Caching Strategy

The cache is content-addressed and safe to reuse across runs.

Cache keys:

- Image evidence key: model name, prompt version, image byte hash, image resize policy, claim object, claimed part, claimed issue family.
- Claim parser key: prompt version, normalized `user_claim`, `claim_object`.
- Decision key: decision version, parsed claim hash, image evidence hashes, history hash, requirements hash.

Cache files:

- JSONL for append-friendly writes.
- One record per cache result.
- Include prompt version and schema version.
- Never cache secrets or raw API credentials.

Invalidation:

- Bump prompt version when prompts change.
- Bump decision version when rule logic changes.
- Bump schema version when output fields change.
- Recompute if image bytes change even when paths stay the same.

Cache policy:

- Enabled by default for evaluation and final output generation.
- Optional `--no-cache` flag for clean benchmark runs.
- Optional `--refresh-cache` flag for prompt/model comparisons.

## 10. Logging Strategy

There are two separate logging systems.

### Development Transcript Log

The shared hackathon conversation log is controlled by `AGENTS.md` and lives outside the repo:

```text
%USERPROFILE%\hackerrank_orchestrate\log.txt
```

This log is append-only and used for the submitted chat transcript. It must not contain secrets.

### Runtime Pipeline Logs

The claim review system writes machine-readable logs under `code/logs/`.

Runtime log fields:

- timestamp
- run ID
- input file
- row index
- user ID
- image IDs
- cache hit/miss
- model provider alias
- prompt version
- retry count
- parse/validation status
- final claim status
- risk flags
- elapsed milliseconds
- error code if any

Logging requirements:

- Use JSONL for easy inspection and aggregation.
- Redact environment variables and credentials.
- Do not log raw image bytes.
- Do not log full model prompts unless an explicit debug flag is enabled.
- Store concise model response summaries and validation errors.
- Include enough metadata for the evaluation report to estimate cost, latency, retries, and cache effectiveness.

## Final Implementation Gate

Implementation should begin only after this architecture is accepted. The first implementation pass should build the deterministic scaffolding:

1. CSV IO and schema validation.
2. Output schema writer.
3. Evidence requirement and user history lookup.
4. Cache abstraction.
5. Model client interface with a conservative fallback.
6. Evaluation runner and report generation.

Only after that should model prompts and final decision calibration be tuned against `sample_claims.csv`.
