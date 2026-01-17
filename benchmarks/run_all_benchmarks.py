#!/usr/bin/env python3
"""
Run all model benchmarks and generate comparison report.

This script:
1. Runs benchmarks for Anthropic, OpenAI, and Cerebras
2. Aggregates results from all providers
3. Generates a comprehensive comparison report
"""

import subprocess
import json
from pathlib import Path
import sys

BENCHMARKS_DIR = Path(__file__).parent
RESULTS_DIR = BENCHMARKS_DIR / "results"


def run_benchmark(provider: str) -> bool:
    """Run a single provider's benchmark."""
    script_path = BENCHMARKS_DIR / provider / f"bench_{provider}.py"

    if not script_path.exists():
        print(f"⚠️  Benchmark script not found: {script_path}")
        return False

    print(f"\n{'='*60}")
    print(f"Running {provider.upper()} benchmarks...")
    print(f"{'='*60}\n")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=False,
            text=True
        )

        if result.returncode == 0:
            print(f"✓ {provider.upper()} benchmarks completed")
            return True
        else:
            print(f"✗ {provider.upper()} benchmarks failed with return code {result.returncode}")
            return False

    except Exception as e:
        print(f"✗ Error running {provider} benchmarks: {e}")
        return False


def load_results(provider: str) -> list:
    """Load results from a provider's JSON file."""
    results_file = RESULTS_DIR / f"{provider}_results.json"

    if not results_file.exists():
        print(f"⚠️  Results file not found: {results_file}")
        return []

    try:
        with open(results_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Error loading {provider} results: {e}")
        return []


def generate_comparison_report():
    """Generate comprehensive comparison report."""
    print("\n" + "="*80)
    print(" "*25 + "FINAL COMPARISON REPORT")
    print("="*80)

    # Load all results
    all_results = []
    for provider in ["anthropic", "openai", "cerebras"]:
        results = load_results(provider)
        for r in results:
            r['provider'] = provider.upper()
            all_results.append(r)

    if not all_results:
        print("\n⚠️  No results found. Make sure benchmarks completed successfully.")
        return

    # Filter successful results
    successful = [r for r in all_results if r.get("success", False)]
    failed = [r for r in all_results if not r.get("success", False)]

    print(f"\n📊 Total models tested: {len(all_results)}")
    print(f"   ✓ Successful: {len(successful)}")
    print(f"   ✗ Failed: {len(failed)}")

    if not successful:
        print("\n⚠️  No successful results to compare.")
        return

    # Sort by duration
    by_speed = sorted(successful, key=lambda x: x["duration"])

    # Find fastest
    fastest = by_speed[0]

    print("\n" + "="*80)
    print("🏆 FASTEST MODEL")
    print("="*80)
    print(f"\nProvider: {fastest['provider']}")
    print(f"Model: {fastest['model']}")
    print(f"Duration: {fastest['duration']:.2f}s")
    print(f"Themes extracted: {fastest['num_themes']}")
    print(f"Tokens: {fastest['input_tokens']}in / {fastest['output_tokens']}out")

    # Calculate cost per token (approximate)
    cost_estimates = {
        "ANTHROPIC": {
            "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
            "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
            "claude-3-5-haiku-20241022": {"input": 0.8, "output": 4.0},
            "claude-opus-4-5-20251101": {"input": 15.0, "output": 75.0},
        },
        "OPENAI": {
            "gpt-4-turbo-preview": {"input": 10.0, "output": 30.0},
            "gpt-4o": {"input": 5.0, "output": 15.0},
            "gpt-4o-mini": {"input": 0.15, "output": 0.6},
            "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
        },
        "CEREBRAS": {
            "llama3.1-8b": {"input": 0.1, "output": 0.1},
            "llama3.1-70b": {"input": 0.6, "output": 0.6},
            "llama-3.3-70b": {"input": 0.6, "output": 0.6},
        }
    }

    # Add cost estimates
    for r in successful:
        provider = r['provider']
        model = r['model']

        if provider in cost_estimates and model in cost_estimates[provider]:
            rates = cost_estimates[provider][model]
            cost = (r['input_tokens'] / 1_000_000 * rates['input'] +
                   r['output_tokens'] / 1_000_000 * rates['output'])
            r['estimated_cost'] = cost
        else:
            r['estimated_cost'] = None

    print("\n" + "="*80)
    print("📈 ALL MODELS RANKED BY SPEED")
    print("="*80)
    print(f"\n{'Rank':<6}{'Provider':<12}{'Model':<30}{'Time':<10}{'Themes':<10}{'Cost':<10}")
    print("-" * 80)

    for i, r in enumerate(by_speed, 1):
        cost_str = f"${r['estimated_cost']*1000:.4f}" if r['estimated_cost'] else "N/A"
        print(f"{i:<6}{r['provider']:<12}{r['model']:<30}{r['duration']:.2f}s{' ':<6}{r['num_themes']:<10}{cost_str:<10}")

    # Find best value (speed/cost ratio)
    with_cost = [r for r in successful if r['estimated_cost'] is not None]
    if with_cost:
        # Score: lower is better (duration * cost)
        for r in with_cost:
            r['value_score'] = r['duration'] * r['estimated_cost']

        by_value = sorted(with_cost, key=lambda x: x['value_score'])
        best_value = by_value[0]

        print("\n" + "="*80)
        print("💰 BEST VALUE (Speed × Cost)")
        print("="*80)
        print(f"\nProvider: {best_value['provider']}")
        print(f"Model: {best_value['model']}")
        print(f"Duration: {best_value['duration']:.2f}s")
        print(f"Estimated cost per call: ${best_value['estimated_cost']*1000:.4f}")
        print(f"Value score: {best_value['value_score']:.4f} (lower is better)")

    # Quality analysis (did it extract the right themes?)
    print("\n" + "="*80)
    print("✅ QUALITY CHECK (Theme Extraction)")
    print("="*80)
    print("\nExpected themes: 'neural networks' and 'backpropagation'")
    print("-" * 80)

    for r in successful:
        themes = r.get('result', [])
        if isinstance(themes, list):
            theme_names = [t.get('theme_seed', '') for t in themes]
            has_nn = any('neural' in t.lower() for t in theme_names)
            has_bp = any('backprop' in t.lower() for t in theme_names)

            quality = "✓✓" if (has_nn and has_bp) else "✓" if (has_nn or has_bp) else "✗"

            print(f"{quality:<4}{r['provider']:<12}{r['model']:<30}Extracted: {', '.join(theme_names)}")

    # Failed models
    if failed:
        print("\n" + "="*80)
        print("❌ FAILED MODELS")
        print("="*80)

        for r in failed:
            error = r.get('error', 'Unknown error')
            print(f"\n{r['provider']} - {r['model']}")
            print(f"   Error: {error}")

    # Recommendations
    print("\n" + "="*80)
    print("💡 RECOMMENDATIONS")
    print("="*80)

    print(f"\n1. For SPEED: Use {fastest['provider']} - {fastest['model']}")
    print(f"   → {fastest['duration']:.2f}s per call")

    if with_cost:
        print(f"\n2. For VALUE: Use {best_value['provider']} - {best_value['model']}")
        print(f"   → {best_value['duration']:.2f}s per call at ${best_value['estimated_cost']*1000:.4f} per call")

    # Find highest quality
    quality_models = []
    for r in successful:
        themes = r.get('result', [])
        if isinstance(themes, list):
            theme_names = [t.get('theme_seed', '') for t in themes]
            has_nn = any('neural' in t.lower() for t in theme_names)
            has_bp = any('backprop' in t.lower() for t in theme_names)
            if has_nn and has_bp:
                quality_models.append(r)

    if quality_models:
        fastest_quality = min(quality_models, key=lambda x: x['duration'])
        print(f"\n3. For QUALITY + SPEED: Use {fastest_quality['provider']} - {fastest_quality['model']}")
        print(f"   → {fastest_quality['duration']:.2f}s per call, extracts all expected themes")

    print("\n" + "="*80)


def main():
    """Run all benchmarks and generate report."""
    print("\n" + "="*80)
    print(" "*20 + "MULTI-PROVIDER MODEL BENCHMARK")
    print("="*80)
    print("\nThis will test models from Anthropic, OpenAI, and Cerebras")
    print("on the same theme extraction task.\n")

    # Ensure results directory exists
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Run benchmarks
    providers = ["anthropic", "openai", "cerebras"]
    completed = []

    for provider in providers:
        success = run_benchmark(provider)
        if success:
            completed.append(provider)

    if not completed:
        print("\n❌ No benchmarks completed successfully.")
        return

    # Generate comparison report
    generate_comparison_report()

    print("\n" + "="*80)
    print("✅ Benchmark complete!")
    print("="*80)


if __name__ == "__main__":
    main()
