"""Seed script to pre-populate the database with two demo personas.

Usage:
    python -m backend.seed_demo
"""

import json
from datetime import datetime, timezone, timedelta

from backend.database import (
    init_db, get_session_factory,
    UserProfile, Project, ChatMessage, Artifact, AgentRun,
)


def utcnow():
    return datetime.now(timezone.utc)


def seed():
    init_db()
    session = get_session_factory()()

    try:
        _seed_elena(session)
        _seed_marcus(session)
        session.commit()
        print("✓ Demo data seeded (Elena + Marcus)")
    finally:
        session.close()


# ── Elena ────────────────────────────────────────────────────────────

def _seed_elena(db):
    # Check if already seeded
    if db.query(UserProfile).filter(UserProfile.name == "Elena").first():
        print("  Elena already exists, skipping")
        return

    user = UserProfile(
        id="elena-demo-001",
        name="Elena",
        user_type="business",
        onboarding_info="I'm launching a direct-to-consumer skincare line called 'Glow Theory'. "
                        "I need help with competitive analysis, launch planning, social media ads, "
                        "and pricing strategy. I'm a solo founder with a small budget.",
        onboarding_complete=True,
        default_involvement="check_ins",
        explanation_preference="brief_summary",
        known_domains={"ecommerce": True, "skincare": True, "marketing": True},
        model_summary="Solo e-commerce founder launching a DTC skincare brand. "
                      "Prefers concise updates and actionable deliverables.",
    )
    db.add(user)
    db.flush()

    project = Project(
        user_id=user.id,
        name="Product Launch Command Center",
        description="Everything I need to launch Glow Theory — competitive research, "
                    "launch checklist, ad creatives, and pricing.",
        status="active",
    )
    db.add(project)
    db.flush()

    # Agent run (completed)
    run = AgentRun(
        run_id="elena-run-001",
        project_id=project.id,
        user_id=user.id,
        goal="Research competitors, build launch checklist, draft Instagram ad concepts, and analyze pricing",
        status="done",
        result_summary="Completed competitive analysis, launch checklist, ad concepts, and pricing report.",
        created_at=utcnow() - timedelta(hours=2),
        completed_at=utcnow() - timedelta(hours=1, minutes=50),
    )
    db.add(run)
    db.flush()

    # Chat messages
    base_time = utcnow() - timedelta(hours=2)
    messages = [
        ("user", "I'm getting ready to launch my skincare line Glow Theory in 8 weeks. "
                 "Can you help me figure out where I stand vs competitors and what I need to do?", []),
        ("assistant",
         "Absolutely! I'll put together a full launch command center for you. I'm going to research "
         "your top competitors, build a week-by-week launch checklist, draft some Instagram ad concepts, "
         "and analyze pricing strategies. Give me a few minutes to pull this together.",
         [{"label": "Sounds good", "description": "Confirm and proceed", "action_text": "Go ahead!"}]),
        ("user", "Go ahead!", []),
        ("assistant",
         "Your launch command center is ready! I've created four workspace artifacts:\n\n"
         "• **Competitive Landscape** — side-by-side comparison of Glow Theory vs. The Ordinary, Drunk Elephant, and Versed\n"
         "• **8-Week Launch Checklist** — everything from formulation sign-off to launch day\n"
         "• **Instagram Ad Concepts** — 5 ready-to-brief ad ideas with hooks and CTAs\n"
         "• **Pricing Strategy Report** — margin analysis and recommended price points\n\n"
         "Check the workspace tab to explore each one in detail.",
         [{"label": "Deep dive on pricing", "description": "Get more detail on pricing strategy",
           "action_text": "Can you go deeper on the pricing analysis? I want to understand margin sensitivity."},
          {"label": "Refresh workspace", "description": "Re-run agents and update all artifacts with fresh data",
           "action_text": "Please refresh and update all of my workspace artifacts with the latest information."}]),
    ]
    for i, (role, content, actions) in enumerate(messages):
        db.add(ChatMessage(
            project_id=project.id,
            role=role,
            content=content,
            actions=actions,
            run_id=run.run_id if role == "assistant" and i > 0 else None,
            created_at=base_time + timedelta(minutes=i * 2),
        ))

    # Artifacts
    db.add(Artifact(
        run_id=run.run_id,
        project_id=project.id,
        artifact_type="comparison_table",
        title="Competitive Landscape",
        content=(
            "| Feature | Glow Theory | The Ordinary | Drunk Elephant | Versed |\n"
            "|---|---|---|---|---|\n"
            "| **Price Range** | $18–$34 | $6–$15 | $34–$90 | $10–$24 |\n"
            "| **Hero Ingredient** | Bakuchiol + Niacinamide | Acids & Retinoids | Marula Oil | Adaptogens |\n"
            "| **Target Demo** | Millennial/Gen-Z, clean beauty | Budget-conscious | Premium luxury | Clean & affordable |\n"
            "| **DTC Website** | Launching | Yes | Yes | Yes (+ Target) |\n"
            "| **Instagram Followers** | 0 (pre-launch) | 1.2M | 1.8M | 320K |\n"
            "| **Unique Angle** | Science-backed, founder story | Radical transparency pricing | Clinical luxury | Accessible clean beauty |\n"
            "| **Key Weakness** | No brand awareness yet | Overwhelming product line | High price barrier | Generic positioning |"
        ),
        sources=[{"url": "https://theordinary.com"}, {"url": "https://drunkelephant.com"}, {"url": "https://versed.com"}],
    ))

    db.add(Artifact(
        run_id=run.run_id,
        project_id=project.id,
        artifact_type="checklist",
        title="8-Week Launch Checklist",
        content={
            "categories": [
                {"name": "Weeks 1–2: Foundation", "items": [
                    {"text": "Finalize product formulations and get stability test results", "checked": True},
                    {"text": "Lock in packaging design and place MOQ order", "checked": True},
                    {"text": "Register LLC and secure business insurance", "checked": False},
                    {"text": "Set up Shopify store with brand theme", "checked": False},
                ]},
                {"name": "Weeks 3–4: Content & Community", "items": [
                    {"text": "Shoot product photography (flatlays + lifestyle)", "checked": False},
                    {"text": "Write product descriptions and brand story page", "checked": False},
                    {"text": "Create Instagram content calendar (3 posts/week)", "checked": False},
                    {"text": "Seed products to 10 micro-influencers", "checked": False},
                ]},
                {"name": "Weeks 5–6: Pre-Launch", "items": [
                    {"text": "Set up email capture landing page with launch incentive", "checked": False},
                    {"text": "Run $500 awareness campaign on Instagram/TikTok", "checked": False},
                    {"text": "Finalize shipping/fulfillment partner and test orders", "checked": False},
                    {"text": "Prepare PR kit and send to 5 beauty editors", "checked": False},
                ]},
                {"name": "Weeks 7–8: Launch", "items": [
                    {"text": "Launch email blast to waitlist", "checked": False},
                    {"text": "Go live on Shopify — monitor checkout flow", "checked": False},
                    {"text": "Activate paid social ads ($50/day budget)", "checked": False},
                    {"text": "Post launch-day Instagram Reel + Stories", "checked": False},
                ]},
            ]
        },
    ))

    db.add(Artifact(
        run_id=run.run_id,
        project_id=project.id,
        artifact_type="resource_list",
        title="Instagram Ad Concepts",
        content={
            "resources": [
                {"title": "The Science Drop", "url": "",
                 "description": "Hook: 'Your moisturizer is lying to you.' Show lab footage → ingredient breakdown → CTA 'Shop the truth' — targets ingredient-savvy shoppers",
                 "category": "Awareness"},
                {"title": "Founder Story Reel", "url": "",
                 "description": "Hook: 'I quit my job to make skincare that actually works.' Behind-the-scenes founder journey → product reveal → 'Join the waitlist' CTA",
                 "category": "Awareness"},
                {"title": "Before & After Carousel", "url": "",
                 "description": "4-slide carousel with 28-day user trial results. Social proof headline + swipe-to-reveal format → 'Try it yourself' CTA",
                 "category": "Conversion"},
                {"title": "Routine Builder UGC", "url": "",
                 "description": "Partner with 3 micro-influencers to film 'morning routine' reels featuring Glow Theory. Authentic, lo-fi aesthetic → 'Link in bio'",
                 "category": "Conversion"},
                {"title": "Limited Launch Countdown", "url": "",
                 "description": "Stories series: 7-day countdown to launch with daily skincare tips. Builds urgency + educates → 'Turn on notifications' CTA",
                 "category": "Retention"},
            ]
        },
    ))

    db.add(Artifact(
        run_id=run.run_id,
        project_id=project.id,
        artifact_type="report",
        title="Pricing Strategy Report",
        content=(
            "## Glow Theory — Pricing Strategy Analysis\n\n"
            "### Recommended Price Points\n"
            "| Product | Cost of Goods | Recommended Price | Margin |\n"
            "|---|---|---|---|\n"
            "| Daily Moisturizer (50ml) | $4.20 | $28 | 85% |\n"
            "| Brightening Serum (30ml) | $5.80 | $34 | 83% |\n"
            "| Gentle Cleanser (120ml) | $2.90 | $18 | 84% |\n"
            "| The Starter Set (all 3) | $12.90 | $68 (save $12) | 81% |\n\n"
            "### Positioning\n"
            "Glow Theory sits in the **'affordable premium'** tier — above The Ordinary and Versed, "
            "well below Drunk Elephant. This is the fastest-growing segment in DTC skincare.\n\n"
            "### Key Recommendations\n"
            "1. **Launch with the Starter Set** as the hero SKU — bundles convert 2.3× better for new brands\n"
            "2. **Offer a founding-member discount** (15% off first order) to drive early reviews\n"
            "3. **Avoid deep discounting** — it erodes perceived value in the clean beauty space\n"
            "4. **Build toward subscription** — introduce 'auto-replenish' at month 3 with a 10% loyalty discount\n\n"
            "### Margin Sensitivity\n"
            "At the recommended prices, you maintain 80%+ margins even after:\n"
            "- 15% founding discount → effective margin ~70%\n"
            "- $5 flat-rate shipping subsidy → margin ~65% on individual items, ~72% on bundles\n"
            "- Instagram ad spend at $50/day → break-even at ~3 orders/day\n"
        ),
    ))


# ── Marcus ───────────────────────────────────────────────────────────

def _seed_marcus(db):
    if db.query(UserProfile).filter(UserProfile.name == "Marcus").first():
        print("  Marcus already exists, skipping")
        return

    user = UserProfile(
        id="marcus-demo-002",
        name="Marcus",
        user_type="researcher",
        onboarding_info="I'm a VP of Engineering at a mid-size SaaS company. I need to stay on top of "
                        "AI/ML developments, evaluate build-vs-buy decisions for LLM features, "
                        "and brief my team weekly. I want deep technical analysis, not marketing fluff.",
        onboarding_complete=True,
        default_involvement="hands_off",
        explanation_preference="show_your_work",
        known_domains={"engineering": True, "ai_ml": True, "saas": True},
        model_summary="VP Engineering at a SaaS company. Wants rigorous technical analysis "
                      "of AI/ML landscape. Prefers detailed reasoning and primary sources.",
    )
    db.add(user)
    db.flush()

    project = Project(
        user_id=user.id,
        name="AI Engineering Intelligence Brief",
        description="Weekly intelligence brief on AI/ML developments relevant to our engineering org — "
                    "model comparisons, production patterns, and build-vs-buy analysis.",
        status="active",
    )
    db.add(project)
    db.flush()

    run = AgentRun(
        run_id="marcus-run-001",
        project_id=project.id,
        user_id=user.id,
        goal="Compare OpenAI vs open-source LLMs, compile weekly AI digest, curate production LLM talks, build decision checklist",
        status="done",
        result_summary="Completed model comparison, weekly digest, video collection, and build-vs-buy checklist.",
        created_at=utcnow() - timedelta(hours=3),
        completed_at=utcnow() - timedelta(hours=2, minutes=45),
    )
    db.add(run)
    db.flush()

    base_time = utcnow() - timedelta(hours=3)
    messages = [
        ("user",
         "I need to brief my eng team this Friday on where things stand with LLMs. "
         "Can you put together a comparison of OpenAI models vs open-source alternatives, "
         "a digest of this week's important AI news, some good conference talks on production LLM systems, "
         "and a framework for when to build vs buy?",
         []),
        ("assistant",
         "Good scope. I'll structure this as four deliverables for your Friday brief:\n\n"
         "1. **Model comparison matrix** — GPT-4o, Claude, Llama 3, Mixtral across key dimensions\n"
         "2. **Weekly AI digest** — curated developments with engineering relevance scores\n"
         "3. **Production LLM talks** — conference presentations on real-world deployment patterns\n"
         "4. **Build vs. Buy checklist** — decision framework for your specific context\n\n"
         "I'll go deep on benchmarks and include primary sources. Running research now.",
         [{"label": "Add cost analysis", "description": "Include API pricing comparison",
           "action_text": "Also add a detailed cost analysis comparing API pricing across providers."}]),
        ("user", "Perfect, that's exactly what I need.", []),
        ("assistant",
         "Your intelligence brief is ready. I've populated four artifacts in your workspace:\n\n"
         "• **OpenAI vs Open-Source LLMs** — detailed comparison table with benchmarks, latency, and cost\n"
         "• **Weekly AI Engineering Digest** — 6 developments ranked by relevance to your stack\n"
         "• **Production LLM Systems Talks** — 5 curated conference talks with key takeaways\n"
         "• **Build vs. Buy Decision Checklist** — structured framework with your context baked in\n\n"
         "Everything is sourced and ready to drop into your Friday deck.",
         [{"label": "Go deeper on Llama 3", "description": "Expand analysis on Llama 3 fine-tuning",
           "action_text": "Can you do a deep dive on Llama 3 fine-tuning — cost, infra requirements, and when it makes sense vs API?"},
          {"label": "Refresh workspace", "description": "Re-run agents and update all artifacts with fresh data",
           "action_text": "Please refresh and update all of my workspace artifacts with the latest information."}]),
    ]
    for i, (role, content, actions) in enumerate(messages):
        db.add(ChatMessage(
            project_id=project.id,
            role=role,
            content=content,
            actions=actions,
            run_id=run.run_id if role == "assistant" and i > 0 else None,
            created_at=base_time + timedelta(minutes=i * 3),
        ))

    # Artifacts
    db.add(Artifact(
        run_id=run.run_id,
        project_id=project.id,
        artifact_type="comparison_table",
        title="OpenAI vs Open-Source LLMs",
        content=(
            "| Dimension | GPT-4o | Claude 3.5 Sonnet | Llama 3 70B | Mixtral 8x22B |\n"
            "|---|---|---|---|---|\n"
            "| **MMLU Score** | 88.7 | 88.3 | 82.0 | 77.8 |\n"
            "| **HumanEval** | 90.2 | 92.0 | 81.7 | 75.4 |\n"
            "| **Context Window** | 128K | 200K | 8K (128K extended) | 64K |\n"
            "| **Latency (TTFT)** | ~300ms | ~400ms | ~200ms (self-hosted) | ~250ms (self-hosted) |\n"
            "| **Cost (1M tokens)** | $5 in / $15 out | $3 in / $15 out | $0 (infra only) | $0 (infra only) |\n"
            "| **Fine-tuning** | Limited (GPT-4o mini) | Not available | Full weight + LoRA | Full weight + LoRA |\n"
            "| **Data Privacy** | Data processed by OpenAI | Data processed by Anthropic | Full control | Full control |\n"
            "| **Best For** | General tasks, vision | Long-context, analysis | Custom models, privacy | Cost-efficient routing |\n"
            "| **Key Risk** | Vendor lock-in, cost | Vendor lock-in | Infra complexity | Smaller community |"
        ),
        sources=[
            {"url": "https://openai.com/index/gpt-4o"},
            {"url": "https://llama.meta.com"},
            {"url": "https://mistral.ai/news/mixtral-8x22b"},
        ],
    ))

    db.add(Artifact(
        run_id=run.run_id,
        project_id=project.id,
        artifact_type="report",
        title="Weekly AI Engineering Digest",
        content=(
            "## AI Engineering Digest — Week in Review\n\n"
            "### 🔴 High Relevance\n\n"
            "**1. OpenAI Structured Outputs GA** — JSON Schema enforcement now generally available across "
            "all GPT-4o endpoints. Eliminates the need for output parsers in most production pipelines. "
            "*Impact: Simplifies your current extraction pipeline.*\n\n"
            "**2. Llama 3.1 405B Release** — Meta releases largest open model. Early benchmarks show "
            "GPT-4 class performance on reasoning tasks. Available on AWS Bedrock and Azure. "
            "*Impact: Changes the build-vs-buy calculus for your team.*\n\n"
            "### 🟡 Medium Relevance\n\n"
            "**3. Anthropic Tool Use Improvements** — Claude now supports parallel tool calls and "
            "better structured extraction. Relevant if you're evaluating multi-step agent architectures. "
            "*Impact: Worth prototyping for your document processing pipeline.*\n\n"
            "**4. vLLM 0.5 Released** — 2x throughput improvement for self-hosted inference. "
            "PagedAttention v2 reduces memory fragmentation. "
            "*Impact: Lowers the bar for self-hosting if you go the open-source route.*\n\n"
            "### 🟢 Watching\n\n"
            "**5. Google Gemini 1.5 Pro Price Cut** — 50% reduction in API pricing. "
            "Now competitive with GPT-4o on cost. Long context (1M tokens) is a differentiator.\n\n"
            "**6. LangChain v0.2 Migration Guide** — Breaking changes in the chain abstraction. "
            "If you're using LangChain, budget time for migration.\n"
        ),
    ))

    db.add(Artifact(
        run_id=run.run_id,
        project_id=project.id,
        artifact_type="video_collection",
        title="Production LLM Systems Talks",
        content={
            "videos": [
                {"title": "Building LLM Apps for Production — Chip Huyen",
                 "url": "https://www.youtube.com/watch?v=example1",
                 "description": "Practical patterns for LLM app architecture: eval-driven development, prompt management, and guardrails. From AI Eng Summit 2024."},
                {"title": "Scaling Retrieval-Augmented Generation at LinkedIn",
                 "url": "https://www.youtube.com/watch?v=example2",
                 "description": "How LinkedIn built their RAG pipeline for 900M+ profiles. Covers chunking strategies, embedding model selection, and hybrid search."},
                {"title": "The Post-LLM Software Stack — Simon Willison",
                 "url": "https://www.youtube.com/watch?v=example3",
                 "description": "Opinionated take on how the software stack changes with LLMs. Great for framing build-vs-buy decisions with your team."},
                {"title": "Fine-tuning Llama 2 for Production — Hamel Husain",
                 "url": "https://www.youtube.com/watch?v=example4",
                 "description": "Step-by-step guide to fine-tuning open models. Covers data preparation, LoRA vs full fine-tuning, and evaluation methodology."},
                {"title": "LLM Observability in Practice — Arize AI",
                 "url": "https://www.youtube.com/watch?v=example5",
                 "description": "How to monitor LLM apps in production: tracing, drift detection, and cost tracking. Includes open-source tooling recommendations."},
            ]
        },
    ))

    db.add(Artifact(
        run_id=run.run_id,
        project_id=project.id,
        artifact_type="checklist",
        title="Build vs. Buy Decision Checklist",
        content={
            "categories": [
                {"name": "When to Use APIs (Buy)", "items": [
                    {"text": "Your use case is general-purpose (summarization, Q&A, classification)", "checked": False},
                    {"text": "You need to ship in < 4 weeks", "checked": False},
                    {"text": "Your data isn't highly sensitive / regulated", "checked": False},
                    {"text": "Volume is < 1M tokens/day (API cost stays reasonable)", "checked": False},
                    {"text": "You need multimodal capabilities (vision, audio)", "checked": False},
                ]},
                {"name": "When to Self-Host (Build)", "items": [
                    {"text": "Data cannot leave your infrastructure (compliance, PII)", "checked": False},
                    {"text": "You need fine-tuned models for domain-specific performance", "checked": False},
                    {"text": "Volume exceeds 10M tokens/day (self-hosting becomes cheaper)", "checked": False},
                    {"text": "You have ML engineers who can manage inference infrastructure", "checked": False},
                    {"text": "Latency requirements are < 100ms (co-located inference)", "checked": False},
                ]},
                {"name": "Hybrid Approach Indicators", "items": [
                    {"text": "Use API for prototyping, switch to self-hosted after validation", "checked": False},
                    {"text": "Route simple tasks to small open models, complex to GPT-4/Claude", "checked": False},
                    {"text": "Self-host for PII workloads, API for everything else", "checked": False},
                    {"text": "Fine-tune an open model on your proprietary data, use API as fallback", "checked": False},
                ]},
            ]
        },
    ))


if __name__ == "__main__":
    seed()
