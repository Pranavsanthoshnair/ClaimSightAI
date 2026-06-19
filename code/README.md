# Evidence Review Solution

This directory contains the Python 3.11+ implementation for the HackerRank
Orchestrate Multi-Modal Evidence Review challenge.

The current state is an architecture scaffold only. It defines typed package
boundaries, Pydantic models, Pandas-based IO services, pipeline entry points,
prompt placeholders, runtime logging, and evaluation scaffolding. Business
logic for claim parsing, image analysis, decisioning, caching, and metrics will
be implemented in later passes.

## Entry Points

```bash
python code/main.py --input dataset/claims.csv --output output.csv
python code/evaluation/main.py
```

## Structure

- `models/`: Pydantic contracts and allowed-value enums.
- `agents/`: claim parsing and vision evidence extraction components.
- `services/`: IO, cache, model, logging, history, requirements, and decision services.
- `pipelines/`: orchestration layer.
- `evaluation/`: sample-set evaluation workflow.
- `prompts/`: versioned prompt templates.
- `utils/`: shared helpers.
- `outputs/`: generated intermediate outputs.
- `logs/`: runtime JSONL logs.
