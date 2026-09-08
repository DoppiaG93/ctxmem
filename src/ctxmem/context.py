"""Pack complete retrieval records within a counted text budget."""

from . import retrieval


def token_counter():
    """Use cl100k_base when available, otherwise a conservative byte count.

    UTF-8 bytes bound token counts for byte-based tokenizers such as cl100k_base;
    this is deliberately stricter than the benchmark's chars/4 estimate.
    """
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
        return lambda text: len(encoder.encode_ordinary(text)), "tiktoken/cl100k_base"
    except Exception:
        return lambda text: len(text.encode("utf-8")), "utf8-bytes (conservative)"


def _priority(row):
    if row.get("_stale"):
        return 3
    if row.get("type") == "decision":
        return 0
    if row.get("type") in retrieval.ANSWER_MEMORY_TYPES:
        return 1
    return 2


def _block(row):
    head = "[{}] {}".format(row.get("type", "note"), row.get("title") or "")
    if row.get("mem_id"):
        head += " {" + row["mem_id"] + "}"
    parts = [head.rstrip()]
    if row.get("path"):
        parts.append("@ " + row["path"])
    if row.get("_stale"):
        parts.append("WARNING: STALE — " + str(row["_stale"]))
    parts.append(row.get("content") or "")
    return "\n".join(parts).rstrip()


def pack(rows, budget, counter=None):
    """Keep whole blocks, skipping oversized records and superseded memories.

    Count the entire payload including separators and the final newline. Stable
    ordering retains retrieval relevance within each priority group.
    """
    if budget <= 0:
        raise ValueError("budget must be a positive integer")
    count, method = counter or token_counter()
    payload = ""
    selected = 0
    seen = set()
    for row in sorted(rows, key=_priority):
        if row.get("_superseded"):
            continue
        block = _block(row)
        key = row.get("mem_id") or block
        if key in seen:
            continue
        seen.add(key)
        candidate = payload + ("\n" if payload else "") + block + "\n"
        if count(candidate) <= budget:
            payload = candidate
            selected += 1
    return {"text": payload, "tokens": count(payload), "budget": budget,
            "method": method, "selected": selected, "candidates": len(rows)}


def build(root, query, budget, limit=50, type_filter=None, mode=None):
    """Retrieve candidates using the configured backend, then pack them."""
    if budget <= 0 or limit <= 0:
        raise ValueError("budget and limit must be positive integers")
    if not query.strip():
        raise ValueError("query must not be empty")
    conn = retrieval.get_conn(root)
    if conn is None:
        raise ValueError("No memory initialized. Run 'ctxmem init' first.")
    try:
        rows, used = retrieval.search(conn, query, root, limit=limit,
                                      type_filter=type_filter, mode_override=mode)
        result = pack(rows, budget)
        result["mode"] = used
        return result
    finally:
        conn.close()
