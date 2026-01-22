"""Tests for PromptComponents dataclass."""
import pytest
from pathlib import Path
from src.prompt.components import PromptComponents, ClipboardContent, Voice


def test_prompt_components_creation_minimal():
    """Test creating PromptComponents with minimal required fields."""
    repo_root = Path("/tmp/test")
    components = PromptComponents(repo_root=repo_root)
    
    assert components.repo_root == repo_root
    assert components.run_mode is None
    assert components.docs == []
    assert components.diff_files == []
    assert components.voices == []
    assert components.image_files == []
    assert components.summaries == []
    assert components.conversation_history is None
    assert components.schema_state is None


def test_prompt_components_with_all_fields():
    """Test creating PromptComponents with all fields populated."""
    repo_root = Path("/tmp/test")
    docs = [(Path("README.md"), "Test content")]
    diff_files = [(Path("test.py"), "def test(): pass")]
    voices = [Voice(name="test", content="Be helpful")]
    image_files = [Path("image.png")]
    summaries = [("summary1", "Summary content")]
    conversation_history = [{"role": "user", "content": "Hello"}]
    schema_state = {"test": "value"}
    
    components = PromptComponents(
        run_mode="auto",
        docs=docs,
        diff="diff content",
        diff_files=diff_files,
        step=("test_step", "step content"),
        repo_root=repo_root,
        clipboard=ClipboardContent(text="clipboard text"),
        system_instructions="System instructions",
        voices=voices,
        image_files=image_files,
        summaries=summaries,
        conversation_history=conversation_history,
        schema_state=schema_state,
        user_background="User background",
        goal_context={"goal": "test"}
    )
    
    assert components.run_mode == "auto"
    assert components.docs == docs
    assert components.diff == "diff content"
    assert components.diff_files == diff_files
    assert components.step == ("test_step", "step content")
    assert components.repo_root == repo_root
    assert components.clipboard.text == "clipboard text"
    assert components.system_instructions == "System instructions"
    assert components.voices == voices
    assert components.image_files == image_files
    assert components.summaries == summaries
    assert components.conversation_history == conversation_history
    assert components.schema_state == schema_state
    assert components.user_background == "User background"
    assert components.goal_context == {"goal": "test"}


def test_prompt_components_mutable_defaults():
    """Test that mutable defaults are properly initialized."""
    repo_root = Path("/tmp/test")
    components1 = PromptComponents(repo_root=repo_root)
    components2 = PromptComponents(repo_root=repo_root)
    
    # Mutable defaults should be separate instances
    components1.docs.append((Path("test1.md"), "content1"))
    components2.docs.append((Path("test2.md"), "content2"))
    
    assert len(components1.docs) == 1
    assert len(components2.docs) == 1
    assert components1.docs != components2.docs


def test_clipboard_content():
    """Test ClipboardContent dataclass."""
    clipboard = ClipboardContent(text="test text", image_path=Path("image.png"))
    assert clipboard.text == "test text"
    assert clipboard.image_path == Path("image.png")
    
    clipboard_empty = ClipboardContent()
    assert clipboard_empty.text is None
    assert clipboard_empty.image_path is None


def test_voice():
    """Test Voice dataclass."""
    voice = Voice(name="helpful", content="Be helpful and concise")
    assert voice.name == "helpful"
    assert voice.content == "Be helpful and concise"

