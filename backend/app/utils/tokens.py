"""Token count estimation.

Used only when a provider does not report usage. The estimate is the common rule of thumb of
~4 characters per token for English text with BPE tokenizers; it can be off by 20-30% for
code or non-English text. Records that use it are stored with token_count_source='estimated'.
"""

import math

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))
