# Curiosity Discovery System

A multi-version LLM system that conducts 5-minute interviews to discover what someone is genuinely curious about. The system implicitly identifies topics users know somewhat, care about, have confusion around, and want to learn more about—all through natural conversation.

## Overview

This project demonstrates sophisticated prompt engineering techniques for curiosity discovery. The system never explicitly tells users it's analyzing them; instead, it feels like a natural conversation that somehow finds the perfect learning topic.

### Three Implementation Versions

1. **V1: 2-LLM System (Default)** - Interviewer + Ranker
   - Maximum control and transparency
   - LLM-A conducts natural conversation
   - LLM-B provides hidden scoring and guidance
   - Best for: Understanding the mechanics, fine-tuning

2. **V2: Single-LLM** - Internal Scoring
   - One LLM with extended system prompt
   - Uses `<thinking>` tags for internal analysis
   - Best for: Cost efficiency, simpler deployment

3. **V3: 3-LLM System** - Interviewer + Ranker + Polisher
   - Adds LLM-C to polish questions for maximum naturalness
   - Highest quality conversation
   - Best for: Production demos, showcasing capabilities

## Quick Start

### Installation

\`\`\`bash
# Clone or download this repository
cd liminal-demo

# Install dependencies
pip install -r requirements.txt

# Set up your API key
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
\`\`\`

### Running the Demo

\`\`\`bash
# Run with default version (V1: 2-LLM)
python -m src.cli

# Try the single-LLM version (cheaper, faster)
python -m src.cli --version v2

# Try the 3-LLM version (highest quality)
python -m src.cli --version v3

# Enable debug mode to see hidden analysis
python -m src.cli --debug
\`\`\`

### Example Interaction

\`\`\`
Assistant: What's something you ran into recently where you thought,
'I kind of get this… but not in a satisfying way'?

You: I've been doing code reviews and some of my comments get implemented
while others get ignored, even when they seem equally valid.

Assistant: Interesting. What do you think makes the difference between
the comments that land and the ones that don't?

[After 4-6 questions, the system identifies the topic]

Assistant: Okay, so you want to understand what makes code review
feedback stick versus bounce off. Here's the thing: it's usually not
about tone or technical correctness - it's about whether the feedback
aligns with what the person is already worried about. Ready to dive in?
```

## How It Works

### V1: 2-LLM System Flow

1. **User responds** to a question
2. **LLM-B (Ranker)** analyzes the conversation:
   - Extracts topic candidates
   - Scores each on 4 dimensions (1-5 scale):
     - Prior Knowledge: How much they already know
     - Stakes: How much they care
     - Confusion Edge: Clarity of their confusion
     - Surprise Potential: Potential for insights
   - Identifies what's still missing
   - Generates the next question
3. **LLM-A (Interviewer)** receives hidden guidance and asks naturally
4. **Repeat** until ready (usually 4-6 turns)
5. **Handoff**: Present the discovered topic with a learning hook

### Key Design Principles

**Implicit Analysis**
- User never knows they're being scored
- Questions feel natural and conversational
- No "I'm trying to identify your curiosity" language

**Concreteness Gate**
- Won't proceed without specific stories/beliefs/moments
- Repairs vague answers with targeted questions
- Anchors everything to concrete experience

**4-Dimension Scoring**
- Ensures topics have depth (prior knowledge ≥3)
- Ensures genuine care (stakes ≥3)
- Ensures real confusion (confusion edge ≥3)
- Ensures learning potential (surprise ≥2)

**Readiness Threshold**
- All scores ≥3 and total ≥12
- Specific confusion identified (not just "want to know more")
- Personal stakes clear

## Project Structure

```
liminal-demo/
├── src/
│   ├── models/              # Data models for conversation and analysis
│   ├── versions/            # Three implementation versions
│   │   ├── v1_two_llm.py   # Interviewer + Ranker
│   │   ├── v2_single_llm.py # Single-LLM with internal scoring
│   │   └── v3_three_llm.py  # Adds Polisher
│   ├── llm_client.py        # OpenAI API wrapper
│   ├── config.py            # Configuration loader
│   └── cli.py               # Command-line interface
├── prompts/                 # All system prompts
│   ├── interviewer_system.txt
│   ├── ranker_system.txt
│   ├── polisher_system.txt
│   └── single_llm_system.txt
├── examples/                # Example transcripts
│   ├── example_conversation_1.json
│   ├── example_conversation_2.json
│   └── example_conversation_3.json
├── outputs/                 # Saved session transcripts
└── config.yaml             # Model and threshold configuration
```

## Example Outputs

See the `examples/` directory for full conversation transcripts:

1. **example_conversation_1.json** - Successful quick discovery
2. **example_conversation_2.json** - Vague start → concretized
3. **example_conversation_3.json** - Topic shifting → narrowed

## Configuration

Edit `config.yaml` to customize:

- **Models**: Change which GPT-4 variant to use
- **Temperatures**: Adjust creativity vs consistency
- **Max turns**: How many exchanges before forcing commitment
- **Thresholds**: Minimum scores required for each dimension

## Debug Mode

Run with `--debug` to see the hidden ranker analysis:

```bash
python -m src.cli --debug
```

This shows:
- Candidate topics and scores
- Anti-patterns detected
- Readiness assessment
- Next question reasoning

## Design Philosophy

### Why This Matters

Most learning tools ask "what do you want to learn?" But people often:
- Don't know what they're curious about
- Choose topics that are too broad
- Pick things that sound impressive but they don't genuinely care about

This system finds the **sweet spot**:
- Enough knowledge to engage (not starting from zero)
- Genuine confusion (specific edge to explore)
- Real stakes (affects their work/life)
- Surprise potential (room for "aha\!" moments)

### Prompt Engineering Techniques

1. **Hidden/Visible Separation**: Analysis happens backstage, conversation stays natural
2. **Repair Patterns**: Specific strategies for common failure modes
3. **Concreteness Forcing**: Won't accept vague; demands specific moments
4. **Implicit Question Ladder**: Structured progression the user doesn't see
5. **Calibration Examples**: Helps LLM score consistently
6. **Anti-pattern Detection**: Identifies and fixes common issues (too broad, performative, etc.)

## Cost Estimates

**Per 5-minute session** (approximate, with GPT-4 Turbo):

- V1 (2-LLM): ~$0.15-0.30 (15-20k tokens)
- V2 (Single-LLM): ~$0.08-0.15 (8-12k tokens)
- V3 (3-LLM): ~$0.20-0.40 (20-25k tokens)

Debug mode shows exact token usage.

## Limitations

- Requires genuine curiosity; won't work if user is just testing
- Works best with topics the user has *some* exposure to
- Cultural/language assumptions in conversational style
- Depends on LLM quality (GPT-4 recommended)

## Future Enhancements

- [ ] Add conversation branching for multiple curiosities
- [ ] Integrate with actual learning content delivery
- [ ] Support for group curiosity discovery
- [ ] Multi-language support
- [ ] Web UI with rich visualizations
- [ ] Export to learning management systems

## License

MIT License - feel free to use and adapt.

## Contributing

This is a demonstration project. Fork and experiment\!

Interesting directions:
- Different scoring dimensions
- Alternative conversation styles
- Integration with specific learning platforms
- A/B testing different question strategies

## Contact

Questions or feedback? Open an issue or reach out.

---

**Built to demonstrate sophisticated multi-LLM orchestration and implicit curiosity discovery through prompt engineering.**
