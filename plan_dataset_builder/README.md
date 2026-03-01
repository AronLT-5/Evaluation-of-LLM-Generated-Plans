# plan_dataset_builder

Plan dataset production system (plan generator only) for:
- HumanEval (`humaneval`)
- SWE-bench Verified (`swebench_verified`)
- RefactorBench Python (`refactorbench_py`)

The system builds reproducible JSONL datasets of LLM-generated plans with retry logic, schema validation, diversity constraints, resume support, and budget monitoring.

## Install

```bash
cd plan_dataset_builder
python -m venv .venv
. .venv/Scripts/activate  # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Quick Start

1. Create sample config:

```bash
plan-dataset-builder init-config example_config.yaml
```

2. Set API key:

```bash
set OPENAI_API_KEY=YOUR_KEY   # Windows cmd
# or in PowerShell:
$env:OPENAI_API_KEY="YOUR_KEY"
```

3. Dry run (task loading + manifests/tasks JSONL only):

```bash
plan-dataset-builder dry-run --config example_config.yaml
```

4. Full run:

```bash
plan-dataset-builder run --config example_config.yaml
```

`run` now auto-renders human-readable outputs after generation:
- `runs/<run_id>/readable/...` for successful plans
- `runs/<run_id>/failed_plans/readable/...` for local validation failures (if present)

Readable export errors are non-blocking warnings and do not fail the run.

5. Resume:

```bash
plan-dataset-builder run --config example_config.yaml --run-id <run_id> --resume
```

6. Validate run artifacts:

```bash
plan-dataset-builder validate-run runs/<run_id>
```

7. Export plans into human-readable Markdown:

```bash
plan-dataset-builder render-readable --run-dir runs/<run_id>
```

When failed-plan artifacts exist, `render-readable` also exports:
- `runs/<run_id>/failed_plans/readable/...`

Optional:

```bash
plan-dataset-builder render-readable --run-dir runs/<run_id> --output-dir runs/<run_id>/readable_custom --no-task-text
```

## RefactorBench Conversion

If you cloned the `RefactorBench` repo, convert it into the local JSONL expected by `refactorbench_py`:

```bash
python scripts/convert_refactorbench_to_jsonl.py \
  --refactorbench-root ../RefactorBench \
  --variant descriptive \
  --output data/refactorbench_py.jsonl
```

Options:
- `--variant`: `base`, `descriptive`, or `lazy` (default `descriptive`)
- `--limit`: cap rows after deterministic `task_id` sorting
- `--include-test-source`: embeds full test file text in each row (larger prompts/cost)

## Sectioned Production Workflow (4 x 25/25)

To run 100-task SWE-bench + 100-task RefactorBench in manual-gated sections:

1. Prepare section configs and allowlists:

```bash
plan-dataset-builder prepare-sections \
  --config main_config.yaml \
  --section-size 25 \
  --sections 4 \
  --output-dir section_runs \
  --run-prefix full_system
```

2. Run section 1:

```bash
plan-dataset-builder run --config section_runs/section_01/section_config.yaml --run-id full_s01_v1
```

3. Validate and inspect cost:

```bash
plan-dataset-builder validate-run runs/full_s01_v1
```

4. Decide manually:
- rerun same section with new run id, or
- proceed to `section_02`, `section_03`, `section_04`.

5. Merge approved section runs into one consolidated artifact:

```bash
plan-dataset-builder merge-sections \
  --section-run s1=runs/full_s01_v2 \
  --section-run s2=runs/full_s02_v1 \
  --section-run s3=runs/full_s03_v1 \
  --section-run s4=runs/full_s04_v1 \
  --output-run-id full_system_merged_001
```

Section preparation writes:
- `section_runs/sections_manifest.json`
- `section_runs/section_XX/swebench_verified_task_ids.json`
- `section_runs/section_XX/refactorbench_py_task_ids.json`
- `section_runs/section_XX/section_config.yaml`

## Output Structure

Per run:

```text
runs/<run_id>/
  runs.jsonl
  logs/batch_calls.jsonl
  prompts/plan_prompt_template.txt
  config/run_config.json
  manifests/
    <dataset>_task_ids.json
    <dataset>_complete_task_ids.json
    <dataset>_incomplete_task_ids.json
    swebench_verified_first100_instance_ids.json
  datasets/<dataset>/
    tasks.jsonl
    plans.jsonl
  failed_plans/
    datasets/<dataset>/
      tasks.jsonl
      plans.jsonl
    readable/
      index.md
      <dataset>/<task>_b<batch>_a<attempt>_<hash>.md
```

## Notes

- The primary task field is shown under `[PRIMARY_TASK]` and is omitted from `[CONTEXT_FIELDS]` by default to avoid duplication.
- Gold/answer fields are excluded from `task_text` but preserved in `extras`.
- Exactly 12 plans per task are targeted: 3 calls x 4 plans per call.
- `openai.multi_model: true` (or `openai.multi-model: true`) lets you set `model1`/`model2`/`model3` for batch 1/2/3 respectively.
- Prompt caching controls:
  - `openai.prompt_cache_enabled` enables explicit cache fields in requests.
  - `openai.prompt_cache_key_prefix` controls the stable cache key prefix.
  - `openai.prompt_cache_retention` supports `24h` or `in_memory`.
- `openai.temperature`, `openai.top_p`, and `openai.seed` are deprecated and ignored for request compatibility.
- Plan generation always uses strict structured outputs (`json_schema`, `strict=true`) even if `openai.structured_outputs` is set to false.
- `failed_plans` captures local validation failures only (`validation_error`) and stores every failed attempt with associated task rows.
- Batch API mode creates `/v1/responses` JSONL requests with `custom_id` mapping.
- In Batch API mode with multi-model enabled, the runner automatically creates separate batch jobs per model.
- Budget preflight and chunking use an upper-bound estimate; actual token usage is used when available.
- `datasets.refactorbench_py.max_tasks` can cap RefactorBench task count deterministically after task-id sorting.
- Check cache effectiveness in `runs/<run_id>/logs/batch_calls.jsonl` via `cached_input_tokens`.

## Batch API Usage

When `openai.use_batch_api: true`:
- Input JSONL requests are uploaded with `purpose="batch"`.
- A batch is created with `completion_window="24h"`.
- Outputs are matched by `custom_id`.
- Failed/invalid requests are retried up to configured limits via subsequent chunks.

Multi-model example:

```yaml
openai:
  use_batch_api: true
  multi_model: true
  model1: gpt-4.1-mini
  model2: gpt-4.1
  model3: gpt-4o-mini
```
