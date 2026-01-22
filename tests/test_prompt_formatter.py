"""Tests for prompt formatter."""
import pytest
from pathlib import Path
from src.prompt.formatter import format_prompt, format_files
from src.prompt.components import PromptComponents, ClipboardContent, Voice


def test_format_prompt_minimal(tmp_path):
    """Test formatting with minimal components."""
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test_step", "Do something")
    )
    
    result = format_prompt(components)
    
    assert "<lf:step:test_step>" in result
    assert "Do something" in result
    assert "The step." in result


def test_format_prompt_with_conversation(tmp_path):
    """Test formatting with conversation history."""
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test_step", "Do something"),
        conversation_history=history
    )
    
    result = format_prompt(components)
    
    assert "<lf:conversation>" in result
    assert "User: Hello" in result
    assert "Assistant: Hi there!" in result


def test_format_prompt_with_schema(tmp_path):
    """Test formatting with schema state."""
    schema_state = {"test": "value", "nested": {"key": "val"}}
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test_step", "Do something"),
        schema_state=schema_state
    )
    
    result = format_prompt(components)
    
    assert "<lf:schema>" in result
    assert '"test": "value"' in result


def test_format_prompt_with_user_background(tmp_path):
    """Test formatting with user background."""
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test_step", "Do something"),
        user_background="User is a software engineer"
    )
    
    result = format_prompt(components)
    
    assert "<lf:user_background>" in result
    assert "User is a software engineer" in result


def test_format_prompt_with_goal_context(tmp_path):
    """Test formatting with goal context."""
    goal_context = {"goal": "Learn Python", "progress": 0.5}
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test_step", "Do something"),
        goal_context=goal_context
    )
    
    result = format_prompt(components)
    
    assert "<lf:goal_context>" in result
    assert '"goal": "Learn Python"' in result


def test_format_prompt_with_docs(tmp_path):
    """Test formatting with documentation."""
    readme = tmp_path / "README.md"
    readme.write_text("# Test README")
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test_step", "Do something"),
        docs=[(readme, "# Test README")]
    )
    
    result = format_prompt(components)
    
    assert "<lf:docs>" in result
    assert "<lf:README>" in result
    assert "# Test README" in result


def test_format_prompt_with_voices(tmp_path):
    """Test formatting with voices."""
    voices = [Voice(name="helpful", content="Be helpful and concise")]
    
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test_step", "Do something"),
        voices=voices
    )
    
    result = format_prompt(components)
    
    assert "<lf:voice:helpful>" in result
    assert "Be helpful and concise" in result


def test_format_prompt_with_system_instructions(tmp_path):
    """Test formatting with system instructions."""
    components = PromptComponents(
        repo_root=tmp_path,
        step=("test_step", "Do something"),
        system_instructions="You are a helpful assistant."
    )
    
    result = format_prompt(components)
    
    assert "<lf:system>" in result
    assert "You are a helpful assistant." in result


def test_format_prompt_empty_components(tmp_path):
    """Test formatting with empty components (should not add empty tags)."""
    components = PromptComponents(repo_root=tmp_path)
    
    result = format_prompt(components)
    
    # Should not contain empty tags
    assert "<lf:conversation>" not in result
    assert "<lf:schema>" not in result
    assert "<lf:docs>" not in result


def test_format_files(tmp_path):
    """Test formatting file contents."""
    file1 = tmp_path / "test1.py"
    file1.write_text("def test(): pass")
    
    file2 = tmp_path / "test2.py"
    file2.write_text("def test2(): pass")
    
    files = [
        (file1, "def test(): pass"),
        (file2, "def test2(): pass")
    ]
    
    result = format_files(files, tmp_path)
    
    assert "<lf:file" in result
    assert "test1.py" in result
    assert "test2.py" in result
    assert "def test(): pass" in result


def test_format_prompt_ordering(tmp_path):
    """Test that prompt sections are in correct order."""
    components = PromptComponents(
        repo_root=tmp_path,
        system_instructions="System",
        step=("test", "Step"),
        user_background="Background",
        conversation_history=[{"role": "user", "content": "Hello"}],
        docs=[(tmp_path / "README.md", "Docs")]
    )
    
    result = format_prompt(components)
    
    # System should come before step
    system_pos = result.find("<lf:system>")
    step_pos = result.find("<lf:step")
    assert system_pos < step_pos
    
    # Step should come before conversation
    conv_pos = result.find("<lf:conversation>")
    assert step_pos < conv_pos

