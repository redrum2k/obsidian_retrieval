import tiktoken

from .common import VaultError, canonical, cursor_decode, cursor_encode, digest

ENCODING = tiktoken.get_encoding("cl100k_base")


def measured(value):
    # Count the exact emitted JSON (including count field and terminal newline).
    previous = -1
    for _ in range(12):
        count = len(ENCODING.encode(canonical(value) + "\n", disallowed_special=()))
        if count == previous:
            return value
        value["output_tokens"] = count
        previous = count
    value["output_tokens"] = len(ENCODING.encode(canonical(value) + "\n", disallowed_special=()))
    return value


def page(items, snapshot, scope, budget=2000, limit=8, continuation=None, warnings=None):
    if not 256 <= budget <= 8000 or not 1 <= limit <= 20:
        raise VaultError("invalid_input", "budget must be 256..8000 and limit 1..20.")
    fingerprint = digest(canonical({"snapshot": snapshot, "scope": scope, "items": items}).encode())
    start, char = 0, 0
    if continuation:
        cursor = cursor_decode(continuation)
        if cursor.get("fingerprint") != fingerprint:
            raise VaultError("expired_cursor", "Result snapshot changed; restart this operation.")
        start, char = cursor["offset"], cursor.get("character", 0)
        if (
            not isinstance(start, int)
            or not 0 <= start <= len(items)
            or not isinstance(char, int)
            or char < 0
        ):
            raise VaultError("invalid_cursor", "Invalid continuation position.")
    result = {
        "items": [],
        "scope": scope,
        "snapshot": snapshot,
        "tokenizer": "cl100k_base",
        "warnings": sorted(set(warnings or [])),
        "truncated": False,
        "continuation": None,
        "output_tokens": 0,
    }

    def position(offset, character=0):
        more = offset < len(items)
        result["truncated"] = more
        result["continuation"] = (
            cursor_encode({"fingerprint": fingerprint, "offset": offset, "character": character})
            if more
            else None
        )
        measured(result)

    offset = start
    while offset < len(items) and len(result["items"]) < limit:
        item = dict(items[offset])
        text = item.get("text")
        if text is not None:
            item["text"] = text[char:]
            item["returned_span"] = {"start": char, "end": len(text)}
        result["items"].append(item)
        position(offset + 1)
        if result["output_tokens"] > budget:
            if text is not None:
                low, high, best = 1, len(text) - char, 0
                while low <= high:
                    middle = (low + high) // 2
                    item["text"] = text[char : char + middle]
                    item["returned_span"]["end"] = char + middle
                    position(offset, char + middle)
                    if result["output_tokens"] <= budget:
                        best, low = middle, middle + 1
                    else:
                        high = middle - 1
                if best:
                    item["text"] = text[char : char + best]
                    item["returned_span"]["end"] = char + best
                    position(offset, char + best)
                    return result
            result["items"].pop()
            position(offset, char)
            if not result["items"]:
                raise VaultError(
                    "budget_too_small", "Increase budget to fit one item's provenance."
                )
            return result
        offset += 1
        char = 0
    position(offset)
    if result["output_tokens"] > budget:
        raise VaultError("budget_too_small", "Increase budget for response metadata.")
    return result
