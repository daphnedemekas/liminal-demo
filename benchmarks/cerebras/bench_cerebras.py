#!/usr/bin/env python3
"""Benchmark Cerebras models for ranker tasks."""

import time
import json
from openai import OpenAI
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import get_cerebras_api_key

# Test conversation with concrete topic mention
TEST_CONVERSATION = """Assistant: When you encounter something you don't understand, does it feel more like an invitation or an itch?
User: It feels like an itch. When I don't understand something, I get this nagging feeling that won't go away until I figure it out.
Assistant: What kinds of things tend to create that itch for you?
User: I've been thinking about neural networks lately. The whole deep learning thing just seems like black magic to me.
Assistant: What is it about neural networks that feels like black magic to you?
User: I get the forward pass - you just multiply weights and add biases. But backpropagation doesn't make sense to me. How does the error actually propagate backward?"""

# Simplified ranker prompt for themes extraction
THEMES_PROMPT = """You are analyzing a conversation to update CONVERSATIONAL THEMES.

CURRENT CONVERSATIONAL THEMES:
[]

CONVERSATION:
{conversation}

TASK: Extract ALL themes mentioned - both concrete topics AND abstract patterns.

CRITICAL: Extract concrete topics the user mentioned:
- Examples: "neural networks", "backpropagation", "quantum mechanics"
- Use their exact words

Also extract abstract patterns:
- Goals: "wants to understand deeply"
- Preferences: "prefers visual explanations"

OUTPUT: Return JSON array of themes:
[
  {{
    "id": 1,
    "theme_seed": "exact phrase",
    "theme_type": "concrete_topic" | "abstract_goal" | "preference" | "metacognitive_pattern",
    "specificity": "broad" | "medium" | "specific"
  }}
]

Return ONLY valid JSON."""

# Cerebras typically offers Llama models
MODELS = [
    "llama3.1-8b",
    "llama3.1-70b",
    "llama-3.3-70b",
]

def test_model(client, model, prompt, temperature=0.3, max_tokens=1500):
    """Test a single model and return timing + result."""
    try:
        start = time.time()

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )

        duration = time.time() - start

        # Try to parse JSON
        result_text = response.choices[0].message.content.strip()

        # Extract JSON
        if '```json' in result_text:
            start_idx = result_text.find('```json') + 7
            end_idx = result_text.find('```', start_idx)
            result_text = result_text[start_idx:end_idx].strip()
        elif '```' in result_text:
            start_idx = result_text.find('```') + 3
            end_idx = result_text.find('```', start_idx)
            result_text = result_text[start_idx:end_idx].strip()

        # Find JSON boundaries
        first_bracket = result_text.find('[')
        if first_bracket != -1:
            depth = 0
            for i in range(first_bracket, len(result_text)):
                if result_text[i] == '[':
                    depth += 1
                elif result_text[i] == ']':
                    depth -= 1
                    if depth == 0:
                        result_text = result_text[first_bracket:i+1]
                        break

        try:
            parsed = json.loads(result_text)
            num_themes = len(parsed) if isinstance(parsed, list) else 1
        except:
            num_themes = -1
            parsed = None

        return {
            "model": model,
            "duration": duration,
            "success": parsed is not None,
            "num_themes": num_themes,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "result": parsed
        }

    except Exception as e:
        return {
            "model": model,
            "duration": -1,
            "success": False,
            "error": str(e)
        }

def main():
    try:
        api_key = get_cerebras_api_key()
    except:
        print("Error: Cerebras API key not found in config")
        print("Add it to config.yaml or set CEREBRAS_API_KEY environment variable")
        return

    # Cerebras uses OpenAI-compatible API
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.cerebras.ai/v1"
    )

    results = []

    print("="*60)
    print("CEREBRAS MODEL BENCHMARKS")
    print("="*60)
    print(f"\nTesting {len(MODELS)} models on theme extraction task")
    print(f"Temperature: 0.3, Max tokens: 1500\n")

    prompt = THEMES_PROMPT.format(conversation=TEST_CONVERSATION)

    for model in MODELS:
        print(f"Testing {model}...", end=" ", flush=True)

        result = test_model(client, model, prompt)
        results.append(result)

        if result["success"]:
            print(f"✓ {result['duration']:.2f}s - {result['num_themes']} themes - {result['input_tokens']}in/{result['output_tokens']}out tokens")
        else:
            print(f"✗ Error: {result.get('error', 'Unknown')}")

    # Save results
    output_file = Path(__file__).parent.parent / "results" / "cerebras_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✓ Results saved to {output_file}")

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    successful = [r for r in results if r["success"]]
    if successful:
        fastest = min(successful, key=lambda x: x["duration"])
        print(f"\n🏆 Fastest: {fastest['model']}")
        print(f"   Duration: {fastest['duration']:.2f}s")
        print(f"   Themes extracted: {fastest['num_themes']}")
        print(f"   Tokens: {fastest['input_tokens']}in / {fastest['output_tokens']}out")

        for r in sorted(successful, key=lambda x: x["duration"]):
            print(f"\n{r['model']}: {r['duration']:.2f}s ({r['num_themes']} themes)")

if __name__ == "__main__":
    main()
