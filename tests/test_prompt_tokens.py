"""Tests for token counting."""
import pytest
from src.prompt.tokens import count_tokens, MAX_SAFE_TOKENS


def test_count_tokens_empty():
    """Test counting tokens in empty string."""
    assert count_tokens("") == 0


def test_count_tokens_simple():
    """Test counting tokens in simple text."""
    text = "Hello, world!"
    tokens = count_tokens(text)
    
    # Should be a small positive number
    assert tokens > 0
    assert tokens < 10


def test_count_tokens_long_text():
    """Test counting tokens in longer text."""
    text = "This is a longer piece of text. " * 100
    tokens = count_tokens(text)
    
    # Should be proportional to text length
    assert tokens > 100


def test_count_tokens_unicode():
    """Test counting tokens with unicode characters."""
    text = "Hello 世界 🌍"
    tokens = count_tokens(text)
    
    # Should handle unicode correctly
    assert tokens > 0


def test_max_safe_tokens():
    """Test that MAX_SAFE_TOKENS is set correctly."""
    assert MAX_SAFE_TOKENS == 120_000


def test_count_tokens_consistency():
    """Test that token counting is consistent."""
    text = "The quick brown fox jumps over the lazy dog."
    tokens1 = count_tokens(text)
    tokens2 = count_tokens(text)
    
    assert tokens1 == tokens2


def test_count_tokens_vs_length():
    """Test that token count is roughly proportional to text length."""
    short_text = "Short"
    long_text = "This is a much longer piece of text that should have more tokens."
    
    short_tokens = count_tokens(short_text)
    long_tokens = count_tokens(long_text)
    
    assert long_tokens > short_tokens

