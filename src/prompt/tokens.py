"""Token counting and analysis for prompts."""
import tiktoken

# Use cl100k_base encoding (same as Claude and GPT-4)
_encoder = tiktoken.get_encoding("cl100k_base")

# Context limit: 120k leaves room for model response
MAX_SAFE_TOKENS = 120_000


def count_tokens(text: str) -> int:
    """
    Count tokens in text using cl100k_base encoding.
    
    This encoding is used by Claude and GPT-4, providing accurate token counts
    for models with 100k+ context windows.
    
    Args:
        text: Text to count tokens for
        
    Returns:
        Number of tokens in the text
    """
    if not text:
        return 0
    return len(_encoder.encode(text))

