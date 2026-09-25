"""Pinned cl100k_base tokenizer; packaged data avoids runtime network access."""

from pathlib import Path

import tiktoken
from tiktoken.load import load_tiktoken_bpe


def encoding():
    mergeable_ranks = load_tiktoken_bpe(
        str(Path(__file__).with_name("data") / "cl100k_base.tiktoken"),
        expected_hash="223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    )
    special_tokens = {
        "<|endoftext|>": 100257,
        "<|fim_prefix|>": 100258,
        "<|fim_middle|>": 100259,
        "<|fim_suffix|>": 100260,
        "<|endofprompt|>": 100276,
    }
    return tiktoken.Encoding(
        **{
            "name": "cl100k_base",
            "pat_str": r"""'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s""",
            "mergeable_ranks": mergeable_ranks,
            "special_tokens": special_tokens,
        }
    )
