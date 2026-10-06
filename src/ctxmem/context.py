"""Pack complete retrieval records within a counted text budget."""

import math

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


TYPE_WEIGHTS = {
    "decision": 1.5,
    "note": 1.2,
    "session": 1.2,
    "todo": 1.2,
    "symbol": 1.0,
    "map": 0.9,
}


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


def _identity(row, block):
    return row.get("mem_id") or block


def _label(row):
    return row.get("title") or row.get("path") or (row.get("content") or "")[:40]


def _lexical_weight(row, query):
    query_terms = retrieval.meaningful_tokens(query)
    if not query_terms:
        return 1.0, None
    record = " ".join([
        row.get("title") or "",
        row.get("content") or "",
        row.get("tags") or "",
        row.get("path") or "",
    ])
    coverage = len(query_terms & retrieval.meaningful_tokens(record)) / len(query_terms)
    return 0.25 + 0.75 * coverage, coverage


def _utility(row, rank, cost, budget, query=None, keyword=False):
    """Balance retrieval rank, source authority, freshness, and budget cost."""
    relevance = 1.0 / (1.0 + 0.25 * rank)
    authority = TYPE_WEIGHTS.get(row.get("type"), 1.0)
    freshness = 0.5 if row.get("_stale") else 1.0
    lexical, coverage = _lexical_weight(row, query) if keyword else (1.0, None)
    target = max(1.0, budget / 4.0)
    size_penalty = math.sqrt(max(1.0, cost / target))
    utility = relevance * authority * freshness * lexical / size_penalty
    signals = {"relevance": relevance, "authority": authority,
               "freshness": freshness, "coverage": coverage,
               "size_penalty": size_penalty}
    return utility, signals


def _explanation(row, rank, cost, utility, status, reason, signals=None):
    return {
        "id": row.get("mem_id") or "",
        "type": row.get("type", "note"),
        "label": _label(row),
        "rank": rank + 1,
        "tokens": cost,
        "utility": round(utility, 4),
        "status": status,
        "reason": reason,
        "signals": signals or {},
    }


def _reason(signals, outcome):
    parts = ["rank relevance {:.2f}".format(signals["relevance"]),
             "type weight {:.2f}".format(signals["authority"])]
    if signals["freshness"] < 1.0:
        parts.append("stale penalty {:.2f}".format(signals["freshness"]))
    if signals["coverage"] is not None:
        parts.append("keyword coverage {:.0%}".format(signals["coverage"]))
    if signals["size_penalty"] > 1.0:
        parts.append("size penalty {:.2f}".format(signals["size_penalty"]))
    parts.append(outcome)
    return ", ".join(parts)


def pack(rows, budget, counter=None, explain=False, query=None, keyword=False):
    """Select whole blocks using relevance-aware utility within the budget.

    Retrieval rank is the primary relevance signal. Memory types receive a
    modest authority bonus, stale records are penalized, and blocks larger than
    one quarter of the budget receive a progressive size penalty. Superseded
    and duplicate records are excluded. The final budget check counts the exact
    payload including separators and the trailing newline.
    """
    if budget <= 0:
        raise ValueError("budget must be a positive integer")
    count, method = counter or token_counter()
    candidates = []
    details = []
    seen = set()
    for rank, row in enumerate(rows):
        block = _block(row)
        cost = count(block + "\n")
        if row.get("_superseded"):
            details.append(_explanation(
                row, rank, cost, 0.0, "skipped", "superseded memory"))
            continue
        key = _identity(row, block)
        if key in seen:
            details.append(_explanation(
                row, rank, cost, 0.0, "skipped", "duplicate record"))
            continue
        seen.add(key)
        utility, signals = _utility(row, rank, cost, budget, query, keyword)
        if keyword and signals["coverage"] == 0:
            details.append(_explanation(
                row, rank, cost, utility, "skipped",
                "no meaningful keyword overlap", signals))
            continue
        candidates.append((utility, rank, row, block, cost, signals))

    payload = ""
    selected = 0
    for utility, rank, row, block, cost, signals in sorted(
            candidates, key=lambda item: (-item[0], item[1])):
        candidate = payload + ("\n" if payload else "") + block + "\n"
        if count(candidate) <= budget:
            payload = candidate
            selected += 1
            status = "selected"
            reason = _reason(signals, "fits remaining budget")
        else:
            status = "skipped"
            reason = _reason(signals, "complete block does not fit remaining budget")
        details.append(_explanation(
            row, rank, cost, utility, status, reason, signals))

    result = {"text": payload, "tokens": count(payload), "budget": budget,
              "method": method, "selected": selected, "candidates": len(rows),
              "policy": "relevance-aware-v1"}
    if explain:
        result["selection"] = sorted(details, key=lambda item: item["rank"])
    return result


def build(root, query, budget, limit=50, type_filter=None, mode=None, explain=False):
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
        result = pack(rows, budget, explain=explain, query=query,
                      keyword=used.startswith("keyword"))
        result["mode"] = used
        return result
    finally:
        conn.close()
