# Drafting Module Scaffold

This directory contains the groundwork for Stage 4 (Single-Writer LLM drafting).

## Purpose

The drafting stage combines four structured inputs:

- `data/ClientProfile.json`
- `data/RetrievalBundle.json`
- `data/ModelOutputs.json`
- `data/Outline.json`

## Directory Layout

- `loaders/` - Input loading and schema validation helpers
- `context/` - Prompt context builders and normalization
- `prompts/` - System and user prompt templates
- `llm/` - LLM invocation wrappers for drafting
- `drafting/` - Section-by-section writer logic
- `postprocessing/` - Citation and numeric placeholder cleanup
- `output/` - Draft output writing utilities
- `pipeline/` - Stage orchestration entry points
- `utils/` - Shared utility functions
- `tests/` - Unit and integration tests
- `data/` - Local sample inputs for development

## Notes

- This scaffold is additive and does not modify prior pipeline stages.
- Data files are seeded from existing pipeline artifacts where available.

## Environment Setup

Use the lock file for reproducible dependency installation:

```bash
python -m pip install -r requirements.lock
```

Install drafting modules in editable mode to enable absolute imports from project root:

```bash
python -m pip install -e .
```

After editable install, imports work as:

```python
from loaders.client_profile import load_client_profile
from loaders.retrieval_bundle import load_retrieval_bundle
from loaders.model_outputs import load_model_outputs
from loaders.outline import load_outline
```
