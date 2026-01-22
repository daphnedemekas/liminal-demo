"""Tests for prompt gathering functions."""
import pytest
from pathlib import Path
from src.prompt.gather import (
    gather_docs,
    gather_conversation,
    gather_schema,
    gather_teaching_context,
    gather_prompt_components,
)
from src.schema.full_schema import DiscoverySchema, UserProfile


def test_gather_docs(tmp_path):
    """Test gathering documentation files."""
    # Create test repo with some docs
    readme = tmp_path / "README.md"
    readme.write_text("# Test README")
    
    style = tmp_path / "STYLE.md"
    style.write_text("# Style Guide")
    
    docs = gather_docs(tmp_path)
    
    assert len(docs) == 2
    doc_paths = [d[0] for d in docs]
    assert readme in doc_paths
    assert style in doc_paths


def test_gather_docs_missing_files(tmp_path):
    """Test gathering docs when files don't exist."""
    docs = gather_docs(tmp_path)
    assert docs == []


def test_gather_conversation():
    """Test formatting conversation history."""
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
    ]
    
    result = gather_conversation(history)
    
    assert result is not None
    assert "User: Hello" in result
    assert "Assistant: Hi there!" in result
    assert "User: How are you?" in result


def test_gather_conversation_empty():
    """Test gathering conversation with empty history."""
    result = gather_conversation(None)
    assert result is None
    
    result = gather_conversation([])
    assert result is None


def test_gather_conversation_max_messages():
    """Test conversation truncation to max messages."""
    history = [
        {"role": "user", "content": f"Message {i}"}
        for i in range(20)
    ]
    
    result = gather_conversation(history, max_messages=5)
    
    # Should only include last 5 messages
    assert "Message 15" in result
    assert "Message 19" in result
    assert "Message 0" not in result


def test_gather_schema_with_pydantic():
    """Test serializing Pydantic schema."""
    # Create a minimal schema dict (simulating what would come from model_dump())
    schema_dict = {
        "curiosity_type": "interest",
        "tolerance_level": "medium",
        "interest_phase": "triggered",
    }
    
    # Test with a dict that simulates a Pydantic model
    class MockPydanticModel:
        def model_dump(self):
            return schema_dict
    
    mock_model = MockPydanticModel()
    result = gather_schema(mock_model)
    
    assert isinstance(result, dict)
    assert result.get("curiosity_type") == "interest"


def test_gather_schema_with_dict():
    """Test serializing dict schema."""
    schema_dict = {"test": "value", "nested": {"key": "val"}}
    result = gather_schema(schema_dict)
    
    assert result == schema_dict


def test_gather_schema_none():
    """Test gathering schema with None."""
    result = gather_schema(None)
    assert result is None


def test_gather_teaching_context():
    """Test gathering teaching context."""
    context = gather_teaching_context(
        assessment_concepts_known=["concept1", "concept2"],
        assessment_concepts_unclear=["concept3"],
        assessment_confidence=0.75
    )
    
    assert context["assessment_concepts_known"] == ["concept1", "concept2"]
    assert context["assessment_concepts_unclear"] == ["concept3"]
    assert context["assessment_confidence"] == 0.75


def test_gather_prompt_components_minimal(tmp_path):
    """Test gathering prompt components with minimal data."""
    components = gather_prompt_components(repo_root=tmp_path)
    
    assert components.repo_root == tmp_path
    assert components.docs == []
    assert components.conversation_history is None
    assert components.schema_state is None


def test_gather_prompt_components_full(tmp_path):
    """Test gathering prompt components with all data."""
    history = [{"role": "user", "content": "Test"}]
    schema_dict = {"test": "value"}
    
    components = gather_prompt_components(
        repo_root=tmp_path,
        step=("test_step", "step content"),
        conversation_history=history,
        schema_state=schema_dict,
        user_background="User background",
        goal_context={"goal": "test"},
        system_instructions="System instructions",
        run_mode="auto"
    )
    
    assert components.repo_root == tmp_path
    assert components.step == ("test_step", "step content")
    assert components.conversation_history == history
    assert components.schema_state == schema_dict
    assert components.user_background == "User background"
    assert components.goal_context == {"goal": "test"}
    assert components.system_instructions == "System instructions"
    assert components.run_mode == "auto"

