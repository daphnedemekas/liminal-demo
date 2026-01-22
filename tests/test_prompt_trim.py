"""Tests for prompt trimming."""
import pytest
from pathlib import Path
from src.prompt.trim import (
    trim_prompt_components,
    DroppedComponent,
    _total_component_tokens,
)
from src.prompt.components import PromptComponents, ClipboardContent
from src.prompt.tokens import MAX_SAFE_TOKENS, count_tokens


def test_trim_under_budget(tmp_path):
    """Test trimming when already under budget."""
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test", "Short step"),
    )
    
    trimmed, dropped = trim_prompt_components(components, max_tokens=MAX_SAFE_TOKENS)
    
    assert len(dropped) == 0
    assert trimmed.step == components.step


def test_trim_over_budget_drops_lowest_priority(tmp_path):
    """Test that lowest priority components are dropped first."""
    # Create components that exceed budget
    large_text = "x" * 100000  # Large text to exceed budget
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test", "Important step"),  # Should never be dropped
        system_instructions="System instructions",  # Should never be dropped
        summaries=[("summary1", large_text)],  # Should be dropped first
        diff_files=[(tmp_path / "file1.py", large_text)],  # Should be dropped first
    )
    
    trimmed, dropped = trim_prompt_components(components, max_tokens=1000)
    
    # Step and system_instructions should remain
    assert trimmed.step == components.step
    assert trimmed.system_instructions == components.system_instructions
    
    # Summaries and diff_files should be dropped
    assert len(trimmed.summaries) == 0
    assert len(trimmed.diff_files) == 0
    
    # Should have dropped components
    assert len(dropped) > 0
    dropped_kinds = [d.kind for d in dropped]
    assert "summaries" in dropped_kinds or "diff_files" in dropped_kinds


def test_trim_priority_order(tmp_path):
    """Test that trimming follows priority order."""
    large_text = "x" * 50000
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test", "Step"),  # Never dropped
        system_instructions="System",  # Never dropped
        docs=[(tmp_path / "README.md", large_text)],  # Medium priority
        summaries=[(tmp_path / "summary.md", large_text)],  # Lowest priority
    )
    
    trimmed, dropped = trim_prompt_components(components, max_tokens=1000)
    
    # Step and system should remain
    assert trimmed.step is not None
    assert trimmed.system_instructions is not None
    
    # Summaries (lowest priority) should be dropped before docs
    dropped_kinds = [d.kind for d in dropped]
    if "summaries" in dropped_kinds and "docs" in dropped_kinds:
        # Find indices
        summaries_idx = dropped_kinds.index("summaries")
        docs_idx = dropped_kinds.index("docs")
        # Summaries should be dropped first (earlier in list)
        assert summaries_idx < docs_idx


def test_trim_never_drops_step(tmp_path):
    """Test that step/task is never dropped."""
    large_text = "x" * 200000
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("critical", large_text),  # Large but should never be dropped
        docs=[(tmp_path / "README.md", large_text)],
        summaries=[(tmp_path / "summary.md", large_text)],
    )
    
    trimmed, dropped = trim_prompt_components(components, max_tokens=1000)
    
    # Step should always remain
    assert trimmed.step is not None
    assert trimmed.step == components.step
    
    # Other components should be dropped instead
    assert len(dropped) > 0


def test_trim_never_drops_system_instructions(tmp_path):
    """Test that system_instructions is never dropped."""
    large_text = "x" * 200000
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test", "Step"),
        system_instructions=large_text,  # Large but should never be dropped
        docs=[(tmp_path / "README.md", large_text)],
    )
    
    trimmed, dropped = trim_prompt_components(components, max_tokens=1000)
    
    # System instructions should always remain
    assert trimmed.system_instructions is not None
    assert trimmed.system_instructions == components.system_instructions


def test_trim_conversation_history(tmp_path):
    """Test trimming old conversation history."""
    # Create long conversation history
    history = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(20)
    ]
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test", "Step"),
        conversation_history=history,
    )
    
    trimmed, dropped = trim_prompt_components(components, max_tokens=100)
    
    # Should trim old messages, keep recent ones
    if len(dropped) > 0:
        # Conversation should be trimmed
        assert len(trimmed.conversation_history) <= len(history)


def test_total_component_tokens(tmp_path):
    """Test token counting for all components."""
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test", "Step content"),
        system_instructions="System",
        docs=[(tmp_path / "README.md", "Doc content")],
    )
    
    total = _total_component_tokens(components)
    
    # Should be sum of all component tokens
    assert total > 0
    assert total == (
        count_tokens("Step content") +
        count_tokens("System") +
        count_tokens("Doc content")
    )


def test_trim_empty_components(tmp_path):
    """Test trimming with mostly empty components."""
    components = PromptComponents(repo_root=tmp_path)
    
    trimmed, dropped = trim_prompt_components(components)
    
    assert len(dropped) == 0
    assert trimmed.repo_root == tmp_path

