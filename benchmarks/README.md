# Model Benchmarking Suite

This directory contains benchmarking scripts to compare different LLM providers and models for the ranker task.

## Setup

### 1. Install Dependencies

Make sure you have the required packages:

```bash
pip install anthropic openai python-dotenv
```

### 2. Configure API Keys

Add your API keys to `.env` file in the project root:

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
OPENAI_API_KEY=sk-...

# Cerebras
CEREBRAS_API_KEY=csk-...
```

You can test with any combination of providers - the script will skip providers where API keys are missing.

## Usage

### Run All Benchmarks

To test all models from all providers and generate a comparison report:

```bash
python benchmarks/run_all_benchmarks.py
```

### Phase-1 Task Microbenchmarks (recommended next)

This runs the repo’s **real call-site tasks** (ranker themes, teaching candidates, controller, etc.)
across a list of models and writes results to `benchmarks/results/task_benchmarks.json`.

```bash
python benchmarks/task_benchmarks.py
```

Optionally specify models/scenarios:

```bash
python benchmarks/task_benchmarks.py \
  --models cerebras:llama-3.3-70b cerebras:llama3.1-8b openai:gpt-4o openai:gpt-4o-mini anthropic:claude-sonnet-4-20250514 \
  --scenarios backprop_gap preference_heavy
```

### End-to-End Persona Simulation (judge-ready artifacts)

This simulates multiple user personas using a **fixed user model** (for consistency),
and runs the system under multiple routing configs. It outputs one JSON artifact per run
containing transcript + timings + final schema.

```bash
python benchmarks/persona_simulation.py --user-model openai:gpt-4o
```

Artifacts are written to:
- `benchmarks/results/persona_runs/`

This will:
1. Run Anthropic benchmarks (Claude models)
2. Run OpenAI benchmarks (GPT models)
3. Run Cerebras benchmarks (Llama models)
4. Generate a comprehensive comparison report

### Run Individual Provider Benchmarks

You can also run benchmarks for a single provider:

```bash
# Anthropic only
python benchmarks/anthropic/bench_anthropic.py

# OpenAI only
python benchmarks/openai/bench_openai.py

# Cerebras only
python benchmarks/cerebras/bench_cerebras.py
```

## Results

Results are saved to `benchmarks/results/`:
- `anthropic_results.json` - Anthropic model results
- `openai_results.json` - OpenAI model results
- `cerebras_results.json` - Cerebras model results

Each result includes:
- Model name
- Duration (seconds)
- Success/failure status
- Number of themes extracted
- Input/output token counts
- Raw JSON output

## Models Tested

### Anthropic
- Claude 3.5 Sonnet (20241022)
- Claude Sonnet 4 (20250514)
- Claude 3.5 Haiku (20241022)
- Claude Opus 4.5 (20251101)

### OpenAI
- GPT-4 Turbo
- GPT-4o
- GPT-4o-mini
- GPT-3.5 Turbo

### Cerebras
- Llama 3.1 8B
- Llama 3.1 70B
- Llama 3.3 70B

## Comparison Report

The final report includes:

1. **Fastest Model** - Lowest latency
2. **Best Value** - Best speed/cost ratio
3. **Quality Check** - Which models correctly extracted expected themes
4. **Speed Rankings** - All models sorted by speed
5. **Cost Estimates** - Approximate cost per API call
6. **Recommendations** - Which model to use based on your priorities

## Test Task

All models are tested on the same theme extraction task:

**Input**: A conversation where a user mentions:
- Concrete topics: "neural networks", "backpropagation"
- Abstract pattern: "wants to understand deeply"

**Expected Output**: JSON array with at least 2-3 themes correctly extracted

**Evaluation Criteria**:
- Speed (duration in seconds)
- Correctness (extracted expected themes)
- Cost (estimated $ per call)
- Token efficiency (input/output tokens used)

## Troubleshooting

### Missing API Key

If you see:
```
Error: ANTHROPIC_API_KEY not found in environment variables
```

Make sure you've added the key to your `.env` file.

### Model Not Available

Some models may not be available to all accounts (e.g., Claude Opus 4.5 is limited access). The benchmark will mark these as failed and continue with other models.

### Slow Performance

Initial runs may be slower due to:
- Cold start delays
- API rate limiting
- Network latency

Run the benchmark multiple times to get more consistent results.

## Interpreting Results

### Speed
- **< 5s**: Excellent for real-time conversation
- **5-15s**: Acceptable for ranker tasks
- **> 15s**: May need optimization or different model

### Cost
- **< $0.01 per call**: Very economical
- **$0.01-0.05**: Reasonable for production
- **> $0.05**: May be expensive at scale

### Quality
Look for models that extract both:
- Concrete topics ("neural networks", "backpropagation")
- Abstract patterns ("wants to understand deeply")

Models that only extract one type may not be suitable for the ranker task.

## Next Steps

After reviewing the benchmark results:

1. **Choose a model** based on your priorities (speed, cost, or quality)
2. **Update your config** to use the selected model in `src/llm_client.py`
3. **Test in production** with real conversations to validate performance
4. **Monitor costs** as you scale up usage
